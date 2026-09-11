"""The store billing endpoints.

The property under test throughout is that nothing grants access except a purchase the
store itself confirmed. These endpoints are public payment paths — the notification ones
are unauthenticated by design — so the interesting cases are the refusals, not the happy
path.
"""

from datetime import UTC, datetime

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import (
    CurrentUser,
    current_user,
    get_settings,
    get_store_gateway,
    service_db,
)
from app.api.store import router as store_router
from app.billing.store import PurchaseFacts, RecordPurchase
from app.billing.store_gateway import StoreNotConfigured, StoreVerificationError
from app.config import Settings

USER_ID = "66666666-6666-6666-6666-666666666666"
PAID_THROUGH = datetime(2026, 12, 1, tzinfo=UTC)


class _ConfirmingGateway:
    """A store that confirms whatever it is asked about."""

    def verify_play_purchase(self, *, purchase_token: str, product_id: str, user_id: str):
        return PurchaseFacts(
            platform="play",
            product_id=product_id,
            purchase_identifier=purchase_token,
            kind="subscription",
            state="purchased",
            expires_at=PAID_THROUGH,
            user_id=user_id,
        )

    def verify_appstore_purchase(self, *, transaction_id: str, user_id: str):
        return PurchaseFacts(
            platform="appstore",
            product_id="badgeday.promote.monthly",
            purchase_identifier=transaction_id,
            kind="subscription",
            state="purchased",
            expires_at=PAID_THROUGH,
            user_id=user_id,
        )

    def read_play_notification(self, *, payload: bytes, authorization: str):
        return None

    def read_appstore_notification(self, *, payload: bytes):
        return None


class _RefusingGateway(_ConfirmingGateway):
    """A store that does not recognise the purchase it is shown."""

    def verify_play_purchase(self, *, purchase_token: str, product_id: str, user_id: str):
        raise StoreVerificationError("no such purchase")

    def verify_appstore_purchase(self, *, transaction_id: str, user_id: str):
        raise StoreVerificationError("no such transaction")


class _UnconfiguredGateway(_ConfirmingGateway):
    def verify_play_purchase(self, *, purchase_token: str, product_id: str, user_id: str):
        raise StoreNotConfigured("not configured")


class _AcknowledgingGateway(_ConfirmingGateway):
    """Confirms, and records whether Play was told we kept the purchase."""

    def __init__(self) -> None:
        self.acks: list = []

    def acknowledge_play_purchase(self, facts):
        self.acks.append(facts)


def _harness(monkeypatch: pytest.MonkeyPatch, gateway: object, **settings: object):
    """Returns a client and the list of changes that reached the database."""
    written: list = []
    monkeypatch.setattr(
        "app.api.store.apply_store_change", lambda _db, change: written.append(change)
    )
    # Mapped Promote SKUs so a confirmed store purchase can write. Tests that
    # need a blank or Recruit mapping pass their own IDs; an unmapped product
    # still fails closed.
    settings.setdefault("play_product_id_monthly", "badgeday.promote.monthly")
    settings.setdefault("appstore_product_id_monthly", "badgeday.promote.monthly")

    app = FastAPI()
    app.include_router(store_router)
    app.dependency_overrides[current_user] = lambda: CurrentUser(
        id=USER_ID, email="c@example.com", access_token="t"
    )
    app.dependency_overrides[service_db] = lambda: object()
    app.dependency_overrides[get_store_gateway] = lambda: gateway
    app.dependency_overrides[get_settings] = lambda: Settings(**settings)
    return TestClient(app), written


# --- The app reporting its own purchase --------------------------------------


def test_a_confirmed_recruit_play_purchase_writes_recruit_entitlement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.storage.entitlements import SetModuleSubscription

    entitlements: list = []
    monkeypatch.setattr(
        "app.api.store.apply_entitlement", lambda _db, change: entitlements.append(change)
    )
    client, written = _harness(
        monkeypatch,
        _ConfirmingGateway(),
        play_product_id_recruit_monthly="badgeday.recruit.monthly",
        play_product_id_monthly="badgeday.promote.monthly",
    )
    response = client.post(
        "/billing/store/play/purchase",
        json={"purchase_token": "token-r", "product_id": "badgeday.recruit.monthly"},
    )

    assert response.status_code == 200
    assert response.json()["entitled"] is True
    assert written[0].module == "recruit"
    assert entitlements[0] == SetModuleSubscription(
        user_id=USER_ID, module="recruit", status="active"
    )


def test_a_promote_play_purchase_does_not_write_recruit_entitlement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entitlements: list = []
    monkeypatch.setattr(
        "app.api.store.apply_entitlement", lambda _db, change: entitlements.append(change)
    )
    client, written = _harness(
        monkeypatch,
        _ConfirmingGateway(),
        play_product_id_monthly="badgeday.promote.monthly",
        play_product_id_recruit_monthly="badgeday.recruit.monthly",
    )
    response = client.post(
        "/billing/store/play/purchase",
        json={"purchase_token": "token-abc", "product_id": "badgeday.promote.monthly"},
    )

    assert response.status_code == 200
    assert written[0].module == "promote"
    assert entitlements == []


def test_a_confirmed_play_purchase_is_recorded_against_the_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, written = _harness(monkeypatch, _ConfirmingGateway())
    response = client.post(
        "/billing/store/play/purchase",
        json={"purchase_token": "token-abc", "product_id": "badgeday.promote.monthly"},
    )

    assert response.status_code == 200
    assert response.json()["entitled"] is True
    assert len(written) == 1
    change = written[0]
    assert isinstance(change, RecordPurchase)
    assert change.user_id == USER_ID
    assert change.status == "active"
    assert change.expires_at == PAID_THROUGH


def test_a_purchase_the_store_will_not_confirm_grants_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The client says what to check, never what to believe.

    Without this the endpoint is a subscription for anyone who can POST a made-up token,
    which is the whole reason verification is not optional.
    """
    client, written = _harness(monkeypatch, _RefusingGateway())
    response = client.post(
        "/billing/store/play/purchase",
        json={"purchase_token": "invented", "product_id": "badgeday.promote.monthly"},
    )

    assert response.status_code == 402
    assert written == []


def test_an_unconfigured_store_refuses_rather_than_assumes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """503, not a silent success. A payment path that cannot verify must not pretend."""
    client, written = _harness(monkeypatch, _UnconfiguredGateway())
    response = client.post(
        "/billing/store/play/purchase",
        json={"purchase_token": "token-abc", "product_id": "badgeday.promote.monthly"},
    )

    assert response.status_code == 503
    assert written == []


def test_a_successful_persist_acknowledges_play_once(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _AcknowledgingGateway()
    client, written = _harness(monkeypatch, gateway)
    response = client.post(
        "/billing/store/play/purchase",
        json={"purchase_token": "token-abc", "product_id": "badgeday.promote.monthly"},
    )

    assert response.status_code == 200
    assert len(written) == 1
    assert len(gateway.acks) == 1
    assert gateway.acks[0].purchase_identifier == "token-abc"


def test_a_failed_persist_does_not_acknowledge_play(monkeypatch: pytest.MonkeyPatch) -> None:
    gateway = _AcknowledgingGateway()
    client, written = _harness(monkeypatch, gateway)
    monkeypatch.setattr(
        "app.api.store.apply_store_change",
        lambda _db, _change: (_ for _ in ()).throw(RuntimeError("db write failed")),
    )

    with pytest.raises(RuntimeError, match="db write failed"):
        client.post(
            "/billing/store/play/purchase",
            json={"purchase_token": "token-abc", "product_id": "badgeday.promote.monthly"},
        )

    assert written == []
    assert gateway.acks == []


def test_a_confirmed_appstore_purchase_is_recorded(monkeypatch: pytest.MonkeyPatch) -> None:
    client, written = _harness(monkeypatch, _ConfirmingGateway())
    response = client.post(
        "/billing/store/appstore/purchase", json={"transaction_id": "2000000012345678"}
    )

    assert response.status_code == 200
    assert len(written) == 1
    assert written[0].platform == "appstore"
    assert written[0].purchase_identifier == "2000000012345678"
    assert written[0].module == "promote"


def test_an_unmapped_play_product_is_refused_without_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Store confirmation is not a module mapping. An unknown SKU must not
    default to promote, write has_access, or ack a Play purchase we will not keep.
    """
    gateway = _AcknowledgingGateway()
    entitlements: list = []
    monkeypatch.setattr(
        "app.api.store.apply_entitlement", lambda _db, change: entitlements.append(change)
    )
    client, written = _harness(monkeypatch, gateway)
    response = client.post(
        "/billing/store/play/purchase",
        json={"purchase_token": "token-x", "product_id": "badgeday.someone.invented"},
    )

    assert response.status_code == 200
    assert response.json()["entitled"] is False
    assert written == []
    assert entitlements == []
    assert gateway.acks == []


# --- The store reporting it ---------------------------------------------------


def test_notifications_are_refused_until_the_store_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unauthenticated endpoint that cannot check a signature must not accept anything."""
    client, written = _harness(monkeypatch, _ConfirmingGateway())
    assert client.post("/billing/store/play/notifications", content=b"{}").status_code == 503
    assert client.post("/billing/store/appstore/notifications", content=b"{}").status_code == 503
    assert written == []


def test_a_verified_notification_that_changes_nothing_is_still_answered_200(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pub/Sub redelivers anything it does not get a 2xx for.

    A price-change notification is nothing to do, not an error, and answering it with one
    buys an indefinite retry loop over a message that will never mean anything different.
    """
    client, written = _harness(
        monkeypatch,
        _ConfirmingGateway(),
        play_package_name="com.badgeday.app",
        play_service_account_json="{}",
        play_pubsub_audience="https://api.badgeday.com",
        play_pubsub_service_account="rtdn@badgeday.iam.gserviceaccount.com",
    )
    response = client.post("/billing/store/play/notifications", content=b"{}")

    assert response.status_code == 200
    assert written == []


def test_an_unverifiable_notification_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Forged(_ConfirmingGateway):
        def read_play_notification(self, *, payload: bytes, authorization: str):
            raise StoreVerificationError("bad oidc token")

    client, written = _harness(
        monkeypatch,
        _Forged(),
        play_package_name="com.badgeday.app",
        play_service_account_json="{}",
        play_pubsub_audience="https://api.badgeday.com",
        play_pubsub_service_account="rtdn@badgeday.iam.gserviceaccount.com",
    )
    response = client.post("/billing/store/play/notifications", content=b"{}")

    assert response.status_code == 400
    assert written == []
