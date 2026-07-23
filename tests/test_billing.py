"""Entitlement translation and the gate it produces.

The rule itself lives in `has_access` and is exercised against the live project. What
matters here is the translation: a database refusal has to become "pay us", and only a
database refusal — because getting that wrong in the other direction asks a paying
candidate for money during an outage, and never tells us the database was down.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from postgrest.exceptions import APIError

from app.api.deps import CurrentUser, current_user, user_db
from app.api.documents import router as documents_router
from app.api.practice import router as practice_router
from app.config import Settings, get_settings
from app.storage.billing import SubscriptionRequired, as_subscription_required

USER_ID = "44444444-4444-4444-4444-444444444444"
PDF = "application/pdf"


def _error(message: str, code: str) -> APIError:
    return APIError({"message": message, "code": code, "details": "", "hint": ""})


# --- Translation -------------------------------------------------------------


def test_an_rls_refusal_becomes_a_subscription_problem() -> None:
    denied = _error("new row violates row-level security policy", "42501")
    assert isinstance(as_subscription_required(denied), SubscriptionRequired)


def test_the_message_alone_is_enough_to_recognise_it() -> None:
    """Not every driver surfaces the code, and the policy is the only thing that refuses
    these two tables for a candidate who owns the row."""
    denied = _error('new row violates row-level security policy for table "documents"', "")
    assert isinstance(as_subscription_required(denied), SubscriptionRequired)


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("connection reset by peer", "08006"),
        ("duplicate key value violates unique constraint", "23505"),
        ("canceling statement due to statement timeout", "57014"),
    ],
)
def test_every_other_failure_is_passed_through(message: str, code: str) -> None:
    """A database that is merely broken must not be reported as an unpaid invoice."""
    original = _error(message, code)
    assert as_subscription_required(original) is original


# --- The gate ----------------------------------------------------------------


class _Db:
    """Placeholder; the storage call is monkeypatched over it."""


def _client(monkeypatch: pytest.MonkeyPatch, target: str, raises: Exception) -> TestClient:
    app = FastAPI()
    app.include_router(documents_router)
    app.include_router(practice_router)
    app.dependency_overrides[current_user] = lambda: CurrentUser(
        id=USER_ID, email="c@example.com", access_token="t"
    )
    app.dependency_overrides[user_db] = _Db
    app.dependency_overrides[get_settings] = lambda: Settings(max_upload_bytes=1024)

    def explode(*_: object, **__: object) -> None:
        raise raises

    monkeypatch.setattr(target, explode)
    return TestClient(app)


DENIED = _error("new row violates row-level security policy", "42501")
BROKEN = _error("connection reset by peer", "08006")


def test_uploading_without_a_subscription_is_402(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, "app.api.documents.create_document", DENIED)
    response = client.post("/documents", files={"file": ("sog.pdf", b"%PDF-1.4", PDF)})
    assert response.status_code == 402


def test_the_upload_refusal_says_the_documents_are_safe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A candidate whose card lapsed needs to know their uploads are still theirs, in the
    same breath as being told they cannot add more."""
    client = _client(monkeypatch, "app.api.documents.create_document", DENIED)
    response = client.post("/documents", files={"file": ("sog.pdf", b"%PDF-1.4", PDF)})
    assert "delete them" in response.json()["detail"]


def test_starting_a_session_without_a_subscription_is_402(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(monkeypatch, "app.api.practice.start_session", DENIED)
    response = client.post("/sessions", json={"document_id": None})
    assert response.status_code == 402


def test_a_broken_database_is_not_a_payment_demand(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(monkeypatch, "app.api.practice.start_session", BROKEN)
    with pytest.raises(APIError):
        client.post("/sessions", json={"document_id": None})
