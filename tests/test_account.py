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
from app.api.deps import CurrentUser, current_user, get_gateway, get_settings, service_db, user_db
from app.config import Settings
from app.storage.billing import Entitlement
from app.storage.entitlements import ModuleEntitlement
from app.storage.store import ManagedElsewhere

USER_ID = "44444444-4444-4444-4444-444444444444"


class _Db:
    """Placeholder; the storage call is monkeypatched over it."""


def _recruit(
    *,
    entitled: bool = False,
    subscription_status: str = "none",
    access_expires_at=None,
) -> ModuleEntitlement:
    return ModuleEntitlement(
        module="recruit",
        entitled=entitled,
        subscription_status=subscription_status,
        access_expires_at=access_expires_at,
    )


def _client(
    monkeypatch: pytest.MonkeyPatch,
    state: Entitlement,
    store: ManagedElsewhere | None = None,
    *,
    recruit: ModuleEntitlement | None = None,
    recruit_store: ManagedElsewhere | None = None,
    settings: Settings | None = None,
) -> TestClient:
    configured = settings or Settings()
    app = FastAPI()
    app.include_router(account_router)
    app.dependency_overrides[current_user] = lambda: CurrentUser(
        id=USER_ID, email="c@example.com", access_token="t"
    )
    app.dependency_overrides[user_db] = _Db
    app.dependency_overrides[get_settings] = lambda: configured
    monkeypatch.setattr("app.api.account.entitlement", lambda *_: state)
    monkeypatch.setattr(
        "app.api.account.module_entitlement", lambda *_: recruit or _recruit()
    )

    def _managed(_db, _user_id, *, product_ids):
        # Same rule as managed_elsewhere_for: only a row whose product is in
        # the requested set counts. A Recruit Play SKU must not satisfy a
        # Promote query (and the reverse).
        if not product_ids:
            return None
        for row in (store, recruit_store):
            if row is not None and row.product_id in product_ids:
                return row
        return None

    monkeypatch.setattr("app.api.account.managed_elsewhere_for", _managed)
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
    assert body["play_products"] == {
        "monthly": None,
        "intensive_90day": None,
        "recruit_monthly": None,
        "recruit_intensive_90day": None,
        "recruit_6month": None,
        "recruit_annual": None,
    }


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
        settings=Settings(appstore_product_id_monthly="badgeday.promote.monthly"),
    )
    body = client.get("/me").json()
    assert body["managed_by"] == "appstore"
    assert body["entitled"] is True


def test_me_reports_recruit_separately_from_a_promote_subscription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Lieutenant plan is not a Recruit plan. The milestone reads recruit, not these."""
    client = _client(
        monkeypatch,
        Entitlement(entitled=True, subscription_status="active", access_expires_at=None),
        recruit=_recruit(entitled=False, subscription_status="none"),
    )
    body = client.get("/me").json()
    assert body["entitled"] is True
    assert body["subscription_status"] == "active"
    assert body["recruit"]["entitled"] is False
    assert body["recruit"]["subscription_status"] == "none"
    assert body["recruit"]["managed_by"] is None


def test_me_reports_a_stripe_recruit_subscription(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(
        monkeypatch,
        Entitlement(entitled=False, subscription_status="none", access_expires_at=None),
        recruit=_recruit(entitled=True, subscription_status="active"),
    )
    body = client.get("/me").json()
    assert body["recruit"]["entitled"] is True
    assert body["recruit"]["subscription_status"] == "active"
    assert body["recruit"]["managed_by"] is None


def test_me_reports_store_managed_recruit_only_from_recruit_products(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _client(
        monkeypatch,
        Entitlement(entitled=True, subscription_status="none", access_expires_at=None),
        ManagedElsewhere(
            platform="play", product_id="badgeday.promote.monthly", status="active"
        ),
        recruit=_recruit(entitled=True, subscription_status="active"),
        recruit_store=ManagedElsewhere(
            platform="appstore", product_id="named.by.grant.recruit", status="active"
        ),
        settings=Settings(
            play_product_id_monthly="badgeday.promote.monthly",
            appstore_product_id_recruit_monthly="named.by.grant.recruit",
        ),
    )
    body = client.get("/me").json()
    assert body["managed_by"] == "play"
    assert body["recruit"]["managed_by"] == "appstore"


def test_held_recruit_skus_do_not_invent_a_store_till() -> None:
    """Blank Recruit product IDs must not match a Promote Play row."""
    from app.billing.module import store_product_ids_for
    from app.config import Settings
    from app.storage.store import managed_elsewhere_for

    assert store_product_ids_for(Settings(), "recruit") == frozenset()
    assert (
        managed_elsewhere_for(object(), USER_ID, product_ids=frozenset()) is None
    )


def test_me_exposes_configured_play_product_ids_and_never_invents_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The TWA buy path reads these. Empty means no Play buy button — not a fake SKU."""
    client = _client(
        monkeypatch,
        Entitlement(entitled=False, subscription_status="none", access_expires_at=None),
        settings=Settings(
            play_product_id_monthly="named.by.grant.monthly",
            play_product_id_intensive_90day="",
            play_product_id_recruit_monthly="named.by.grant.recruit.monthly",
            play_product_id_recruit_intensive_90day="",
            play_product_id_recruit_6month="named.by.grant.recruit.6month",
            play_product_id_recruit_annual="named.by.grant.recruit.annual",
        ),
    )
    body = client.get("/me").json()
    assert body["play_products"]["monthly"] == "named.by.grant.monthly"
    assert body["play_products"]["intensive_90day"] is None
    assert body["play_products"]["recruit_monthly"] == "named.by.grant.recruit.monthly"
    assert body["play_products"]["recruit_intensive_90day"] is None
    assert body["play_products"]["recruit_6month"] == "named.by.grant.recruit.6month"
    assert body["play_products"]["recruit_annual"] == "named.by.grant.recruit.annual"


def test_a_recruit_play_row_does_not_set_promote_managed_by(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Top-level managed_by is Promote SKUs only. A Recruit Play purchase must not
    send the reading-list Billing button to Play.
    """
    client = _client(
        monkeypatch,
        Entitlement(entitled=False, subscription_status="none", access_expires_at=None),
        store=ManagedElsewhere(
            platform="play", product_id="badgeday.recruit.monthly", status="active"
        ),
        recruit=_recruit(entitled=True, subscription_status="active"),
        recruit_store=ManagedElsewhere(
            platform="play", product_id="badgeday.recruit.monthly", status="active"
        ),
        settings=Settings(
            play_product_id_monthly="badgeday.promote.monthly",
            play_product_id_recruit_monthly="badgeday.recruit.monthly",
        ),
    )
    body = client.get("/me").json()
    assert body["managed_by"] is None
    assert body["recruit"]["managed_by"] == "play"


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
