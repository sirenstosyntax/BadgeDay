"""Recruit boards: start, resume, abandon, C1 complete.

Slots live on the row but are not granted to the candidate. The API only
ever returns the current question, then the released notes at the end.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel
from supabase import Client

from app.recruit.bank import DrawnBoard
from app.storage.recruit import RecruitAttemptRecord, utc_day_start

BoardStatus = Literal["in_progress", "scoring", "completed", "abandoned"]


class BoardSlot(BaseModel):
    scenario_id: str
    question_text: str
    family: str
    criterion_id: str
    draw_group: str = ""
    attempt_id: str | None = None


class RecruitBoardRecord(BaseModel):
    id: str
    user_id: str
    started_at: datetime
    completed_at: datetime | None = None
    abandoned_at: datetime | None = None
    status: BoardStatus
    current_index: int
    current_question_text: str
    current_scenario_id: str
    current_criterion_id: str
    current_family: str
    issued_families: list[str] = []
    issued_scenario_ids: list[str] = []
    current_attempt_id: str | None = None
    notes_released: bool = False
    c1_candidate_lines: list[str] = []
    slots: list[BoardSlot] = []


def _lines(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(line) for line in value]


def _slots_payload(drawn: DrawnBoard) -> list[dict]:
    return [
        {
            "scenario_id": slot.scenario_id,
            "question_text": slot.question_text,
            "family": slot.family,
            "criterion_id": slot.criterion_id,
            "draw_group": slot.draw_group,
        }
        for slot in drawn.slots
    ]


def _parse_slots(raw: object) -> list[BoardSlot]:
    if not isinstance(raw, list):
        return []
    return [BoardSlot.model_validate(item) for item in raw]


def _row_to_board(row: dict) -> RecruitBoardRecord:
    lines = _lines(row.get("c1_candidate_lines"))
    families = row.get("issued_families") or []
    if not isinstance(families, list):
        families = []
    ids = row.get("issued_scenario_ids") or []
    if not isinstance(ids, list):
        ids = []
    row = {
        **row,
        "c1_candidate_lines": lines,
        "issued_families": [str(item) for item in families if item],
        "issued_scenario_ids": [str(item) for item in ids if item],
        "slots": _parse_slots(row.get("slots")),
    }
    return RecruitBoardRecord.model_validate(row)


def get_open_board(db: Client) -> RecruitBoardRecord | None:
    """The candidate's in-progress or scoring board. RLS scopes the table."""
    rows = (
        db.table("recruit_boards")
        .select(
            "id,user_id,started_at,completed_at,abandoned_at,status,"
            "current_index,current_question_text,current_scenario_id,"
            "current_criterion_id,current_family,issued_families,issued_scenario_ids,"
            "current_attempt_id,"
            "notes_released,c1_candidate_lines"
        )
        .in_("status", ["in_progress", "scoring"])
        .order("started_at", desc=True)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        return None
    return _row_to_board(rows[0])


def get_board(db: Client, board_id: str) -> RecruitBoardRecord | None:
    rows = (
        db.table("recruit_boards")
        .select(
            "id,user_id,started_at,completed_at,abandoned_at,status,"
            "current_index,current_question_text,current_scenario_id,"
            "current_criterion_id,current_family,issued_families,issued_scenario_ids,"
            "current_attempt_id,"
            "notes_released,c1_candidate_lines"
        )
        .eq("id", board_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        return None
    return _row_to_board(rows[0])


def get_board_for_worker(db: Client, board_id: str) -> RecruitBoardRecord | None:
    """Service-role read, including slots (upcoming text stays off the user grant)."""
    rows = (
        db.table("recruit_boards")
        .select(
            "id,user_id,started_at,completed_at,abandoned_at,status,slots,"
            "current_index,current_question_text,current_scenario_id,"
            "current_criterion_id,current_family,issued_families,issued_scenario_ids,"
            "current_attempt_id,"
            "notes_released,c1_candidate_lines"
        )
        .eq("id", board_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        return None
    return _row_to_board(rows[0])


def start_board(
    db: Client,
    user_id: str,
    drawn: DrawnBoard,
    *,
    started_at: datetime,
) -> RecruitBoardRecord:
    board_id = str(uuid4())
    slots = _slots_payload(drawn)
    db.rpc(
        "start_recruit_board",
        {
            "p_id": board_id,
            "p_user_id": user_id,
            "p_started_at": started_at.isoformat(),
            "p_slots": slots,
        },
    ).execute()
    first = drawn.slots[0]
    record = get_board(db, board_id)
    if record is not None:
        return record
    return RecruitBoardRecord(
        id=board_id,
        user_id=user_id,
        started_at=started_at,
        status="in_progress",
        current_index=0,
        current_question_text=first.question_text,
        current_scenario_id=first.scenario_id,
        current_criterion_id=first.criterion_id,
        current_family=first.family,
        slots=[BoardSlot.model_validate(item) for item in slots],
    )


def abandon_board(db: Client, board_id: str) -> None:
    db.rpc("abandon_recruit_board", {"p_board_id": board_id}).execute()


def complete_board_c1(
    db: Client,
    board_id: str,
    *,
    outcome: str,
    points: list[dict],
    candidate_lines: list[str],
    internal_score: int | None = None,
    route: str = "n/a",
    determination: str = "",
    deciding_clause_id: str | None = None,
) -> None:
    db.rpc(
        "complete_recruit_board",
        {
            "p_board_id": board_id,
            "p_c1_outcome": outcome,
            "p_c1_points": points,
            "p_c1_candidate_lines": candidate_lines,
            "p_c1_internal_score": internal_score,
            "p_c1_route": route,
            "p_c1_determination": determination,
            "p_c1_deciding_clause_id": deciding_clause_id,
        },
    ).execute()


def count_boards_started(db: Client, *, started_on_or_after: datetime | None = None) -> int:
    """Daily ceiling: every started board counts, including abandoned."""
    query = db.table("recruit_boards").select("id")
    if started_on_or_after is not None:
        query = query.gte("started_at", started_on_or_after.isoformat())
    rows = query.execute().data or []
    return len(rows)


def notes_were_released(status: str, notes_released: object, lines: object) -> bool:
    if status != "completed":
        return False
    if notes_released is not True:
        return False
    return any(str(line).strip() for line in _lines(lines))


def count_completed_boards(db: Client, *, started_on_or_after: datetime | None = None) -> int:
    """Free session: a complete board with released notes."""
    query = (
        db.table("recruit_boards")
        .select("id,status,notes_released,c1_candidate_lines")
        .eq("status", "completed")
    )
    if started_on_or_after is not None:
        query = query.gte("started_at", started_on_or_after.isoformat())
    rows = query.execute().data or []
    return sum(
        1
        for row in rows
        if notes_were_released(
            row.get("status") or "",
            row.get("notes_released"),
            row.get("c1_candidate_lines"),
        )
    )


def issued_scenario_ids(db: Client) -> list[str]:
    """Every prompt already issued — attempts and board slots. RLS scopes both."""
    seen: list[str] = []
    found: set[str] = set()
    attempt_rows = db.table("recruit_attempts").select("scenario_id").execute().data or []
    for row in attempt_rows:
        sid = row.get("scenario_id")
        if sid and sid not in found:
            found.add(sid)
            seen.append(sid)
    board_rows = (
        db.table("recruit_boards").select("issued_scenario_ids").execute().data or []
    )
    for row in board_rows:
        raw = row.get("issued_scenario_ids") or []
        if not isinstance(raw, list):
            continue
        for sid in raw:
            if sid and sid not in found:
                found.add(sid)
                seen.append(sid)
    return seen


def issued_scenario_ids_for_worker(db: Client, user_id: str) -> list[str]:
    """Service-role: attempts plus every board slot, including un-answered ones."""
    seen: list[str] = []
    found: set[str] = set()
    attempt_rows = (
        db.table("recruit_attempts").select("scenario_id").eq("user_id", user_id).execute().data
        or []
    )
    for row in attempt_rows:
        sid = row.get("scenario_id")
        if sid and sid not in found:
            found.add(sid)
            seen.append(sid)
    board_rows = (
        db.table("recruit_boards").select("slots").eq("user_id", user_id).execute().data or []
    )
    for row in board_rows:
        for slot in _parse_slots(row.get("slots")):
            if slot.scenario_id and slot.scenario_id not in found:
                found.add(slot.scenario_id)
                seen.append(slot.scenario_id)
    return seen


def recent_board_families(db: Client, *, limit: int = 8) -> list[str]:
    """Families on the last `limit` started boards (any status). No question text."""
    rows = (
        db.table("recruit_boards")
        .select("issued_families,started_at")
        .order("started_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    families: list[str] = []
    for row in rows:
        raw = row.get("issued_families") or []
        if not isinstance(raw, list):
            continue
        families.extend(str(item) for item in raw if item)
    return families


def recent_families_from_attempts(db: Client, *, board_limit: int = 8) -> list[str]:
    """Families already issued, newest boards first, capped at `board_limit` boards.

    Built from attempt rows the candidate can read (scenario_id FAMILY.n).
    """
    rows = (
        db.table("recruit_attempts")
        .select("scenario_id,started_at,board_id")
        .order("started_at", desc=True)
        .execute()
        .data
        or []
    )
    families: list[str] = []
    seen_boards: list[str] = []
    found_families: set[str] = set()
    for row in rows:
        board_id = row.get("board_id") or ""
        if board_id:
            if board_id not in seen_boards:
                if len(seen_boards) >= board_limit:
                    continue
                seen_boards.append(board_id)
        sid = row.get("scenario_id") or ""
        family = sid.rsplit(".", 1)[0] if "." in sid else ""
        if family and family not in found_families:
            found_families.add(family)
            families.append(family)
    return families


def board_attempts(db: Client, board_id: str) -> list[RecruitAttemptRecord]:
    rows = (
        db.table("recruit_attempts")
        .select(
            "id,user_id,scenario_id,question_text,started_at,completed_at,"
            "status,audio_storage_path,error,candidate_lines,"
            "audio_retained,criterion_id,board_id,slot_index"
        )
        .eq("board_id", board_id)
        .order("slot_index")
        .execute()
        .data
        or []
    )
    out: list[RecruitAttemptRecord] = []
    for row in rows:
        lines = row.get("candidate_lines") or []
        if not isinstance(lines, list):
            lines = []
        row["candidate_lines"] = [str(line) for line in lines]
        out.append(RecruitAttemptRecord.model_validate(row))
    return out


def worker_board_attempts(db: Client, board_id: str) -> list[dict]:
    """Service-role: transcripts + held lines for C1 and release."""
    return (
        db.table("recruit_attempts")
        .select(
            "id,slot_index,scenario_id,question_text,status,transcript,"
            "held_candidate_lines,candidate_lines,criterion_id"
        )
        .eq("board_id", board_id)
        .order("slot_index")
        .execute()
        .data
        or []
    )


def enqueue_c1(db: Client, board_id: str) -> None:
    db.table("jobs").insert({"kind": "recruit_c1", "board_id": board_id}).execute()


_TERMINAL_SLOT = {"completed", "critique_failed", "abandoned"}


def notes_cannot_finish(board_status: str, rows: list[dict]) -> bool:
    """True when a terminal slot has no spoken material, so C1 cannot run.

    Spec default (BD-R-003 §6 / §8.4): no C1 until five transcripts exist
    or the board is abandoned. A critique_failed slot with an empty
    transcript leaves the board in scoring forever unless the candidate
    leaves.
    """
    if board_status not in ("in_progress", "scoring"):
        return False
    empty_failed = any(
        (row.get("status") or "") == "critique_failed"
        and not str(row.get("transcript") or "").strip()
        for row in rows
    )
    if empty_failed:
        return True
    if board_status != "scoring" or len(rows) < 5:
        return False
    if any((row.get("status") or "") not in _TERMINAL_SLOT for row in rows):
        return False
    spoken = sum(1 for row in rows if str(row.get("transcript") or "").strip())
    return spoken < 5


def board_attempt_note_rows(db: Client, board_id: str) -> list[dict]:
    """Status + transcript emptiness for the notes-blocked check. No prose."""
    return (
        db.table("recruit_attempts")
        .select("status,transcript,error")
        .eq("board_id", board_id)
        .execute()
        .data
        or []
    )


def notes_blocked_for_board(db: Client, board: RecruitBoardRecord) -> bool:
    if board.status not in ("in_progress", "scoring"):
        return False
    return notes_cannot_finish(board.status, board_attempt_note_rows(db, board.id))


# Silence unused import warning if utc_day_start is only used by callers.
_ = utc_day_start
