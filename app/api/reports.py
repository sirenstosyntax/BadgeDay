"""Telling us a question is wrong.

The one route by which a bad question gets caught after it ships. Verification proves a
question is cited; nothing proves it is right, so the candidate reading it is the check.

Kept deliberately small. A report is one enum and one optional sentence, because the
friction of the form is the thing that decides whether a busy candidate mid-session
bothers at all — and a report we never receive is worth nothing.
"""

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.api.deps import CurrentUserDep, DbDep
from app.storage.reports import (
    MAX_DETAIL_CHARS,
    QuestionNotFound,
    QuestionReport,
    ReportReason,
    my_reports,
    report_question,
    withdraw_report,
)

router = APIRouter(tags=["reports"])


class ReportRequest(BaseModel):
    reason: ReportReason = Field(
        description=(
            "not_in_document: the cited section does not say this. answer_wrong: it is in "
            "the document but the marked answer is not right. unclear: ambiguous or badly "
            "worded. other: anything else."
        )
    )
    detail: str | None = Field(
        default=None,
        max_length=MAX_DETAIL_CHARS,
        description=(
            "What you saw, in your own words. Optional, and far more useful than the category."
        ),
    )


@router.post("/questions/{question_id}/report", status_code=status.HTTP_201_CREATED)
def report(
    question_id: str, body: ReportRequest, user: CurrentUserDep, db: DbDep
) -> QuestionReport:
    """Report a question as wrong.

    Reporting the same question twice replaces the earlier report rather than failing. A
    candidate who has changed his mind about what is wrong with a question is giving us
    better information, not committing an error.
    """
    try:
        return report_question(db, user.id, question_id, body.reason, body.detail)
    except QuestionNotFound as exc:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No such question."
        ) from exc


@router.delete("/questions/{question_id}/report", status_code=status.HTTP_204_NO_CONTENT)
def unreport(question_id: str, db: DbDep) -> None:
    """Withdraw a report."""
    if not withdraw_report(db, question_id):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "You have not reported that question.")


@router.get("/reports")
def list_reports(db: DbDep) -> list[QuestionReport]:
    """Every report you have filed, newest first."""
    return my_reports(db)
