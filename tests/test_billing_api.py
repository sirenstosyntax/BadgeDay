"""The three billing endpoints, against a fake Stripe.

The gateway is a seam precisely so these can run with no Stripe account: a fake records
what the endpoint asked Stripe to do and hands back canned events. What is under test is the
wiring — that checkout creates and links a customer exactly once, that the portal refuses
when there is nothing to manage, and that the webhook trusts the signature and nothing else
before it writes anything.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.billing import get_gateway, service_db
from app.api.billing import router as billing_router
from app.api.deps import CurrentUser, current_user, user_db
from app.billing.gateway import WebhookVerificationError
from app.billing.plan import GrantPass, LinkCustomer
from app.config import Settings, get_settings

USER_ID = "44444444-4444-4444-4444-444444444444"

CONFIGURED = Settings(
    stripe_secret_key="sk_test",
    stripe_price_id_monthly="price_monthly",
    stripe_price_id_intensive_90day="price_intensive",
    public_web_url="https://app.badgeday.test",
)


class FakeGateway:
    def __init__(self) -> None:
        self.ensured: list[tuple[str | None, str]] = []
        self.checkouts: list[dict] = []
        self.portals: list[dict] = []
        self.event: dict = {}
        self.reject_signature = False

    def ensure_customer(self, *, email: str | None, user_id: str) -> str:
        self.ensured.append((email, user_id))
        return "cus_new"

    def start_checkout(self, **kwargs: object) -> str:
        self.checkouts.append(kwargs)
        return "https://checkout.stripe.test/session"

    def open_portal(self, **kwargs: object) -> str:
        self.portals.append(kwargs)
        return "https://portal.stripe.test/session"

    def read_event(self, *, payload: bytes, signature: str) -> dict:
        if self.reject_signature:
            raise WebhookVerificationError("bad signature")
        return self.event


def _harness(
    monkeypatch: pytest.MonkeyPatch,
    *,
    existing_customer: str | None = None,
    settings: Settings = CONFIGURED,
) -> tuple[TestClient, FakeGateway, list]:
    gateway = FakeGateway()
    applied: list = []

    monkeypatch.setattr("app.api.billing.customer_id_for", lambda *_: existing_customer)
    monkeypatch.setattr("app.api.billing.apply_change", lambda _db, change: applied.append(change))

    app = FastAPI()
    app.include_router(billing_router)
    app.dependency_overrides[current_user] = lambda: CurrentUser(
        id=USER_ID, email="c@example.com", access_token="t"
    )
    app.dependency_overrides[user_db] = lambda: object()
    app.dependency_overrides[service_db] = lambda: object()
    app.dependency_overrides[get_gateway] = lambda: gateway
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app), gateway, applied


# --- Checkout ----------------------------------------------------------------


def test_a_first_time_checkout_creates_and_links_a_customer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, gateway, applied = _harness(monkeypatch, existing_customer=None)
    response = client.post("/billing/checkout", json={"plan": "monthly"})

    assert response.status_code == 200
    assert response.json()["url"] == "https://checkout.stripe.test/session"
    assert gateway.ensured == [("c@example.com", USER_ID)]
    assert applied == [LinkCustomer(user_id=USER_ID, customer_id="cus_new")]
    assert gateway.checkouts[0]["mode"] == "subscription"
    assert gateway.checkouts[0]["price_id"] == "price_monthly"
    assert gateway.checkouts[0]["client_reference_id"] == USER_ID


def test_a_returning_customer_is_not_created_again(monkeypatch: pytest.MonkeyPatch) -> None:
    client, gateway, applied = _harness(monkeypatch, existing_customer="cus_existing")
    client.post("/billing/checkout", json={"plan": "intensive_90day"})

    assert gateway.ensured == []
    assert applied == []
    assert gateway.checkouts[0]["customer_id"] == "cus_existing"
    assert gateway.checkouts[0]["mode"] == "payment"
    assert gateway.checkouts[0]["price_id"] == "price_intensive"


def test_checkout_is_unavailable_until_billing_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, _ = _harness(monkeypatch, settings=Settings())
    response = client.post("/billing/checkout", json={"plan": "monthly"})
    assert response.status_code == 503


def test_checkout_rejects_a_plan_it_does_not_sell(monkeypatch: pytest.MonkeyPatch) -> None:
    client, _, _ = _harness(monkeypatch)
    response = client.post("/billing/checkout", json={"plan": "lifetime"})
    assert response.status_code == 422


# --- Portal ------------------------------------------------------------------


def test_the_portal_opens_for_a_customer(monkeypatch: pytest.MonkeyPatch) -> None:
    client, gateway, _ = _harness(monkeypatch, existing_customer="cus_existing")
    response = client.post("/billing/portal")
    assert response.status_code == 200
    assert response.json()["url"] == "https://portal.stripe.test/session"
    assert gateway.portals[0]["customer_id"] == "cus_existing"


def test_the_portal_refuses_when_there_is_nothing_to_manage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _, _ = _harness(monkeypatch, existing_customer=None)
    response = client.post("/billing/portal")
    assert response.status_code == 409


# --- Webhook -----------------------------------------------------------------


def test_a_forged_webhook_is_refused_before_any_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, gateway, applied = _harness(monkeypatch)
    gateway.reject_signature = True
    response = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "x"})
    assert response.status_code == 400
    assert applied == []


def test_a_verified_pass_webhook_grants_the_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    client, gateway, applied = _harness(monkeypatch)
    gateway.event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": USER_ID,
                "customer": "cus_existing",
                "mode": "payment",
                "payment_status": "paid",
            }
        },
    }
    response = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "x"})
    assert response.status_code == 200
    assert applied[0] == LinkCustomer(user_id=USER_ID, customer_id="cus_existing")
    assert isinstance(applied[1], GrantPass)


def test_an_unhandled_event_is_acknowledged_without_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, gateway, applied = _harness(monkeypatch)
    gateway.event = {"type": "charge.refunded", "data": {"object": {}}}
    response = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "x"})
    assert response.status_code == 200
    assert applied == []
