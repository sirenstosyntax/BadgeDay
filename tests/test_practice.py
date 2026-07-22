"""Quiz-loop logic that does not need a database.

The integration is covered against the live project: that a candidate cannot read
correct_answer, that submit_response grades and returns the citation, that one candidate
cannot answer into another's session. What is worth pinning here is the arithmetic and
the error mapping — a coverage tracker that divides by zero, or a duplicate answer that
surfaces as a 500 instead of a 409, are both bugs no schema check would catch.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from app.api.deps import CurrentUser, current_user, user_db
from app.api.practice import router
from app.storage.practice import (
    AlreadyAnswered,
    Coverage,
    QuestionNotFound,
    SessionNotFound,
    _translate,
    _verdict,
)

USER_ID = "33333333-3333-3333-3333-333333333333"


# --- Coverage arithmetic -----------------------------------------------------


def test_a_document_with_nothing_worth_asking_reads_as_zero() -> None:
    """Not a division error. A document of pure container headings has no denominator,
    and the tracker still has to render."""
    record = Coverage(document_id="d", sections_total=0, sections_exercised=0)
    assert record.percent == 0


@pytest.mark.parametrize(
    ("exercised", "total", "expected"),
    [(0, 4, 0), (1, 4, 25), (2, 3, 67), (3, 3, 100)],
)
def test_coverage_percentages(exercised: int, total: int, expected: int) -> None:
    record = Coverage(document_id="d", sections_total=total, sections_exercised=exercised)
    assert record.percent == expected


# --- Citations ---------------------------------------------------------------


def _row(**overrides) -> dict:
    return {
        "is_correct": True,
        "explanation": "Because the guideline says so.",
        "correct_index": 1,
        "correct_answer": None,
        "model_answer": None,
        "section_path": ["304.2.1"],
        "section_title": "Water Supply",
        "page_start": 3,
        "page_end": 3,
        **overrides,
    }


def test_a_numbered_section_cites_number_title_and_page() -> None:
    assert _verdict(_row()).citation == "304.2.1 Water Supply, p. 3"


def test_a_section_spanning_pages_cites_a_range() -> None:
    assert _verdict(_row(page_end=5)).citation == "304.2.1 Water Supply, pp. 3–5"


def test_an_untitled_section_still_cites_its_number() -> None:
    assert _verdict(_row(section_title=None)).citation == "304.2.1, p. 3"


def test_a_lettered_outline_keeps_its_ancestors() -> None:
    """`d` on its own is meaningless; the path is the citation."""
    verdict = _verdict(_row(section_path=["PROCEDURE", "C", "4", "d"], section_title=None))
    assert verdict.citation == "PROCEDURE C.4.d, p. 3"


def test_a_semantic_chunk_cites_the_page_alone() -> None:
    verdict = _verdict(_row(section_path=[], section_title=None))
    assert verdict.citation == "p. 3"


def test_short_answer_carries_no_verdict_but_does_carry_the_model_answer() -> None:
    verdict = _verdict(
        _row(is_correct=None, correct_index=None, model_answer="Continuous supply first.")
    )
    assert verdict.is_correct is None
    assert verdict.model_answer == "Continuous supply first."


# --- Translating database errors ---------------------------------------------


def _api_error(message: str, code: str = "P0001") -> APIError:
    return APIError({"message": message, "code": code, "details": "", "hint": ""})


def test_a_duplicate_answer_is_recognised() -> None:
    assert isinstance(_translate(_api_error("duplicate key", "23505")), AlreadyAnswered)


def test_a_missing_session_is_recognised() -> None:
    assert isinstance(_translate(_api_error("no such session")), SessionNotFound)


def test_a_missing_question_is_recognised() -> None:
    assert isinstance(_translate(_api_error("no such question")), QuestionNotFound)


def test_an_unrecognised_error_is_passed_through_unchanged() -> None:
    """Guessing at an unfamiliar database error would turn an outage into a 404."""
    original = _api_error("connection reset by peer", "08006")
    assert _translate(original) is original


# --- Status codes ------------------------------------------------------------


class _Db:
    """Stands in for the client; every practice call is monkeypatched over it."""


def _client(monkeypatch: pytest.MonkeyPatch, raises: Exception) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[current_user] = lambda: CurrentUser(
        id=USER_ID, email="c@example.com", access_token="t"
    )
    app.dependency_overrides[user_db] = _Db

    def explode(*_: object, **__: object) -> None:
        raise raises

    monkeypatch.setattr("app.api.practice.submit", explode)
    return TestClient(app)


ANSWER = {"question_id": "q1", "selected_index": 0}


def test_answering_twice_is_a_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _client(monkeypatch, AlreadyAnswered("dupe")).post(
        "/sessions/s1/responses", json=ANSWER
    )
    assert response.status_code == 409


def test_answering_into_an_unknown_session_is_404(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _client(monkeypatch, SessionNotFound("nope")).post(
        "/sessions/s1/responses", json=ANSWER
    )
    assert response.status_code == 404


def test_answering_an_unknown_question_is_404(monkeypatch: pytest.MonkeyPatch) -> None:
    """Another candidate's question reaches here as 'no such question', deliberately —
    distinguishing it would confirm the id exists."""
    response = _client(monkeypatch, QuestionNotFound("nope")).post(
        "/sessions/s1/responses", json=ANSWER
    )
    assert response.status_code == 404


def test_an_unexpected_database_error_is_not_dressed_up_as_a_404(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A 404 would tell the candidate their session is gone when the database merely
    blinked. It has to surface as the server error it is."""
    with pytest.raises(APIError):
        _client(monkeypatch, _api_error("connection reset", "08006")).post(
            "/sessions/s1/responses", json=ANSWER
        )


def test_the_served_question_shape_carries_no_answer() -> None:
    """A regression guard on the response model itself: if an answer column is ever added
    to QuizQuestion, this fails before it reaches a browser."""
    from app.storage.practice import QuizQuestion

    assert set(QuizQuestion.model_fields) == {
        "id",
        "document_id",
        "chunk_id",
        "type",
        "stem",
        "options",
    }


def test_the_selected_columns_match_the_grant() -> None:
    """QUESTION_COLUMNS is the list migration 0004 grants. Drifting from it either breaks
    every query or, worse, starts selecting a column the candidate should not see."""
    from app.storage.practice import QUESTION_COLUMNS, QuizQuestion

    assert set(QUESTION_COLUMNS.split(",")) == set(QuizQuestion.model_fields)
