"""C2 spoken question: issue the CLI prompt, transcribe, persist a verified critique.

One criterion. The question text is `QUESTIONS["c2"]` from the CLI — not a bank,
not C3. The response is `candidate_lines` only. Score, route, determination, and
clause ids stay on the server via 0010; they are not in this payload.

The live path uses Deepgram only. If the key is unset this returns 503 rather than
critiquing a fixture. `get_transcriber` stays for tests.

Word timestamps from that transcript are run through `metrics.compute` and passed
into `critique_answer`. Without them the prompt falls back to "no delivery metrics
were computed" and production critiques cannot cite pace, pauses, or filler.

No subscription check. This slice is not a Stripe path.
Audio is transcribed and discarded. `audio_retained` stays false.
"""

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from anthropic import Anthropic
from fastapi import APIRouter, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.api.deps import CurrentUserDep, SettingsDep
from app.audio.deepgram import DeepgramTranscriber
from app.audio.metrics import compute
from app.audio.models import Transcript
from app.critique import rubric as rubric_module
from app.critique.cli import QUESTIONS
from app.critique.critiquer import RecruitPersist, critique_answer
from app.critique.models import Metric
from app.critique.render import candidate_lines

router = APIRouter(prefix="/recruit", tags=["recruit"])

C2_SCENARIO_ID = "c2"
MAX_AUDIO_BYTES = 10 * 1024 * 1024


class RecruitQuestion(BaseModel):
    scenario_id: str
    question_text: str


class RecruitResult(BaseModel):
    """What the mic screen is allowed to show. No score field on purpose."""

    attempt_id: str | None
    lines: list[str]
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


@router.post("/attempts", status_code=status.HTTP_201_CREATED)
def submit_attempt(
    user: CurrentUserDep,
    settings: SettingsDep,
    audio: UploadFile,
) -> RecruitResult:
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

    started_at = datetime.now(UTC)
    data = audio.file.read(MAX_AUDIO_BYTES + 1)
    if len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "That recording is larger than 10 MB.",
        )
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "That recording is empty.")

    name = Path(audio.filename or "answer.webm")
    suffix = name.suffix or ".webm"
    stem = name.stem or "answer"
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / f"{stem}{suffix}"
        path.write_bytes(data)
        try:
            transcript = DeepgramTranscriber(settings).transcribe(path)
        except Exception as exc:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                "The recording could not be transcribed.",
            ) from exc

    if transcript.is_empty or not transcript.text.strip():
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "There was not enough in that recording to make a transcript.",
        )

    rubric = rubric_module.load(C2_SCENARIO_ID)
    outcome = critique_answer(
        rubric=rubric,
        question=QUESTIONS[C2_SCENARIO_ID],
        transcript=transcript.text,
        client=Anthropic(api_key=settings.anthropic_api_key),
        settings=settings,
        metrics=metrics_for_critique(transcript),
        persist=RecruitPersist(
            user_id=user.id,
            scenario_id=C2_SCENARIO_ID,
            started_at=started_at,
        ),
    )

    if outcome.critique is None or not outcome.critique.points:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY,
            "The critique could not be verified.",
        )

    return RecruitResult(
        attempt_id=outcome.attempt_id,
        lines=candidate_lines(outcome.critique),
        failed=bool(outcome.failure),
        failure=None,
    )
