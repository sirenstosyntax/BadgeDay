"""Practice sessions, answering, review and coverage.

The one thing to hold onto in this module: `QUESTION_COLUMNS` is not a convenience, it is
the list of columns migration 0004 grants a candidate. Selecting `*` here does not return
more data — it fails outright, because the answer columns were revoked. Grading therefore
does not happen in this file at all; it happens inside submit_response(), which is the
only thing in the system that can see a correct answer and a candidate's answer at the
same time.
"""

import logging
from datetime import datetime
from typing import Any, Literal

from postgrest.exceptions import APIError
from pydantic import BaseModel
from supabase import Client

from app.ingest.models import format_section_path

logger = logging.getLogger(__name__)

# Exactly what 0004 grants. Adding a column to `questions` does not add it here, and
# adding it here without the matching grant fails loudly rather than leaking quietly.
QUESTION_COLUMNS = "id,document_id,chunk_id,type,stem,options"

QuestionType = Literal["multiple_choice", "true_false", "short_answer"]


class SessionNotFound(Exception):
    """No such session, or not this candidate's."""


class QuestionNotFound(Exception):
    """No such question, or not from this candidate's documents."""


class AlreadyAnswered(Exception):
    """This session has already recorded an answer to this question."""


class PracticeSession(BaseModel):
    id: str
    user_id: str
    document_id: str | None = None
    created_at: datetime
    completed_at: datetime | None = None


class QuizQuestion(BaseModel):
    """A question as it is served: the ask, and nothing that answers it."""

    id: str
    document_id: str
    chunk_id: str
    type: QuestionType
    stem: str
    options: list[str] | None = None


class Verdict(BaseModel):
    """What comes back once an answer has been committed.

    `is_correct` is None for short answer, which has a model answer to compare against
    rather than a key to match. Auto-grading free text would be a confident lie about
    whether an officer knows their guideline.
    """

    is_correct: bool | None = None
    explanation: str
    correct_index: int | None = None
    correct_answer: bool | None = None
    model_answer: str | None = None
    citation: str


class Coverage(BaseModel):
    document_id: str
    sections_total: int
    sections_exercised: int

    @property
    def percent(self) -> int:
        """0 rather than a division error when a document has nothing worth asking."""
        if not self.sections_total:
            return 0
        return round(100 * self.sections_exercised / self.sections_total)


# --- Sessions ----------------------------------------------------------------


def start_session(db: Client, user_id: str, document_id: str | None = None) -> PracticeSession:
    """Begin practice. A null document_id means a mix across every uploaded document."""
    row = (
        db.table("practice_sessions")
        .insert({"user_id": user_id, "document_id": document_id})
        .execute()
        .data[0]
    )
    return PracticeSession.model_validate(row)


def get_session(db: Client, session_id: str) -> PracticeSession | None:
    rows = db.table("practice_sessions").select("*").eq("id", session_id).limit(1).execute().data
    return PracticeSession.model_validate(rows[0]) if rows else None


def complete_session(db: Client, session_id: str) -> bool:
    rows = (
        db.table("practice_sessions")
        .update({"completed_at": "now()"})
        .eq("id", session_id)
        .execute()
        .data
    )
    return bool(rows)


# --- Asking ------------------------------------------------------------------


def next_question(db: Client, session: PracticeSession) -> QuizQuestion | None:
    """The next question this session has not already asked.

    Served in generation order, which is reading order through the document — a candidate
    working a guideline front to back is doing something coherent, and shuffling would
    take that away for no gain the coverage tracker does not already provide.
    """
    answered = (
        db.table("responses").select("question_id").eq("session_id", session.id).execute().data
    )
    asked = [row["question_id"] for row in answered]

    query = db.table("questions").select(QUESTION_COLUMNS)
    if session.document_id:
        query = query.eq("document_id", session.document_id)
    if asked:
        query = query.not_.in_("id", asked)

    rows = query.order("created_at").limit(1).execute().data
    return QuizQuestion.model_validate(rows[0]) if rows else None


def remaining(db: Client, session: PracticeSession) -> int:
    """How many questions are left in this session's pool."""
    query = db.table("questions").select("id", count="exact")
    if session.document_id:
        query = query.eq("document_id", session.document_id)
    total = query.execute().count or 0

    answered = (
        db.table("responses").select("id", count="exact").eq("session_id", session.id).execute()
    )
    return max(0, total - (answered.count or 0))


# --- Answering ---------------------------------------------------------------


def submit(
    db: Client,
    session_id: str,
    question_id: str,
    selected_index: int | None = None,
    answered_boolean: bool | None = None,
    answered_text: str | None = None,
) -> Verdict:
    """Commit an answer and get the verdict, the explanation and the citation.

    All of it happens in one round trip inside submit_response, because the grade and the
    answer cannot both be visible on this side of the wire. Committing first is also what
    makes the returned explanation safe to hand over: it is released as a consequence of
    answering, not as something available for the asking.
    """
    try:
        rows = (
            db.rpc(
                "submit_response",
                {
                    "p_session_id": session_id,
                    "p_question_id": question_id,
                    "p_selected_index": selected_index,
                    "p_answered_boolean": answered_boolean,
                    "p_answered_text": answered_text,
                },
            )
            .execute()
            .data
        )
    except APIError as exc:
        raise _translate(exc) from exc

    if not rows:
        raise QuestionNotFound(question_id)
    return _verdict(rows[0])


def _translate(exc: APIError) -> Exception:
    """Turn a Postgres error into something the API layer can map to a status code."""
    message = (exc.message or "") + (exc.details or "")
    if exc.code == "23505":
        return AlreadyAnswered(message)
    if "no such session" in message:
        return SessionNotFound(message)
    if "no such question" in message:
        return QuestionNotFound(message)
    return exc


def _verdict(row: dict[str, Any]) -> Verdict:
    citation = format_section_path(row.get("section_path") or [])
    page_start, page_end = row["page_start"], row["page_end"]
    pages = f"p. {page_start}" if page_start == page_end else f"pp. {page_start}–{page_end}"
    title = row.get("section_title")

    if citation and title:
        display = f"{citation} {title}, {pages}"
    elif citation:
        display = f"{citation}, {pages}"
    else:
        display = pages

    return Verdict(
        is_correct=row["is_correct"],
        explanation=row["explanation"],
        correct_index=row["correct_index"],
        correct_answer=row["correct_answer"],
        model_answer=row["model_answer"],
        citation=display,
    )


# --- Review and coverage -----------------------------------------------------


def reviewable(db: Client, session_id: str) -> list[dict]:
    """Everything answered in a session, with its answer and citation.

    Reads answered_questions, which joins through responses — so a question is reviewable
    only once it has been answered.
    """
    return (
        db.table("answered_questions")
        .select("*")
        .eq("session_id", session_id)
        .order("answered_at")
        .execute()
        .data
    )


def coverage(db: Client, document_id: str | None = None) -> list[Coverage]:
    query = db.table("document_coverage").select("*")
    if document_id:
        query = query.eq("document_id", document_id)
    return [Coverage.model_validate(row) for row in query.execute().data]


# --- Saved questions ---------------------------------------------------------


def save_question(db: Client, user_id: str, question_id: str) -> None:
    db.table("saved_questions").upsert({"user_id": user_id, "question_id": question_id}).execute()


def unsave_question(db: Client, question_id: str) -> bool:
    rows = db.table("saved_questions").delete().eq("question_id", question_id).execute().data
    return bool(rows)


def saved_questions(db: Client) -> list[QuizQuestion]:
    saved = db.table("saved_questions").select("question_id").execute().data
    ids = [row["question_id"] for row in saved]
    if not ids:
        return []
    rows = db.table("questions").select(QUESTION_COLUMNS).in_("id", ids).execute().data
    return [QuizQuestion.model_validate(row) for row in rows]
