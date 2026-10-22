"""Recruit attempts: queued row, pollable status, temporary audio.

The request path talks through the candidate's own client. Inserts go through
`submit_queued_recruit_attempt` (migration 0011) so a job is created in the
same transaction and a candidate cannot write a completed row. The worker
uses the service role to mark running / failed and to download audio.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel
from supabase import Client

from app.recruit.copy import PER_ANSWER_NOT_ANSWERED
from app.storage.documents import safe_filename

logger = logging.getLogger(__name__)

AUDIO_BUCKET = "recruit-audio"
ORPHAN_TABLE = "recruit_audio_orphans"
# Queued and running attempts still need the recording. Anything else should
# already have been deleted; the sweep treats those objects as unattached.
IN_PROGRESS_ATTEMPT_STATUSES = ("queued", "running")
# Young objects may still be inside the critique that uploaded them. Older
# than this, and not on an in-progress attempt, they are recordings we said
# we would not keep.
STALE_AUDIO_AFTER = timedelta(hours=24)
# Supabase storage list defaults to 100. Ask for that page and walk offset
# ourselves so a busy prefix is not silently truncated.
_LIST_PAGE = 100
# user / attempt / file is three levels. Deeper than this is not our layout.
_MAX_LIST_DEPTH = 8
_PLACEHOLDER = ".emptyFolderPlaceholder"

AttemptStatus = Literal["queued", "running", "completed", "abandoned", "critique_failed"]
OrphanReason = Literal["delete_failed", "stale_unattached"]


@dataclass(frozen=True)
class RecruitAudioObject:
    path: str
    created_at: datetime | None


class RecruitAttemptRecord(BaseModel):
    id: str
    user_id: str
    scenario_id: str
    question_text: str
    started_at: datetime
    completed_at: datetime | None = None
    status: AttemptStatus
    audio_storage_path: str | None = None
    error: str | None = None
    candidate_lines: list[str] = []
    held_candidate_lines: list[str] = []
    audio_retained: bool = False
    criterion_id: str | None = None
    board_id: str | None = None
    slot_index: int | None = None


def utc_day_start(now: datetime | None = None) -> datetime:
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def count_attempts(db: Client, *, started_on_or_after: datetime | None = None) -> int:
    """How many attempts this candidate already has. RLS scopes the table.

    Used for the daily ceiling: every started row counts, including queued
    and failed ones. The free-session grant is `count_delivered_attempts`.
    """
    query = db.table("recruit_attempts").select("id")
    if started_on_or_after is not None:
        query = query.gte("started_at", started_on_or_after.isoformat())
    rows = query.execute().data or []
    return len(rows)


def critique_was_delivered(status: str, candidate_lines: object) -> bool:
    """True when the candidate actually received well/improve notes.

    The UI only renders `candidate_lines` on a completed attempt. An empty
    array — the Aug 2026 completed-but-blank shape — did not demonstrate
    help, so it must not consume a free session.
    """
    if status != "completed":
        return False
    if not isinstance(candidate_lines, list):
        return False
    return any(str(line).strip() for line in candidate_lines)


def count_delivered_attempts(db: Client, *, started_on_or_after: datetime | None = None) -> int:
    """Attempts that showed the candidate critique. RLS scopes the table.

    Completed + non-empty `candidate_lines`. Queued, running, failed,
    abandoned, and completed-but-empty rows do not consume a free session.
    """
    query = db.table("recruit_attempts").select("id,status,candidate_lines").eq(
        "status", "completed"
    )
    if started_on_or_after is not None:
        query = query.gte("started_at", started_on_or_after.isoformat())
    rows = query.execute().data or []
    return sum(
        1
        for row in rows
        if critique_was_delivered(row.get("status") or "", row.get("candidate_lines"))
    )


def _distinct_scenario_ids(rows: list) -> list[str]:
    seen: list[str] = []
    found: set[str] = set()
    for row in rows:
        sid = row.get("scenario_id")
        if sid and sid not in found:
            found.add(sid)
            seen.append(sid)
    return seen


def attempted_scenario_ids(db: Client) -> list[str]:
    """Distinct scenario ids already issued to this candidate. RLS scopes the table.

    Any attempt row consumes novelty — queued, running, completed, failed, or
    abandoned. The next issue must not re-offer those prompts.
    """
    rows = db.table("recruit_attempts").select("scenario_id").execute().data or []
    return _distinct_scenario_ids(rows)


def completed_scenario_ids(db: Client) -> list[str]:
    """Distinct bank questions this candidate has finished. RLS scopes the table.

    AC3: only `completed` — queued, running, critique_failed, and abandoned
    do not count as answered.
    """
    rows = (
        db.table("recruit_attempts")
        .select("scenario_id")
        .eq("status", "completed")
        .execute()
        .data
        or []
    )
    return _distinct_scenario_ids(rows)


def get_attempt(db: Client, attempt_id: str) -> RecruitAttemptRecord | None:
    rows = (
        db.table("recruit_attempts")
        .select(
            "id,user_id,scenario_id,question_text,started_at,completed_at,"
            "status,audio_storage_path,error,candidate_lines,"
            "audio_retained,criterion_id,board_id,slot_index"
        )
        .eq("id", attempt_id)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        return None
    row = rows[0]
    for key in ("candidate_lines", "held_candidate_lines"):
        lines = row.get(key) or []
        if not isinstance(lines, list):
            lines = []
        row[key] = [str(line) for line in lines]
    return RecruitAttemptRecord.model_validate(row)


def store_audio(db: Client, user_id: str, attempt_id: str, filename: str, data: bytes) -> str:
    stored = safe_filename(filename)
    path = f"{user_id}/{attempt_id}/{stored}"
    content_type = "audio/webm"
    if stored.endswith(".m4a") or stored.endswith(".mp4"):
        content_type = "audio/mp4"
    db.storage.from_(AUDIO_BUCKET).upload(
        path, data, {"content-type": content_type, "upsert": "false"}
    )
    return path


def download_audio(db: Client, path: str) -> bytes:
    return db.storage.from_(AUDIO_BUCKET).download(path)


def delete_audio(db: Client, path: str | None) -> None:
    """Remove one recording. A failure is an orphan, not a raised exception.

    Callers have often already finished the attempt (the critique is stored,
    or the insert rolled back). Raising here would retry work that succeeded
    and still leave the file. The ERROR line is the alert; the
    `recruit_audio_orphans` row is the list to retry from.
    """
    if not path:
        return
    try:
        db.storage.from_(AUDIO_BUCKET).remove([path])
    except Exception as exc:
        detail = f"{type(exc).__name__}: {exc}"
        logger.error(
            "recruit_audio_delete_failed storage_path=%s error=%s",
            path,
            " ".join(detail.split()),
            exc_info=True,
        )
        record_recruit_audio_orphan(db, path, reason="delete_failed", error=detail)
        return
    clear_recruit_audio_orphan(db, path)


def record_recruit_audio_orphan(
    db: Client, path: str, *, reason: OrphanReason, error: str
) -> None:
    """Upsert one path we failed to discard. Service role only; see migration 0019."""
    detail = " ".join((error or "unknown error").split())[:2000] or "unknown error"
    now = datetime.now(UTC).isoformat()
    try:
        existing = (
            db.table(ORPHAN_TABLE)
            .select("storage_path")
            .eq("storage_path", path)
            .limit(1)
            .execute()
            .data
        )
        if existing:
            (
                db.table(ORPHAN_TABLE)
                .update({"reason": reason, "error": detail, "last_seen_at": now})
                .eq("storage_path", path)
                .execute()
            )
            return
        db.table(ORPHAN_TABLE).insert(
            {
                "storage_path": path,
                "reason": reason,
                "error": detail,
                "first_seen_at": now,
                "last_seen_at": now,
            }
        ).execute()
    except Exception:
        logger.error(
            "recruit_audio_orphan_record_failed storage_path=%s reason=%s",
            path,
            reason,
            exc_info=True,
        )


def clear_recruit_audio_orphan(db: Client, path: str) -> None:
    """Drop the retry row after the object is gone. Missing row is success."""
    try:
        db.table(ORPHAN_TABLE).delete().eq("storage_path", path).execute()
    except Exception:
        logger.error(
            "recruit_audio_orphan_clear_failed storage_path=%s",
            path,
            exc_info=True,
        )


def _created_at(item: dict) -> datetime | None:
    raw = item.get("created_at")
    if isinstance(raw, datetime):
        moment = raw if raw.tzinfo is not None else raw.replace(tzinfo=UTC)
        return moment.astimezone(UTC)
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _is_folder(item: dict) -> bool:
    """Storage list returns a folder with a null id and a file with a uuid."""
    return not item.get("id")


def _list_prefix(bucket, prefix: str) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    seen: set[str] = set()
    while True:
        page = bucket.list(
            prefix,
            {
                "limit": _LIST_PAGE,
                "offset": offset,
                "sortBy": {"column": "name", "order": "asc"},
            },
        )
        if not page:
            break
        fresh: list[dict] = []
        for item in page:
            name = str(item.get("name") or "")
            if name in seen:
                continue
            seen.add(name)
            fresh.append(item)
        if not fresh:
            # Offset was ignored and this page repeated. Stop rather than loop.
            break
        rows.extend(fresh)
        if len(page) < _LIST_PAGE:
            break
        offset += len(page)
    return rows


def list_recruit_audio_objects(db: Client) -> list[RecruitAudioObject]:
    """Every object in the private recruit-audio bucket.

    The storage API lists one prefix at a time. Recordings live at
    `{user}/{attempt}/{file}`. The caller must be the service role: there is
    no select policy for a candidate, on purpose.
    """
    bucket = db.storage.from_(AUDIO_BUCKET)
    found: list[RecruitAudioObject] = []
    stack: list[tuple[str, int]] = [("", 0)]
    while stack:
        prefix, depth = stack.pop()
        for item in _list_prefix(bucket, prefix):
            name = str(item.get("name") or "")
            if not name or name == _PLACEHOLDER:
                continue
            path = f"{prefix}/{name}" if prefix else name
            if _is_folder(item):
                if depth + 1 > _MAX_LIST_DEPTH:
                    logger.error(
                        "recruit_audio_sweep_failed storage_path=%s error=listing_too_deep",
                        path,
                    )
                    continue
                stack.append((path, depth + 1))
                continue
            found.append(RecruitAudioObject(path=path, created_at=_created_at(item)))
    return found


def in_progress_audio_paths(db: Client) -> set[str]:
    """Paths a queued or running attempt still points at. Service role sees all."""
    paths: set[str] = set()
    start = 0
    page = 1000
    while True:
        rows = (
            db.table("recruit_attempts")
            .select("audio_storage_path")
            .in_("status", list(IN_PROGRESS_ATTEMPT_STATUSES))
            .order("audio_storage_path")
            .range(start, start + page - 1)
            .execute()
            .data
            or []
        )
        for row in rows:
            path = row.get("audio_storage_path")
            if path:
                paths.add(path)
        if len(rows) < page:
            break
        start += page
    return paths


def sweep_stale_recruit_audio(
    db: Client,
    *,
    now: datetime | None = None,
    max_age: timedelta = STALE_AUDIO_AFTER,
) -> list[str]:
    """ERROR, and record, each object older than `max_age` with no live attempt.

    Does not delete. A mis-listed bucket must not become a mass delete. The
    row in `recruit_audio_orphans` is what a retry reads. Returns the stale
    paths. Listing or attempt-lookup failure logs ERROR and returns nothing,
    so a broken read cannot mark every file an orphan.
    """
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    moment = moment.astimezone(UTC)
    cutoff = moment - max_age
    try:
        objects = list_recruit_audio_objects(db)
    except Exception:
        logger.error("recruit_audio_sweep_failed", exc_info=True)
        return []
    try:
        protected = in_progress_audio_paths(db)
    except Exception:
        logger.error("recruit_audio_sweep_failed", exc_info=True)
        return []

    hours = int(max_age.total_seconds() // 3600)
    stale: list[str] = []
    seen: set[str] = set()
    for obj in objects:
        if obj.path in seen:
            continue
        seen.add(obj.path)
        if obj.created_at is not None and obj.created_at >= cutoff:
            continue
        if obj.path in protected:
            continue
        stale.append(obj.path)
        if obj.created_at is None:
            age = "unknown"
        else:
            age = f"{(moment - obj.created_at).total_seconds() / 3600:.1f}"
        logger.error(
            "recruit_audio_orphan storage_path=%s age_hours=%s",
            obj.path,
            age,
        )
        record_recruit_audio_orphan(
            db,
            obj.path,
            reason="stale_unattached",
            error=(
                f"object older than {hours}h and not attached to a queued or running attempt"
            ),
        )
    if stale:
        logger.error("recruit_audio_orphan_count count=%d", len(stale))
    else:
        logger.info("recruit audio sweep found no stale objects")
    return stale


def create_queued_attempt(
    db: Client,
    user_id: str,
    *,
    scenario_id: str,
    question_text: str,
    started_at: datetime,
    filename: str,
    data: bytes,
    criterion_id: str = "c2",
    board_id: str | None = None,
    slot_index: int | None = None,
) -> RecruitAttemptRecord:
    """Upload audio, then insert the queued row and its job.

    Upload first: a row whose file never arrived would sit at queued forever.
    A stored object with no row is cleaned up below.
    """
    attempt_id = str(uuid4())
    path = store_audio(db, user_id, attempt_id, filename, data)
    try:
        db.rpc(
            "submit_queued_recruit_attempt",
            {
                "p_id": attempt_id,
                "p_user_id": user_id,
                "p_scenario_id": scenario_id,
                "p_question_text": question_text,
                "p_started_at": started_at.isoformat(),
                "p_audio_storage_path": path,
                "p_criterion_id": criterion_id,
                "p_board_id": board_id,
                "p_slot_index": slot_index,
            },
        ).execute()
    except Exception:
        delete_audio(db, path)
        raise
    record = get_attempt(db, attempt_id)
    if record is None:
        # The RPC succeeded; RLS should still let the owner read the row. If
        # it does not, return what we know so the client can poll the id.
        return RecruitAttemptRecord(
            id=attempt_id,
            user_id=user_id,
            scenario_id=scenario_id,
            question_text=question_text,
            started_at=started_at,
            status="queued",
            audio_storage_path=path,
            criterion_id=criterion_id,
            board_id=board_id,
            slot_index=slot_index,
        )
    return record


def mark_running(db: Client, attempt_id: str) -> None:
    db.table("recruit_attempts").update({"status": "running"}).eq("id", attempt_id).eq(
        "status", "queued"
    ).execute()


def mark_failed(
    db: Client,
    attempt_id: str,
    error: str,
    *,
    transcript: str | None = None,
) -> None:
    """Terminal critique_failed. Retries are spent, or the audio was empty."""
    patch: dict = {
        "status": "critique_failed",
        "error": error[:2000],
        "audio_storage_path": None,
        "held_candidate_lines": [PER_ANSWER_NOT_ANSWERED],
    }
    if transcript is not None:
        patch["transcript"] = transcript
    db.table("recruit_attempts").update(patch).eq("id", attempt_id).execute()


def list_audio_paths(db: Client) -> list[str]:
    rows = db.table("recruit_attempts").select("audio_storage_path").execute().data or []
    return [row["audio_storage_path"] for row in rows if row.get("audio_storage_path")]
