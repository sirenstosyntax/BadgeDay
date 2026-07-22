"""The quiz loop: start a session, answer questions, review with citations, track coverage.

Nothing here grades anything. An answer goes to submit_response() in the database and the
verdict comes back, because after migration 0004 the answer columns are not readable by
the candidate's token — which is what this API holds. That is the point: the code path
that serves a question cannot see its answer even by mistake.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.deps import CurrentUserDep, DbDep
from app.storage.practice import (
    AlreadyAnswered,
    PracticeSession,
    QuestionNotFound,
    QuizQuestion,
    SessionNotFound,
    Verdict,
    complete_session,
    coverage,
    get_session,
    next_question,
    remaining,
    reviewable,
    save_question,
    saved_questions,
    start_session,
    submit,
    unsave_question,
)

router = APIRouter(tags=["practice"])


class StartSession(BaseModel):
    document_id: str | None = None


class Answer(BaseModel):
    """One answer. Which field is filled depends on the question type."""

    question_id: str
    selected_index: int | None = None
    answered_boolean: bool | None = None
    answered_text: str | None = None


class NextQuestion(BaseModel):
    question: QuizQuestion | None
    remaining: int


class CoverageReport(BaseModel):
    document_id: str
    sections_total: int
    sections_exercised: int
    percent: int


def _session(db: DbDep, session_id: str) -> PracticeSession:
    session = get_session(db, session_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such practice session.")
    return session


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
def begin(user: CurrentUserDep, db: DbDep, body: StartSession | None = None) -> PracticeSession:
    """Start practising, either one document or a mix across all of them."""
    document_id = body.document_id if body else None
    return start_session(db, user.id, document_id)


@router.get("/sessions/{session_id}")
def read_session(db: DbDep, session_id: str) -> PracticeSession:
    return _session(db, session_id)


@router.get("/sessions/{session_id}/next")
def ask(db: DbDep, session_id: str) -> NextQuestion:
    """The next unanswered question, or null when the session has run out."""
    session = _session(db, session_id)
    return NextQuestion(question=next_question(db, session), remaining=remaining(db, session))


@router.post("/sessions/{session_id}/responses")
def answer(db: DbDep, session_id: str, body: Answer) -> Verdict:
    """Commit an answer and get back the verdict, the explanation and the citation."""
    try:
        return submit(
            db,
            session_id,
            body.question_id,
            selected_index=body.selected_index,
            answered_boolean=body.answered_boolean,
            answered_text=body.answered_text,
        )
    except AlreadyAnswered as exc:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "That question has already been answered in this session."
        ) from exc
    except SessionNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such practice session.") from exc
    except QuestionNotFound as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No such question.") from exc


@router.get("/sessions/{session_id}/review")
def review(db: DbDep, session_id: str) -> list[dict]:
    """Everything answered in this session, with the source section for each."""
    _session(db, session_id)
    return reviewable(db, session_id)


@router.post("/sessions/{session_id}/complete")
def finish(db: DbDep, session_id: str) -> PracticeSession:
    _session(db, session_id)
    complete_session(db, session_id)
    return _session(db, session_id)


@router.get("/coverage")
def read_coverage(db: DbDep, document_id: str | None = None) -> list[CoverageReport]:
    """How much of each document has been exercised."""
    return [
        CoverageReport(
            document_id=record.document_id,
            sections_total=record.sections_total,
            sections_exercised=record.sections_exercised,
            percent=record.percent,
        )
        for record in coverage(db, document_id)
    ]


@router.get("/saved")
def list_saved(db: DbDep) -> list[QuizQuestion]:
    return saved_questions(db)


@router.put("/saved/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def save(user: CurrentUserDep, db: DbDep, question_id: str) -> None:
    """Flag a question to come back to. Idempotent — saving twice is saving once."""
    save_question(db, user.id, question_id)


@router.delete("/saved/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def unsave(db: DbDep, question_id: str) -> None:
    if not unsave_question(db, question_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "That question is not saved.")
