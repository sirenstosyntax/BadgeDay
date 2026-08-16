"""The candidate's account endpoints: reporting entitlement, and deleting the account.

`/me` reports entitlement, not a plan name — a subscription and a 90-day pass are different
purchases and the same answer to "can this person work today". `DELETE /me` must stop
billing before it removes anything, so a Stripe failure never leaves a deleted account that
keeps being charged.
"""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.account import router as account_router
from app.api.deps import CurrentUser, current_user, get_gateway, service_db, user_db
from app.storage.billing import Entitlement
from app.storage.store import ManagedElsewhere

USER_ID = "44444444-4444-4444-4444-444444444444"


class _Db:
    """Placeholder; the storage call is monkeypatched over it."""


def _client(
    monkeypatch: pytest.MonkeyPatch,
    state: Entitlement,
    store: ManagedElsewhere | None = None,
) -> TestClient:
    app = FastAPI()
    app.include_router(account_router)
    app.dependency_overrides[current_user] = lambda: CurrentUser(
        id=USER_ID, email="c@example.com", access_token="t"
    )
    app.dependency_overrides[user_db] = _Db
    monkeypatch.setattr("app.api.account.entitlement", lambda *_: state)
    monkeypatch.setattr("app.api.account.managed_elsewhere", lambda *_: store)
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


def test_a_stripe_candidate_is_not_reported_as_managed_by_a_store(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The common case, and the one the web app depends on to keep showing its portal."""
    client = _client(
        monkeypatch,
        Entitlement(entitled=True, subscription_status="active", access_expires_at=None),
    )
    assert client.get("/me").json()["managed_by"] is None


def test_a_store_subscription_is_reported_so_the_app_can_send_them_to_the_right_place(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Offering a Stripe portal button to someone who paid Apple shows them an empty page.

    They then cannot find how to cancel, and the way that ends is a chargeback rather than
    a cancellation — so the endpoint has to say which till took the money.
    """
    client = _client(
        monkeypatch,
        Entitlement(entitled=True, subscription_status="none", access_expires_at=None),
        ManagedElsewhere(
            platform="appstore", product_id="badgeday.promote.monthly", status="active"
        ),
    )
    body = client.get("/me").json()
    assert body["managed_by"] == "appstore"
    assert body["entitled"] is True


# --- Deleting the account ----------------------------------------------------


class _DeletingGateway:
    def __init__(self, fails: bool = False) -> None:
        self.deleted: list[str] = []
        self.fails = fails

    def delete_customer(self, customer_id: str) -> None:
        if self.fails:
            raise RuntimeError("stripe unreachable")
        self.deleted.append(customer_id)


def _delete_harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    customer_id: str | None,
    gateway: _DeletingGateway,
) -> tuple[TestClient, list]:
    order: list = []
    monkeypatch.setattr("app.api.account.customer_id_for", lambda *_: customer_id)
    monkeypatch.setattr(
        "app.api.account.purge_account", lambda *_: order.append("purged")
    )
    # If the gateway is asked to stop billing, record that it happened before the purge, so
    # the ordering the endpoint promises is an assertion and not just a hope.
    original = gateway.delete_customer

    def record(cid: str) -> None:
        order.append("billing")
        original(cid)

    gateway.delete_customer = record  # type: ignore[method-assign]

    app = FastAPI()
    app.include_router(account_router)
    app.dependency_overrides[current_user] = lambda: CurrentUser(
        id=USER_ID, email="c@example.com", access_token="t"
    )
    app.dependency_overrides[user_db] = _Db
    app.dependency_overrides[service_db] = _Db
    app.dependency_overrides[get_gateway] = lambda: gateway
    return TestClient(app), order


def test_deleting_stops_billing_then_purges(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _DeletingGateway()
    client, order = _delete_harness(monkeypatch, customer_id="cus_1", gateway=gateway)
    response = client.delete("/me")
    assert response.status_code == 204
    assert gateway.deleted == ["cus_1"]
    assert order == ["billing", "purged"]  # billing is stopped before anything is removed


def test_deleting_a_candidate_who_never_paid_skips_stripe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = _DeletingGateway()
    client, order = _delete_harness(monkeypatch, customer_id=None, gateway=gateway)
    response = client.delete("/me")
    assert response.status_code == 204
    assert gateway.deleted == []
    assert order == ["purged"]


def test_a_stripe_failure_deletes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole point: never leave a deleted account still being charged."""
    gateway = _DeletingGateway(fails=True)
    client, order = _delete_harness(monkeypatch, customer_id="cus_1", gateway=gateway)
    response = client.delete("/me")
    assert response.status_code == 502
    assert "purged" not in order
