"""Persisting what the pipeline produces, and reading it back as the same types.

The domain models and the tables disagree about names in two places — a chunk's
`chunk_id` is a row's `id`, a chunk's `text` is a row's `body` — and the translation
lives here rather than in either of them. `Chunk` is shared with the CLI and with the
citation logic, and reshaping it to match Postgres would couple the pipeline to the
schema for the convenience of one insert.

`is_generatable` is the interesting column. It is not a field on `Chunk`; it is a
judgement made by app/generate/verify.py about whether a chunk holds anything worth
asking about. It is written here because the coverage view divides by it: a container
heading that can never yield a question must stay out of the denominator, or coverage
never reaches 100% and reads as broken to a candidate who has in fact covered
everything.

Everything in this module is called by the worker under the service role. Chunks and
questions have no client insert policy at all — a candidate must not author the
questions they are then graded on — so none of this is reachable from a request.
"""

import logging

from supabase import Client

from app.generate.models import Citation, Question
from app.generate.verify import is_generatable
from app.ingest.models import Chunk

logger = logging.getLogger(__name__)


def _chunk_row(chunk: Chunk) -> dict:
    return {
        "id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "ordinal": chunk.ordinal,
        "kind": chunk.kind,
        "section_path": list(chunk.section_path),
        "section_title": chunk.section_title,
        "page_start": chunk.page_start,
        "page_end": chunk.page_end,
        "body": chunk.text,
        "is_generatable": is_generatable(chunk),
    }


def _chunk_from_row(row: dict) -> Chunk:
    return Chunk(
        chunk_id=row["id"],
        document_id=row["document_id"],
        ordinal=row["ordinal"],
        kind=row["kind"],
        section_path=row.get("section_path") or [],
        section_title=row.get("section_title"),
        page_start=row["page_start"],
        page_end=row["page_end"],
        text=row["body"],
    )


def save_chunks(db: Client, chunks: list[Chunk]) -> int:
    """Write a document's chunks, replacing any previous ingestion of it.

    Upsert rather than insert because chunk IDs are uuid5 over (document_id, ordinal) and
    therefore stable across re-ingestion — which is the entire reason they are minted that
    way. Re-running ingestion on the same document rewrites the same rows and leaves every
    citation pointing where it already pointed.
    """
    if not chunks:
        return 0
    rows = [_chunk_row(chunk) for chunk in chunks]
    db.table("chunks").upsert(rows).execute()
    return len(rows)


def load_chunks(db: Client, document_id: str, generatable_only: bool = False) -> list[Chunk]:
    """Read a document's chunks back in reading order."""
    query = db.table("chunks").select("*").eq("document_id", document_id)
    if generatable_only:
        query = query.eq("is_generatable", True)
    rows = query.order("ordinal").execute().data
    return [_chunk_from_row(row) for row in rows]


def _question_row(question: Question) -> dict:
    citation: Citation = question.citation
    return {
        "id": question.question_id,
        "document_id": citation.document_id,
        "chunk_id": citation.chunk_id,
        "type": question.type,
        "stem": question.stem,
        "explanation": question.explanation,
        "options": question.options,
        "correct_index": question.correct_index,
        "correct_answer": question.correct_answer,
        "model_answer": question.model_answer,
    }


def save_questions(db: Client, questions: list[Question]) -> int:
    """Write verified questions.

    No citation columns are written beyond `chunk_id`. The citation *is* the foreign key:
    section and page are read through the chunk, so a displayed citation cannot drift from
    the chunk it points at. Nothing here writes `source_quote` either — the quote proved
    the grounding, was checked, and was discarded, because storing verbatim source text is
    what the copyright constraint forbids.
    """
    if not questions:
        return 0
    db.table("questions").insert([_question_row(q) for q in questions]).execute()
    return len(questions)


def clear_questions(db: Client, document_id: str) -> None:
    """Drop a document's questions before regenerating them.

    Generation is not idempotent — question IDs are uuid4, minted fresh at verification —
    so a second generation run would otherwise stack a new set on top of the old one, and
    the candidate's coverage would count sections they had already been asked about twice.
    """
    db.table("questions").delete().eq("document_id", document_id).execute()
