"""What a job actually does.

Three handlers, matching the three job kinds. Ingestion turns an uploaded file into
stored chunks; generation turns those chunks into stored questions; a Recruit
critique turns a spoken answer into a verified, candidate-facing set of lines.
They are separate jobs rather than one because they fail differently and cost
differently.

Neither handler catches its own exceptions. Failure handling — retry, backoff,
giving up, marking the document or attempt failed — is the runner's job, in one
place, so the handlers can read as the sequence of steps they are.
"""

import logging
import tempfile
from pathlib import Path

from anthropic import Anthropic
from supabase import Client

from app.api.recruit import C2_SCENARIO_ID, metrics_for_critique
from app.audio.deepgram import DeepgramTranscriber
from app.config import Settings
from app.critique import rubric as rubric_module
from app.critique.cli import QUESTIONS
from app.critique.critiquer import RecruitPersist, critique_answer
from app.generate.generator import generate_for_chunk
from app.ingest.analyzer import get_analyzer
from app.ingest.chunker import chunk_document
from app.storage.content import clear_questions, load_chunks, save_chunks, save_questions
from app.storage.documents import BUCKET, get_document, record_page_count, set_status
from app.storage.recruit import delete_audio, download_audio, get_attempt, mark_running
from app.worker.jobs import Job, enqueue

logger = logging.getLogger(__name__)


class DocumentGone(Exception):
    """The document was deleted while its job was queued. Not a failure."""


class AttemptGone(Exception):
    """The Recruit attempt was deleted while its job was queued. Not a failure."""


class EmptyRecruitAudio(Exception):
    """The recording produced no transcript. Terminal — do not retry."""

    def __init__(self, attempt_id: str, detail: str) -> None:
        super().__init__(detail)
        self.attempt_id = attempt_id
        self.detail = detail


def _document(db: Client, job: Job):
    document = get_document(db, job.document_id)
    if document is None:
        raise DocumentGone(job.document_id)
    return document


def run_ingest(db: Client, settings: Settings, job: Job) -> None:
    """File -> analyzed document -> chunks, then queue generation."""
    document = _document(db, job)
    set_status(db, document.id, "analyzing")

    data = db.storage.from_(BUCKET).download(document.storage_path)

    # The analyzer takes a path because Document Intelligence and the fixture analyzer
    # both do; nothing upstream of here has the file on disk. delete=False plus an
    # explicit unlink, because on some platforms the analyzer cannot reopen a
    # NamedTemporaryFile that is still held open here.
    suffix = Path(document.filename).suffix or ".pdf"
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        handle.write(data)
        handle.close()
        analyzed = get_analyzer(settings).analyze(Path(handle.name))
    finally:
        Path(handle.name).unlink(missing_ok=True)

    set_status(db, document.id, "chunking")
    chunks = chunk_document(analyzed, document.id)
    save_chunks(db, chunks)
    record_page_count(db, document.id, analyzed.page_count)

    logger.info(
        "document %s: %d chunks from %d pages", document.id, len(chunks), analyzed.page_count
    )
    enqueue(db, "generate", document.id)


def run_generate(db: Client, settings: Settings, job: Job) -> None:
    """Chunks -> verified, cited questions."""
    document = _document(db, job)
    set_status(db, document.id, "generating")

    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set; cannot generate.")

    # Only the chunks worth asking about. generate_for_chunk would skip the rest anyway,
    # but filtering here means the skipped ones never become a loop iteration.
    chunks = load_chunks(db, document.id, generatable_only=True)

    # A regeneration must replace, not accumulate: question IDs are minted fresh each run,
    # so without this a second pass leaves the candidate two sets of questions over the
    # same sections and a coverage figure counting both.
    clear_questions(db, document.id)

    client = Anthropic(api_key=settings.anthropic_api_key)
    stored = 0
    for chunk in chunks:
        outcome = generate_for_chunk(chunk, client, settings)
        stored += save_questions(db, outcome.questions)

    logger.info("document %s: %d questions across %d sections", document.id, stored, len(chunks))
    set_status(db, document.id, "ready")


def run_recruit_critique(db: Client, settings: Settings, job: Job) -> None:
    """Audio -> transcript + delivery metrics -> verified critique on the attempt."""
    if not job.attempt_id:
        raise RuntimeError("recruit_critique job has no attempt_id")
    attempt = get_attempt(db, job.attempt_id)
    if attempt is None:
        raise AttemptGone(job.attempt_id)

    mark_running(db, attempt.id)

    if not settings.transcription_configured:
        raise RuntimeError("DEEPGRAM_API_KEY is not set; cannot transcribe.")
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not set; cannot critique.")
    if not attempt.audio_storage_path:
        raise EmptyRecruitAudio(attempt.id, "The recording is no longer available.")

    data = download_audio(db, attempt.audio_storage_path)
    if not data:
        raise EmptyRecruitAudio(attempt.id, "The recording is no longer available.")

    suffix = Path(attempt.audio_storage_path).suffix or ".webm"
    handle = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        handle.write(data)
        handle.close()
        transcript = DeepgramTranscriber(settings).transcribe(Path(handle.name))
    finally:
        Path(handle.name).unlink(missing_ok=True)

    if transcript.is_empty or not transcript.text.strip():
        raise EmptyRecruitAudio(
            attempt.id,
            "There was not enough in that recording to make a transcript.",
        )

    scenario_id = attempt.scenario_id or C2_SCENARIO_ID
    question = attempt.question_text or QUESTIONS[C2_SCENARIO_ID]
    rubric = rubric_module.load(scenario_id)
    audio_path = attempt.audio_storage_path
    outcome = critique_answer(
        rubric=rubric,
        question=question,
        transcript=transcript.text,
        client=Anthropic(api_key=settings.anthropic_api_key),
        settings=settings,
        metrics=metrics_for_critique(transcript),
        persist=RecruitPersist(
            user_id=attempt.user_id,
            scenario_id=scenario_id,
            started_at=attempt.started_at,
            attempt_id=attempt.id,
        ),
    )

    if outcome.critique is None or not outcome.critique.points:
        raise RuntimeError(outcome.failure or "The critique could not be verified.")
    if outcome.failure and outcome.failure.startswith("persist_failed"):
        raise RuntimeError(outcome.failure)

    delete_audio(db, audio_path)
    logger.info("recruit attempt %s: critique stored", attempt.id)


HANDLERS = {
    "ingest": run_ingest,
    "generate": run_generate,
    "recruit_critique": run_recruit_critique,
}
