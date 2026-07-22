"""What a job actually does.

Two handlers, matching the two job kinds. Ingestion turns an uploaded file into stored
chunks; generation turns those chunks into stored questions. They are separate jobs
rather than one because they fail differently and cost differently: a corrupt PDF fails
in seconds and should not be retried by re-running generation, and a generation run that
dies halfway should not re-analyze a document that was already analyzed fine.

Neither handler catches its own exceptions. Failure handling — retry, backoff, giving up,
marking the document failed — is the runner's job, in one place, so the two handlers can
read as the sequence of steps they are.
"""

import logging
import tempfile
from pathlib import Path

from anthropic import Anthropic
from supabase import Client

from app.config import Settings
from app.generate.generator import generate_for_chunk
from app.ingest.analyzer import get_analyzer
from app.ingest.chunker import chunk_document
from app.storage.content import clear_questions, load_chunks, save_chunks, save_questions
from app.storage.documents import BUCKET, get_document, record_page_count, set_status
from app.worker.jobs import Job, enqueue

logger = logging.getLogger(__name__)


class DocumentGone(Exception):
    """The document was deleted while its job was queued. Not a failure."""


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


HANDLERS = {"ingest": run_ingest, "generate": run_generate}
