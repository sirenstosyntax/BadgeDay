"""Reporting a question as wrong.

The verification gate proves a question is grounded in the section it cites. It cannot
prove the question is any good — a perfectly cited question about a revision date is
perfectly worthless, and a subtly wrong answer is cited just as confidently as a right
one. The candidate reading it is the only party positioned to notice, which makes this
the product's one external check on generation quality.

That framing matters for how forgiving the write is. A candidate who has spotted a bad
question and bothered to say so has done us a favour at some cost to his own study time;
the interaction should not then argue with him about whether he already reported it.
Re-reporting a question updates what he said rather than failing.
"""

import logging
from dataclasses import dataclass
from typing import Literal

from postgrest.exceptions import APIError
from supabase import Client

logger = logging.getLogger(__name__)

ReportReason = Literal["not_in_document", "answer_wrong", "unclear", "other"]

MAX_DETAIL_CHARS = 2000


class QuestionNotFound(Exception):
    """The question does not exist, or is not one this candidate can see."""


@dataclass(frozen=True)
class QuestionReport:
    id: str
    question_id: str
    reason: ReportReason
    detail: str | None
    created_at: str
    resolved_at: str | None


def _row_to_report(row: dict) -> QuestionReport:
    return QuestionReport(
        id=row["id"],
        question_id=row["question_id"],
        reason=row["reason"],
        detail=row.get("detail"),
        created_at=row["created_at"],
        resolved_at=row.get("resolved_at"),
    )


def report_question(
    db: Client,
    user_id: str,
    question_id: str,
    reason: ReportReason,
    detail: str | None = None,
) -> QuestionReport:
    """Record that a candidate believes a question is wrong.

    The question is read first through the candidate's own client. That is not a
    permission check bolted on — it is the permission check, because his policies only
    return questions belonging to his own documents. A question he cannot read is one he
    cannot report, and the handler never has to remember to filter.
    """
    found = db.table("questions").select("id").eq("id", question_id).execute()
    if not found.data:
        raise QuestionNotFound(question_id)

    payload = {
        "question_id": question_id,
        "user_id": user_id,
        "reason": reason,
        "detail": (detail or "").strip()[:MAX_DETAIL_CHARS] or None,
    }

    # on_conflict rather than an insert that fails: a candidate re-reporting a question has
    # changed his mind about it, and telling him "you already said that" is a worse answer
    # than recording what he now thinks.
    response = (
        db.table("question_reports")
        .upsert(payload, on_conflict="question_id,user_id")
        .execute()
    )
    logger.info("question %s reported: %s", question_id, reason)
    return _row_to_report(response.data[0])


def withdraw_report(db: Client, question_id: str) -> bool:
    """Remove a candidate's report. Returns False if there was nothing to remove."""
    response = (
        db.table("question_reports").delete().eq("question_id", question_id).execute()
    )
    return bool(response.data)


def my_reports(db: Client) -> list[QuestionReport]:
    """Every report this candidate has filed, newest first."""
    response = (
        db.table("question_reports")
        .select("*")
        .order("created_at", desc=True)
        .execute()
    )
    return [_row_to_report(row) for row in response.data]


# --- operational: read with the service role only ----------------------------


def open_reports(db: Client, limit: int = 100) -> list[dict]:
    """Unresolved reports across all candidates. Service-role client only."""
    response = (
        db.table("question_reports")
        .select("*")
        .is_("resolved_at", "null")
        .order("created_at")
        .limit(limit)
        .execute()
    )
    return response.data


def dead_jobs(db: Client, limit: int = 100) -> list[dict]:
    """Jobs that exhausted their retries. Service-role client only.

    Each row is a candidate whose document never finished and who has not been told.
    """
    try:
        response = db.table("dead_jobs").select("*").order("died_at").limit(limit).execute()
    except APIError:
        logger.exception("dead_jobs view unavailable — has migration 0006 been applied?")
        return []
    return response.data
