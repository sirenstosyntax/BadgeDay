"""Five-question Recruit board: start, current Q only, submit, poll, abandon.

Notes stay withheld until the board is complete. Then per-answer notes and
the C1 whole-board block land together. Free = one complete board with
released notes. Daily ceiling = boards started (UTC). Promote entitlement
does not open this gate.

Legacy GET /question and POST /attempts wrap the board: they resume or start
one, return only the current prompt, and never release notes mid-board.
"""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from supabase import Client

from app.api.deps import CurrentUser, CurrentUserDep, DbDep, SettingsDep
from app.audio.metrics import compute
from app.audio.models import Transcript
from app.config import Settings
from app.critique.models import Metric
from app.recruit.bank import (
    C2_SCENARIO_ID,  # noqa: F401 — re-exported for tests and the worker
    DrawnBoard,
    ExhaustedIssue,
    draw_board,
    draw_is_c2_only,
)
from app.recruit.copy import BOARD_FRAMING, NOTES_BLOCKED, SOFT_TIMER_SECONDS
from app.recruit.gate import RecruitAccessDenied, check_recruit_access
from app.storage.boards import (
    RecruitBoardRecord,
    abandon_board,
    count_boards_started,
    count_completed_boards,
    get_board,
    get_open_board,
    issued_scenario_ids,
    notes_blocked_for_board,
    recent_board_families,
    start_board,
)
from app.storage.recruit import (
    attempted_scenario_ids,
    completed_scenario_ids,
    create_queued_attempt,
    get_attempt,
    utc_day_start,
)

router = APIRouter(prefix="/recruit", tags=["recruit"])

MAX_AUDIO_BYTES = 10 * 1024 * 1024

AttemptViewStatus = Literal["queued", "running", "completed", "critique_failed"]
BoardViewStatus = Literal["in_progress", "scoring", "completed", "abandoned", "exhausted"]


class RecruitQuestionAvailable(BaseModel):
    state: Literal["available"] = "available"
    scenario_id: str
    question_text: str
    board_id: str | None = None
    question_index: int = Field(default=1, ge=1, le=5)
    board_size: int = 5
    soft_timer_seconds: int = SOFT_TIMER_SECONDS


class RecruitQuestionExhausted(BaseModel):
    """Milestone payload. HTTP 200 — the bank is empty or fully seen, not missing."""

    state: Literal["exhausted"] = "exhausted"
    answered_count: int = Field(ge=0)
    bank_size: int = Field(ge=0)
    next_eligible_at: datetime | None = None


RecruitQuestion = RecruitQuestionAvailable | RecruitQuestionExhausted


class BoardAnswerNotes(BaseModel):
    question_index: int
    question_text: str
    lines: list[str]


class RecruitBoardView(BaseModel):
    """Candidate-facing board. Upcoming prompts and notes stay off until the end."""

    board_id: str
    status: BoardViewStatus
    question_index: int = Field(ge=1, le=5)
    board_size: int = 5
    question_text: str | None = None
    scenario_id: str | None = None
    attempt_id: str | None = None
    soft_timer_seconds: int = SOFT_TIMER_SECONDS
    framing: str | None = None
    answers: list[BoardAnswerNotes] = []
    c1_lines: list[str] = []
    notes_blocked: bool = False
    notes_blocked_detail: str | None = None


class RecruitResult(BaseModel):
    """What the mic screen is allowed to show. No score field on purpose.

    Used for both the 202 enqueue acknowledgement and the poll payload.
    `lines` is empty until the board releases notes.
    """

    attempt_id: str | None
    status: AttemptViewStatus = "queued"
    lines: list[str] = []
    failed: bool = False
    failure: str | None = None
    board_id: str | None = None
    question_index: int | None = None


def metrics_for_critique(transcript: Transcript) -> dict[str, Metric]:
    """Map timestamp arithmetic onto the Metric type `critique_answer` already accepts."""
    return {
        metric.name: Metric(
            name=metric.name,
            value=metric.value,
            display=metric.display,
            band=metric.band,
        )
        for metric in compute(transcript).metrics
    }


def _enforce_recruit_access(user: CurrentUser, db: Client, settings: Settings) -> None:
    """Same gate for starting a board and submitting into one.

    Lifetime counts completed boards with released notes. Daily counts
    boards started today. Starting a board the submit would 402 is the
    failure mode this exists to close.
    """
    try:
        check_recruit_access(
            db,
            user.id,
            settings,
            today_count=count_boards_started(db, started_on_or_after=utc_day_start()),
            lifetime_count=count_completed_boards(db),
        )
    except RecruitAccessDenied as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc


def _seen_ids(db: Client) -> list[str]:
    # Board slots count as seen on start, even with no attempt row yet.
    board_ids = issued_scenario_ids(db)
    attempt_ids = attempted_scenario_ids(db)
    seen: list[str] = []
    found: set[str] = set()
    for sid in [*board_ids, *attempt_ids]:
        if sid and sid not in found:
            found.add(sid)
            seen.append(sid)
    return seen


def _draw_or_exhausted(db: Client) -> DrawnBoard | ExhaustedIssue:
    decision = draw_board(
        _seen_ids(db),
        recent_families=recent_board_families(db),
        completed_scenario_ids=completed_scenario_ids(db),
    )
    if isinstance(decision, DrawnBoard) and draw_is_c2_only(decision):
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "The board draw produced five C2-only questions.",
        )
    return decision


def _start_new_board(user: CurrentUser, db: Client, settings: Settings) -> RecruitBoardRecord:
    _enforce_recruit_access(user, db, settings)
    decision = _draw_or_exhausted(db)
    if isinstance(decision, ExhaustedIssue):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "There is no new board to start right now.",
        )
    return start_board(db, user.id, decision, started_at=datetime.now(UTC))


def _resume_or_start(user: CurrentUser, db: Client, settings: Settings) -> RecruitBoardRecord:
    open_board = get_open_board(db)
    if open_board is not None:
        return open_board
    return _start_new_board(user, db, settings)


def _question_from_board(board: RecruitBoardRecord) -> RecruitQuestionAvailable:
    return RecruitQuestionAvailable(
        scenario_id=board.current_scenario_id,
        question_text=board.current_question_text,
        board_id=board.id,
        question_index=board.current_index + 1,
    )


def _released_answers(db: Client, board: RecruitBoardRecord) -> list[BoardAnswerNotes]:
    if not board.notes_released:
        return []
    from app.storage.boards import board_attempts

    notes: list[BoardAnswerNotes] = []
    for record in board_attempts(db, board.id):
        index = (record.slot_index or 0) + 1
        notes.append(
            BoardAnswerNotes(
                question_index=index,
                question_text=record.question_text,
                lines=record.candidate_lines,
            )
        )
    notes.sort(key=lambda item: item.question_index)
    return notes


def _board_view(db: Client, board: RecruitBoardRecord) -> RecruitBoardView:
    released = board.status == "completed" and board.notes_released
    in_progress = board.status == "in_progress"
    blocked = notes_blocked_for_board(db, board)
    return RecruitBoardView(
        board_id=board.id,
        status=board.status,
        question_index=board.current_index + 1,
        question_text=board.current_question_text if in_progress else None,
        scenario_id=board.current_scenario_id if in_progress else None,
        attempt_id=board.current_attempt_id if board.status == "scoring" else None,
        framing=BOARD_FRAMING if released else None,
        answers=_released_answers(db, board) if released else [],
        c1_lines=board.c1_candidate_lines if released else [],
        notes_blocked=blocked,
        notes_blocked_detail=NOTES_BLOCKED if blocked else None,
    )


def _read_audio(audio: UploadFile, settings: Settings) -> bytes:
    if not settings.transcription_configured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Transcription is not configured.",
        )
    if not settings.anthropic_api_key:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Critique is not configured.",
        )
    data = audio.file.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "That recording is larger than 10 MB.",
        )
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That recording is empty.")
    return data


def _submit_current_slot(
    user: CurrentUser,
    db: Client,
    settings: Settings,
    audio: UploadFile,
    board: RecruitBoardRecord,
) -> RecruitResult:
    if board.status != "in_progress":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "This board is not waiting for an answer.",
        )
    data = _read_audio(audio, settings)
    started_at = datetime.now(UTC)
    record = create_queued_attempt(
        db,
        user.id,
        scenario_id=board.current_scenario_id,
        question_text=board.current_question_text,
        started_at=started_at,
        filename=audio.filename or "answer.webm",
        data=data,
        criterion_id=board.current_criterion_id,
        board_id=board.id,
        slot_index=board.current_index,
    )
    return RecruitResult(
        attempt_id=record.id,
        status="queued",
        board_id=board.id,
        question_index=board.current_index + 1,
    )


@router.post("/boards", status_code=status.HTTP_201_CREATED)
def create_board(
    user: CurrentUserDep, db: DbDep, settings: SettingsDep
) -> RecruitBoardView:
    """Start a five-question board. Returns Q1 only."""
    open_board = get_open_board(db)
    if open_board is not None:
        return _board_view(db, open_board)
    board = _start_new_board(user, db, settings)
    return _board_view(db, board)


@router.get("/boards/{board_id}")
def read_board(board_id: str, db: DbDep) -> RecruitBoardView:
    board = get_board(db, board_id)
    if board is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such board.")
    return _board_view(db, board)


@router.post("/boards/{board_id}/answers", status_code=status.HTTP_202_ACCEPTED)
def submit_board_answer(
    board_id: str,
    user: CurrentUserDep,
    db: DbDep,
    settings: SettingsDep,
    audio: UploadFile,
) -> RecruitResult:
    board = get_board(db, board_id)
    if board is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such board.")
    if board.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such board.")
    return _submit_current_slot(user, db, settings, audio, board)


@router.post("/boards/{board_id}/abandon")
def abandon(board_id: str, user: CurrentUserDep, db: DbDep) -> RecruitBoardView:
    board = get_board(db, board_id)
    if board is None or board.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such board.")
    if board.status == "completed":
        # Leave during holding must not wipe a board that just completed.
        return _board_view(db, board)
    if board.status in ("in_progress", "scoring"):
        try:
            abandon_board(db, board_id)
        except Exception:
            # Worker released notes between the read and the RPC.
            board = get_board(db, board_id) or board
            if board.status == "completed":
                return _board_view(db, board)
            raise
        board = get_board(db, board_id) or board
        if board.status == "completed":
            return _board_view(db, board)
    view = _board_view(db, board)
    if view.status == "completed":
        return view
    return view.model_copy(
        update={
            "status": "abandoned",
            "framing": None,
            "answers": [],
            "c1_lines": [],
            "question_text": None,
            "notes_blocked": False,
            "notes_blocked_detail": None,
        }
    )


@router.get("/question")
def issued_question(user: CurrentUserDep, db: DbDep, settings: SettingsDep) -> RecruitQuestion:
    """Current board question, or start a board. Never previews Q2–Q5.

    Exhaustion is a 200 milestone. Auth is required. The first complete
    board with released notes is free; further starts need Recruit
    entitlement. Same check as submit.
    """
    open_board = get_open_board(db)
    if open_board is not None:
        if open_board.status == "scoring":
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "This board is finished recording. Notes are still being prepared.",
            )
        return _question_from_board(open_board)
    try:
        board = _start_new_board(user, db, settings)
    except HTTPException as exc:
        if exc.status_code == 409:
            decision = _draw_or_exhausted(db)
            if isinstance(decision, ExhaustedIssue):
                return RecruitQuestionExhausted(
                    answered_count=decision.answered_count,
                    bank_size=decision.bank_size,
                    next_eligible_at=decision.next_eligible_at,
                )
        raise
    return _question_from_board(board)


@router.post("/attempts", status_code=status.HTTP_202_ACCEPTED)
def submit_attempt(
    user: CurrentUserDep,
    db: DbDep,
    settings: SettingsDep,
    audio: UploadFile,
) -> RecruitResult:
    """Submit audio for the current board slot. Wraps the five-question board."""
    board = _resume_or_start(user, db, settings)
    return _submit_current_slot(user, db, settings, audio, board)


@router.get("/attempts/{attempt_id}")
def read_attempt(attempt_id: str, db: DbDep) -> RecruitResult:
    """Poll one attempt. Lines stay empty until the board releases notes."""
    record = get_attempt(db, attempt_id)
    if record is None or record.status == "abandoned":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such attempt.")
    if record.status not in ("queued", "running", "completed", "critique_failed"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such attempt.")
    failed = record.status == "critique_failed"
    released = False
    if record.board_id:
        board = get_board(db, record.board_id)
        released = bool(board and board.status == "completed" and board.notes_released)
    else:
        released = record.status == "completed"
    lines = record.candidate_lines if released and record.status == "completed" else []
    return RecruitResult(
        attempt_id=record.id,
        status=record.status,
        lines=lines,
        failed=failed or bool(record.error and record.status == "completed"),
        failure=record.error if failed else None,
        board_id=record.board_id,
        question_index=(record.slot_index + 1) if record.slot_index is not None else None,
    )
