"""Recruit attempts: queued row, pollable status, temporary audio.

The request path talks through the candidate's own client. Inserts go through
`submit_queued_recruit_attempt` (migration 0011) so a job is created in the
same transaction and a candidate cannot write a completed row. The worker
uses the service role to mark running / failed and to download audio.
"""

import logging
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel
from supabase import Client

from app.storage.documents import safe_filename

logger = logging.getLogger(__name__)

AUDIO_BUCKET = "recruit-audio"

AttemptStatus = Literal["queued", "running", "completed", "abandoned", "critique_failed"]


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
    audio_retained: bool = False


def utc_day_start(now: datetime | None = None) -> datetime:
    moment = now or datetime.now(UTC)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def count_attempts(db: Client, *, started_on_or_after: datetime | None = None) -> int:
    """How many attempts this candidate already has. RLS scopes the table."""
    query = db.table("recruit_attempts").select("id")
    if started_on_or_after is not None:
        query = query.gte("started_at", started_on_or_after.isoformat())
    rows = query.execute().data or []
    return len(rows)


def get_attempt(db: Client, attempt_id: str) -> RecruitAttemptRecord | None:
    rows = (
        db.table("recruit_attempts")
        .select(
            "id,user_id,scenario_id,question_text,started_at,completed_at,"
            "status,audio_storage_path,error,candidate_lines,audio_retained"
        )
        .eq("id", attempt_id)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        return None
    row = rows[0]
    lines = row.get("candidate_lines") or []
    if not isinstance(lines, list):
        lines = []
    row["candidate_lines"] = [str(line) for line in lines]
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
    if not path:
        return
    try:
        db.storage.from_(AUDIO_BUCKET).remove([path])
    except Exception:
        logger.exception("could not delete Recruit audio at %s", path)


def create_queued_attempt(
    db: Client,
    user_id: str,
    *,
    scenario_id: str,
    question_text: str,
    started_at: datetime,
    filename: str,
    data: bytes,
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
    }
    if transcript is not None:
        patch["transcript"] = transcript
    db.table("recruit_attempts").update(patch).eq("id", attempt_id).execute()


def list_audio_paths(db: Client) -> list[str]:
    rows = db.table("recruit_attempts").select("audio_storage_path").execute().data or []
    return [row["audio_storage_path"] for row in rows if row.get("audio_storage_path")]
