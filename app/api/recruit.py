"""C2 spoken question: issue the prompt, enqueue the critique, poll the result.

One criterion. The question text is `QUESTIONS["c2"]` from the CLI — not a bank,
not C3. The poll payload is `candidate_lines` only. Score, route, determination,
and clause ids stay on the server via 0010 / 0011; they are not in this payload.

The live worker uses Deepgram only. If the key is unset this returns 503 rather
than enqueueing work that cannot run. `get_transcriber` stays for tests.

Word timestamps from that transcript are run through `metrics.compute` on the
worker and passed into `critique_answer`. Without them the prompt falls back to
"no delivery metrics were computed" and production critiques cannot cite pace,
pauses, or filler.

Audio is transcribed and discarded. `audio_retained` stays false.
"""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.api.deps import CurrentUserDep, DbDep, SettingsDep
from app.audio.metrics import compute
from app.audio.models import Transcript
from app.critique.cli import QUESTIONS
from app.critique.models import Metric
from app.recruit.gate import RecruitAccessDenied, check_recruit_access
from app.storage.recruit import (
    count_attempts,
    create_queued_attempt,
    get_attempt,
    utc_day_start,
)

router = APIRouter(prefix="/recruit", tags=["recruit"])

C2_SCENARIO_ID = "c2"
MAX_AUDIO_BYTES = 10 * 1024 * 1024

AttemptViewStatus = Literal["queued", "running", "completed", "critique_failed"]


class RecruitQuestion(BaseModel):
    scenario_id: str
    question_text: str


class RecruitResult(BaseModel):
    """What the mic screen is allowed to show. No score field on purpose.

    Used for both the 202 enqueue acknowledgement and the poll payload.
    `lines` is empty until the worker finishes.
    """

    attempt_id: str | None
    status: AttemptViewStatus = "queued"
    lines: list[str] = []
    failed: bool = False
    failure: str | None = None


def metrics_for_critique(transcript: Transcript) -> dict[str, Metric]:
    """Map timestamp arithmetic onto the Metric type `critique_answer` already accepts.

    `compute` returns an audio-side dataclass with notes the prompt does not take.
    The four fields here are the ones the prompt and the verification gate cite.
    """
    return {
        metric.name: Metric(
            name=metric.name,
            value=metric.value,
            display=metric.display,
            band=metric.band,
        )
        for metric in compute(transcript).metrics
    }


@router.get("/question")
def issued_question(_user: CurrentUserDep) -> RecruitQuestion:
    return RecruitQuestion(
        scenario_id=C2_SCENARIO_ID,
        question_text=QUESTIONS[C2_SCENARIO_ID],
    )


@router.post("/attempts", status_code=status.HTTP_202_ACCEPTED)
def submit_attempt(
    user: CurrentUserDep,
    db: DbDep,
    settings: SettingsDep,
    audio: UploadFile,
) -> RecruitResult:
    """Accept a recording and return 202. The worker transcribes and critiques.

    Auth is required. The first `recruit_free_sessions` attempts (default 1)
    need no card. Further attempts need a Recruit row on entitlements or this
    answers 402. A UTC daily ceiling (`recruit_daily_attempt_limit`, default
    10) answers 429 even for an entitled candidate.
    """
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

    try:
        check_recruit_access(
            db,
            user.id,
            settings,
            today_count=count_attempts(db, started_on_or_after=utc_day_start()),
            lifetime_count=count_attempts(db),
        )
    except RecruitAccessDenied as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc

    started_at = datetime.now(UTC)
    record = create_queued_attempt(
        db,
        user.id,
        scenario_id=C2_SCENARIO_ID,
        question_text=QUESTIONS[C2_SCENARIO_ID],
        started_at=started_at,
        filename=audio.filename or "answer.webm",
        data=data,
    )
    return RecruitResult(attempt_id=record.id, status="queued")


@router.get("/attempts/{attempt_id}")
def read_attempt(attempt_id: str, db: DbDep) -> RecruitResult:
    """Poll one attempt. 404 for missing and for somebody else's id."""
    record = get_attempt(db, attempt_id)
    if record is None or record.status == "abandoned":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such attempt.")
    if record.status not in ("queued", "running", "completed", "critique_failed"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such attempt.")
    failed = record.status == "critique_failed"
    return RecruitResult(
        attempt_id=record.id,
        status=record.status,
        lines=record.candidate_lines if record.status == "completed" else [],
        failed=failed or bool(record.error and record.status == "completed"),
        failure=record.error if failed else None,
    )
