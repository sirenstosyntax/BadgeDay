"""The one endpoint the app polls to decide whether to show the paywall.

It reports entitlement, not a plan name — a subscription and a 90-day pass are different
purchases and the same answer to "can this person work today". The test pins that the
endpoint reports whatever the entitlement rule says, and adds the candidate's identity to
it, without inventing a second opinion about who is entitled.
"""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.account import router as account_router
from app.api.deps import CurrentUser, current_user, user_db
from app.storage.billing import Entitlement

USER_ID = "44444444-4444-4444-4444-444444444444"


class _Db:
    """Placeholder; the storage call is monkeypatched over it."""


def _client(monkeypatch: pytest.MonkeyPatch, state: Entitlement) -> TestClient:
    app = FastAPI()
    app.include_router(account_router)
    app.dependency_overrides[current_user] = lambda: CurrentUser(
        id=USER_ID, email="c@example.com", access_token="t"
    )
    app.dependency_overrides[user_db] = _Db
    monkeypatch.setattr("app.api.account.entitlement", lambda *_: state)
    return TestClient(app)


def test_me_reports_the_entitlement_verdict(monkeypatch: pytest.MonkeyPatch) -> None:
    expires = datetime(2099, 1, 1, tzinfo=UTC)
    client = _client(
        monkeypatch,
        Entitlement(entitled=True, subscription_status="active", access_expires_at=expires),
    )
    body = client.get("/me").json()
    assert body["entitled"] is True
    assert body["subscription_status"] == "active"


def test_me_carries_the_candidates_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _client(
        monkeypatch,
        Entitlement(entitled=False, subscription_status="none", access_expires_at=None),
    )
    body = client.get("/me").json()
    assert body["id"] == USER_ID
    assert body["email"] == "c@example.com"


def test_a_lapsed_candidate_is_reported_as_not_entitled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """past_due is not access — the endpoint must not soften the rule into a maybe."""
    client = _client(
        monkeypatch,
        Entitlement(entitled=False, subscription_status="past_due", access_expires_at=None),
    )
    body = client.get("/me").json()
    assert body["entitled"] is False
    assert body["subscription_status"] == "past_due"
