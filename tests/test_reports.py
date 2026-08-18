"""Reporting a question as wrong.

This is the product's only external check on generation quality. Verification proves a
question is grounded in the section it cites; nothing proves it is *right*, so the
candidate is the last line — and a report we never receive is worth nothing.

Two things are worth pinning without a database. That a question the candidate cannot read
cannot be reported, because that check is the permission model rather than an extra guard
in front of it. And that re-reporting updates rather than fails, because a candidate who
has changed his mind is giving us better information and should not be argued with.

The RLS itself is proved against the live project by `scripts/verify_schema.py`.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import CurrentUser, current_user, user_db
from app.api.reports import router
from app.storage.reports import (
    MAX_DETAIL_CHARS,
    QuestionNotFound,
    report_question,
    withdraw_report,
)

USER_ID = "44444444-4444-4444-4444-444444444444"
QUESTION_ID = "55555555-5555-5555-5555-555555555555"


class FakeTable:
    def __init__(self, db: "FakeDb", name: str) -> None:
        self.db, self.name = db, name
        self._filters: dict = {}

    def select(self, *_):
        self.db.calls.append(("select", self.name))
        return self

    def eq(self, column, value):
        self._filters[column] = value
        return self

    def is_(self, *_):
        return self

    def order(self, *_, **__):
        return self

    def limit(self, *_):
        return self

    def upsert(self, payload, on_conflict=None):
        self.db.calls.append(("upsert", self.name, on_conflict))
        self.db.upserted = payload
        return self

    def delete(self):
        self.db.calls.append(("delete", self.name))
        return self

    def execute(self):
        if self.name == "questions":
            return type("R", (), {"data": self.db.questions})
        if self.db.calls and self.db.calls[-1][0] == "delete":
            return type("R", (), {"data": self.db.delete_result})
        if self.db.upserted is not None:
            row = {
                "id": "report-1",
                "created_at": "2026-07-28T00:00:00Z",
                "resolved_at": None,
                **self.db.upserted,
            }
            return type("R", (), {"data": [row]})
        return type("R", (), {"data": []})


class FakeDb:
    def __init__(self, questions: list | None = None, delete_result: list | None = None):
        self.questions = questions if questions is not None else [{"id": QUESTION_ID}]
        self.delete_result = delete_result if delete_result is not None else [{"id": "r"}]
        self.calls: list = []
        self.upserted = None

    def table(self, name):
        return FakeTable(self, name)


# --- the permission model is the read, not a check in front of it ------------


def test_a_question_the_candidate_cannot_read_cannot_be_reported() -> None:
    """His policies only return questions from his own documents.

    So the lookup *is* the authorisation. If it returns nothing the question either does
    not exist or belongs to someone else, and those must be indistinguishable — telling a
    stranger which of the two it is leaks that the question exists.
    """
    db = FakeDb(questions=[])
    with pytest.raises(QuestionNotFound):
        report_question(db, USER_ID, QUESTION_ID, "answer_wrong")


def test_a_readable_question_records_the_report() -> None:
    db = FakeDb()
    record = report_question(db, USER_ID, QUESTION_ID, "not_in_document", "Not in 304.2.")
    assert record.reason == "not_in_document"
    assert record.detail == "Not in 304.2."
    assert db.upserted["user_id"] == USER_ID


# --- a candidate who changes his mind is not making an error -----------------


def test_reporting_twice_updates_rather_than_fails() -> None:
    """Upsert on (question, user). 'You already said that' is a worse answer than a record
    of what he now thinks."""
    db = FakeDb()
    report_question(db, USER_ID, QUESTION_ID, "unclear")
    assert ("upsert", "question_reports", "question_id,user_id") in db.calls


def test_blank_detail_is_stored_as_null_not_as_empty_string() -> None:
    db = FakeDb()
    report_question(db, USER_ID, QUESTION_ID, "other", "   ")
    assert db.upserted["detail"] is None


def test_overlong_detail_is_truncated_rather_than_rejected() -> None:
    """The column caps at 2000. Losing the tail of a long report beats losing the report."""
    db = FakeDb()
    report_question(db, USER_ID, QUESTION_ID, "other", "x" * (MAX_DETAIL_CHARS + 500))
    assert len(db.upserted["detail"]) == MAX_DETAIL_CHARS


def test_withdrawing_a_report_that_does_not_exist_returns_false() -> None:
    assert withdraw_report(FakeDb(delete_result=[]), QUESTION_ID) is False


# --- API surface -------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[current_user] = lambda: CurrentUser(
        id=USER_ID, email="c@example.com", access_token="t"
    )
    app.dependency_overrides[user_db] = lambda: FakeDb()
    return TestClient(app)


def test_reporting_an_unreadable_question_is_a_404_not_a_500(client: TestClient) -> None:
    client.app.dependency_overrides[user_db] = lambda: FakeDb(questions=[])
    response = client.post(
        f"/questions/{QUESTION_ID}/report", json={"reason": "answer_wrong"}
    )
    assert response.status_code == 404


def test_an_unknown_reason_is_refused(client: TestClient) -> None:
    """The categories are the useful part of a report, so they are closed."""
    response = client.post(
        f"/questions/{QUESTION_ID}/report", json={"reason": "i_just_do_not_like_it"}
    )
    assert response.status_code == 422


def test_detail_is_optional(client: TestClient) -> None:
    """Friction decides whether a busy candidate mid-session bothers at all."""
    response = client.post(
        f"/questions/{QUESTION_ID}/report", json={"reason": "unclear"}
    )
    assert response.status_code == 201


def test_reporting_requires_a_signed_in_candidate() -> None:
    app = FastAPI()
    app.include_router(router)
    response = TestClient(app).post(
        f"/questions/{QUESTION_ID}/report", json={"reason": "unclear"}
    )
    assert response.status_code in (401, 403)
