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

from app.api.billing import router as billing_router
from app.api.deps import CurrentUser, current_user, get_gateway, service_db, user_db
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
    monkeypatch.setattr(
        "app.api.billing.apply_entitlement", lambda _db, change: applied.append(change)
    )
    monkeypatch.setattr(
        "app.api.billing.user_id_for_customer",
        lambda _db, customer_id: USER_ID if customer_id else None,
    )

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


def test_checkout_does_not_sell_recruit_when_the_price_id_is_blank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Recruit plan name is valid, but a blank STRIPE_PRICE_ID_RECRUIT_* is not for sale."""
    client, gateway, _ = _harness(monkeypatch)
    response = client.post("/billing/checkout", json={"plan": "recruit_monthly"})
    assert response.status_code == 503
    assert gateway.checkouts == []


RECRUIT_CONFIGURED = Settings(
    stripe_secret_key="sk_test",
    stripe_price_id_monthly="price_monthly",
    stripe_price_id_intensive_90day="price_intensive",
    stripe_price_id_recruit_monthly="price_recruit_mo",
    stripe_price_id_recruit_intensive_90day="price_recruit_90",
    stripe_price_id_recruit_6month="price_recruit_6mo",
    stripe_price_id_recruit_annual="price_recruit_yr",
    public_web_url="https://app.badgeday.test",
)


def test_recruit_monthly_checkout_uses_the_recruit_price_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, gateway, applied = _harness(monkeypatch, settings=RECRUIT_CONFIGURED)
    response = client.post("/billing/checkout", json={"plan": "recruit_monthly"})

    assert response.status_code == 200
    assert gateway.checkouts[0]["mode"] == "subscription"
    assert gateway.checkouts[0]["price_id"] == "price_recruit_mo"
    assert gateway.checkouts[0]["metadata"]["plan"] == "recruit_monthly"
    assert gateway.checkouts[0]["metadata"]["price_id"] == "price_recruit_mo"
    assert applied == [LinkCustomer(user_id=USER_ID, customer_id="cus_new")]


def test_recruit_pass_checkout_is_a_one_time_payment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, gateway, _ = _harness(
        monkeypatch, existing_customer="cus_existing", settings=RECRUIT_CONFIGURED
    )
    response = client.post("/billing/checkout", json={"plan": "recruit_6month"})

    assert response.status_code == 200
    assert gateway.checkouts[0]["mode"] == "payment"
    assert gateway.checkouts[0]["price_id"] == "price_recruit_6mo"


def test_promote_checkout_is_unchanged_when_recruit_prices_are_also_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, gateway, _ = _harness(
        monkeypatch, existing_customer="cus_existing", settings=RECRUIT_CONFIGURED
    )
    response = client.post("/billing/checkout", json={"plan": "monthly"})

    assert response.status_code == 200
    assert gateway.checkouts[0]["mode"] == "subscription"
    assert gateway.checkouts[0]["price_id"] == "price_monthly"


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
                "metadata": {"price_id": "price_intensive"},
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


def test_a_recruit_pass_webhook_writes_entitlements_not_profiles(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.storage.entitlements import GrantModulePass

    client, gateway, applied = _harness(monkeypatch, settings=RECRUIT_CONFIGURED)
    gateway.event = {
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": USER_ID,
                "customer": "cus_existing",
                "mode": "payment",
                "payment_status": "paid",
                "metadata": {"price_id": "price_recruit_6mo", "plan": "recruit_6month"},
            }
        },
    }
    response = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "x"})
    assert response.status_code == 200
    assert applied[0] == LinkCustomer(user_id=USER_ID, customer_id="cus_existing")
    assert isinstance(applied[1], GrantModulePass)
    assert applied[1].module == "recruit"
    assert applied[1].user_id == USER_ID


def test_a_recruit_subscription_webhook_does_not_write_promote_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.billing.plan import SetSubscription
    from app.storage.entitlements import SetModuleSubscription

    client, gateway, applied = _harness(monkeypatch, settings=RECRUIT_CONFIGURED)
    gateway.event = {
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "customer": "cus_existing",
                "status": "active",
                "metadata": {"price_id": "price_recruit_mo", "user_id": USER_ID},
                "items": {"data": [{"price": {"id": "price_recruit_mo"}}]},
            }
        },
    }
    response = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "x"})
    assert response.status_code == 200
    assert applied == [
        SetModuleSubscription(user_id=USER_ID, module="recruit", status="active")
    ]
    assert not any(isinstance(change, SetSubscription) for change in applied)


def test_a_webhook_without_a_price_id_does_not_fall_open_to_promote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, gateway, applied = _harness(monkeypatch, settings=RECRUIT_CONFIGURED)
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
    assert applied == []


def test_an_unknown_price_id_does_not_fall_open_to_promote(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, gateway, applied = _harness(monkeypatch, settings=RECRUIT_CONFIGURED)
    gateway.event = {
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "customer": "cus_existing",
                "status": "active",
                "items": {"data": [{"price": {"id": "price_someone_invented"}}]},
            }
        },
    }
    response = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "x"})
    assert response.status_code == 200
    assert applied == []


def test_a_promote_webhook_still_writes_profiles_when_recruit_prices_exist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.billing.plan import SetSubscription
    from app.storage.entitlements import SetModuleSubscription

    client, gateway, applied = _harness(monkeypatch, settings=RECRUIT_CONFIGURED)
    gateway.event = {
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "customer": "cus_existing",
                "status": "active",
                "items": {"data": [{"price": {"id": "price_monthly"}}]},
            }
        },
    }
    response = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "x"})
    assert response.status_code == 200
    assert applied == [SetSubscription(customer_id="cus_existing", status="active")]
    assert not any(isinstance(change, SetModuleSubscription) for change in applied)


@pytest.mark.parametrize(
    "items",
    [
        {"data": [{"price": {}}]},
        {"data": [{"price": {"id": "price_someone_invented"}}]},
    ],
    ids=["deleted-with-items-missing-price", "deleted-with-items-unmapped-price"],
)
def test_deleted_subscription_with_items_but_no_mappable_price_is_acked_and_ignored(
    monkeypatch: pytest.MonkeyPatch, items: dict
) -> None:
    """Current fail-closed behavior after PR 68: no mappable price_id means no write.

    `plan_changes` itself would emit SetSubscription canceled for any
    customer.subscription.deleted with a customer id. The webhook does not
    call it unless module_for_stripe_price maps a Promote price, so a
    deleted event that has items but a missing or unknown price_id acks
    200 and writes nothing — including no Promote cancel and no Recruit
    clear. Product has not ruled whether a known-customer Promote cancel
    should still clear Promote when price_id is absent.
    """
    from app.billing.plan import SetSubscription
    from app.storage.entitlements import SetModuleSubscription

    client, gateway, applied = _harness(monkeypatch, settings=RECRUIT_CONFIGURED)
    gateway.event = {
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_legacy",
                "customer": "cus_existing",
                "status": "canceled",
                "items": items,
            }
        },
    }
    response = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "x"})
    assert response.status_code == 200
    assert response.json() == {"received": True}
    assert applied == []
    assert not any(isinstance(change, SetSubscription) for change in applied)
    assert not any(isinstance(change, SetModuleSubscription) for change in applied)


def test_deleted_subscription_with_recruit_price_clears_recruit_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mapped Recruit delete is an intentional path: Recruit canceled, Promote untouched."""
    from app.billing.plan import SetSubscription
    from app.storage.entitlements import SetModuleSubscription

    client, gateway, applied = _harness(monkeypatch, settings=RECRUIT_CONFIGURED)
    gateway.event = {
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_recruit",
                "customer": "cus_existing",
                "status": "canceled",
                "items": {"data": [{"price": {"id": "price_recruit_mo"}}]},
                "metadata": {"price_id": "price_recruit_mo", "user_id": USER_ID},
            }
        },
    }
    response = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "x"})
    assert response.status_code == 200
    assert applied == [
        SetModuleSubscription(user_id=USER_ID, module="recruit", status="canceled")
    ]
    assert not any(isinstance(change, SetSubscription) for change in applied)


def test_deleted_subscription_with_promote_price_clears_promote_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mapped Promote delete is an intentional path: Promote canceled, Recruit untouched."""
    from app.billing.plan import SetSubscription
    from app.storage.entitlements import SetModuleSubscription

    client, gateway, applied = _harness(monkeypatch, settings=RECRUIT_CONFIGURED)
    gateway.event = {
        "type": "customer.subscription.deleted",
        "data": {
            "object": {
                "id": "sub_promote",
                "customer": "cus_existing",
                "status": "canceled",
                "items": {"data": [{"price": {"id": "price_monthly"}}]},
            }
        },
    }
    response = client.post("/billing/webhook", content=b"{}", headers={"stripe-signature": "x"})
    assert response.status_code == 200
    assert applied == [SetSubscription(customer_id="cus_existing", status="canceled")]
    assert not any(isinstance(change, SetModuleSubscription) for change in applied)
