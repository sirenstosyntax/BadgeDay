"""The parts of the Play gateway that do not need Google.

Verifying a push token against Google's keys cannot be tested here. Everything
between a fake publisher and the entitlement facts can: unwrapping the Pub/Sub
envelope, reading Google's timestamps, picking the expiry out of a subscription,
and the lookup-then-persist-then-acknowledge order. Those are places where a
quiet wrong answer becomes a wrong entitlement rather than an error anybody sees.

The timestamp one is the sharpest. Google emits nanosecond precision and
`datetime.fromisoformat` accepts six digits, so the obvious implementation returns None on
every real expiry Google sends — which reads downstream as "this purchase has no
paid-through date" and cuts off a candidate who has one.
"""

from datetime import UTC, datetime

import pytest

from app.billing.play_gateway import (
    PlayGateway,
    _decode_pubsub_envelope,
    _latest_expiry,
    _parse_rfc3339,
    acknowledge_already_done,
    persist_then_acknowledge,
)
from app.billing.store_gateway import StoreVerificationError
from app.config import Settings

# Test-only product ids. Not PLAY_PRODUCT_ID_* values and not a price.
_SUBSCRIPTION_ID = "test.monthly"
_PASS_ID = "test.pass"
_TOKEN = "purchase-token-abc"
_USER = "user-from-app"

# --- Google's timestamps -----------------------------------------------------


def test_nanosecond_precision_parses() -> None:
    """The format Google actually sends. fromisoformat alone rejects this."""
    parsed = _parse_rfc3339("2026-09-30T12:00:00.123456789Z")
    assert parsed == datetime(2026, 9, 30, 12, 0, 0, 123456, tzinfo=UTC)


def test_a_plain_zulu_timestamp_parses() -> None:
    assert _parse_rfc3339("2026-09-30T12:00:00Z") == datetime(2026, 9, 30, 12, tzinfo=UTC)


def test_an_explicit_offset_is_honoured() -> None:
    parsed = _parse_rfc3339("2026-09-30T12:00:00-07:00")
    assert parsed is not None
    assert parsed.utcoffset().total_seconds() == -7 * 3600


def test_a_timestamp_with_no_offset_is_treated_as_utc() -> None:
    """Naive would be worse than wrong: every later comparison against `now` would raise."""
    parsed = _parse_rfc3339("2026-09-30T12:00:00")
    assert parsed is not None and parsed.tzinfo is not None


def test_rubbish_is_none_rather_than_an_exception() -> None:
    """A malformed expiry must not take down a webhook the store will retry forever."""
    for value in ("", "not a date", None, 12345, "2026-13-45T99:99:99Z"):
        assert _parse_rfc3339(value) is None


# --- Which expiry counts ------------------------------------------------------


def test_the_furthest_line_item_wins() -> None:
    """An upgrade mid-period leaves two line items briefly.

    Taking the first would cut a candidate off at a date they have already paid past.
    """
    purchase = {
        "lineItems": [
            {"expiryTime": "2026-09-30T12:00:00Z"},
            {"expiryTime": "2026-10-31T12:00:00Z"},
        ]
    }
    assert _latest_expiry(purchase) == datetime(2026, 10, 31, 12, tzinfo=UTC)


def test_no_line_items_is_no_expiry() -> None:
    assert _latest_expiry({}) is None
    assert _latest_expiry({"lineItems": []}) is None


def test_an_unparseable_line_item_does_not_hide_a_good_one() -> None:
    purchase = {
        "lineItems": [
            {"expiryTime": "garbage"},
            {"expiryTime": "2026-10-31T12:00:00Z"},
        ]
    }
    assert _latest_expiry(purchase) == datetime(2026, 10, 31, 12, tzinfo=UTC)


# --- The Pub/Sub envelope -----------------------------------------------------


def test_the_envelope_unwraps_to_the_notification() -> None:
    import base64
    import json

    rtdn = {"packageName": "com.badgeday.app", "subscriptionNotification": {"version": "1.0"}}
    envelope = json.dumps(
        {"message": {"data": base64.b64encode(json.dumps(rtdn).encode()).decode()}}
    ).encode()

    assert _decode_pubsub_envelope(envelope) == rtdn


def test_already_acknowledged_is_not_a_failure() -> None:
    """A replayed report must not look like the purchase failed."""
    assert acknowledge_already_done(RuntimeError("The purchase has already been acknowledged."))
    assert not acknowledge_already_done(RuntimeError("quota exceeded"))


# --- Lookup, persist, acknowledge --------------------------------------------


class _PendingCall:
    def __init__(self, result=None, error: BaseException | None = None) -> None:
        self._result = result
        self._error = error

    def execute(self):
        if self._error is not None:
            raise self._error
        return self._result


class _FakePublisher:
    """The shape `PlayGateway` walks on `_androidpublisher()`. No network."""

    def __init__(self) -> None:
        self.lookups: list[tuple] = []
        self.acks: list[tuple] = []
        self.ack_error: BaseException | None = None
        self.subscription = {
            "subscriptionState": "SUBSCRIPTION_STATE_ACTIVE",
            "lineItems": [{"expiryTime": "2026-10-31T12:00:00Z"}],
            "externalAccountIdentifiers": {"obfuscatedExternalAccountId": "obfuscated-user"},
        }
        self.product = {
            "purchaseState": 0,
            "obfuscatedExternalAccountId": "obfuscated-user",
        }

    def purchases(self) -> "_FakePurchases":
        return _FakePurchases(self)


class _FakePurchases:
    def __init__(self, publisher: _FakePublisher) -> None:
        self._publisher = publisher

    def subscriptionsv2(self) -> "_FakeSubscriptionsV2":
        return _FakeSubscriptionsV2(self._publisher)

    def subscriptions(self) -> "_FakeSubscriptions":
        return _FakeSubscriptions(self._publisher)

    def products(self) -> "_FakeProducts":
        return _FakeProducts(self._publisher)


class _FakeSubscriptionsV2:
    def __init__(self, publisher: _FakePublisher) -> None:
        self._publisher = publisher

    def get(self, **kwargs):
        self._publisher.lookups.append(("subscriptionsv2.get", kwargs))
        return _PendingCall(self._publisher.subscription)


class _FakeSubscriptions:
    def __init__(self, publisher: _FakePublisher) -> None:
        self._publisher = publisher

    def acknowledge(self, **kwargs):
        self._publisher.acks.append(("subscriptions.acknowledge", kwargs))
        return _PendingCall(error=self._publisher.ack_error)


class _FakeProducts:
    def __init__(self, publisher: _FakePublisher) -> None:
        self._publisher = publisher

    def get(self, **kwargs):
        self._publisher.lookups.append(("products.get", kwargs))
        return _PendingCall(self._publisher.product)

    def acknowledge(self, **kwargs):
        self._publisher.acks.append(("products.acknowledge", kwargs))
        return _PendingCall(error=self._publisher.ack_error)


def _play_gateway(publisher: _FakePublisher | None = None) -> tuple[PlayGateway, _FakePublisher]:
    publisher = publisher or _FakePublisher()
    gateway = PlayGateway(
        Settings(
            play_package_name="com.badgeday.app",
            play_service_account_json="{}",
            play_pubsub_audience="https://example.test/play",
            play_pubsub_service_account="rtdn@example.test",
            play_product_id_monthly=_SUBSCRIPTION_ID,
        )
    )
    gateway._androidpublisher = lambda: publisher  # type: ignore[method-assign]
    return gateway, publisher


def test_successful_subscription_verify_acknowledges_after_persist() -> None:
    """The verify path looks up, then persist_then_acknowledge hits Play once.

    `_acknowledge` used to run inside `_subscription_facts` before the row was
    written. If that write then failed, Play would not auto-refund.
    """
    gateway, publisher = _play_gateway()
    persisted: list[object] = []

    facts = gateway.verify_play_purchase(
        purchase_token=_TOKEN, product_id=_SUBSCRIPTION_ID, user_id=_USER
    )

    assert facts.kind == "subscription"
    assert facts.state == "purchased"
    assert facts.user_id == _USER
    assert publisher.lookups == [
        (
            "subscriptionsv2.get",
            {"packageName": "com.badgeday.app", "token": _TOKEN},
        )
    ]
    assert publisher.acks == []

    persist_then_acknowledge(gateway, facts, lambda: persisted.append(facts))

    assert persisted == [facts]
    assert len(publisher.acks) == 1
    assert publisher.acks[0] == (
        "subscriptions.acknowledge",
        {
            "packageName": "com.badgeday.app",
            "subscriptionId": _SUBSCRIPTION_ID,
            "token": _TOKEN,
            "body": {},
        },
    )


def test_successful_pass_verify_acknowledges_after_persist() -> None:
    gateway, publisher = _play_gateway()
    persisted: list[object] = []

    facts = gateway.verify_play_purchase(
        purchase_token=_TOKEN, product_id=_PASS_ID, user_id=_USER
    )

    assert facts.kind == "pass"
    assert facts.state == "purchased"
    assert publisher.acks == []

    persist_then_acknowledge(gateway, facts, lambda: persisted.append(facts))

    assert persisted == [facts]
    assert publisher.acks == [
        (
            "products.acknowledge",
            {
                "packageName": "com.badgeday.app",
                "productId": _PASS_ID,
                "token": _TOKEN,
                "body": {},
            },
        )
    ]


def test_failed_persist_does_not_acknowledge() -> None:
    gateway, publisher = _play_gateway()

    facts = gateway.verify_play_purchase(
        purchase_token=_TOKEN, product_id=_SUBSCRIPTION_ID, user_id=_USER
    )

    def boom() -> None:
        raise RuntimeError("store_purchases write failed")

    with pytest.raises(RuntimeError, match="store_purchases"):
        persist_then_acknowledge(gateway, facts, boom)

    assert publisher.acks == []


def test_already_acknowledged_from_play_is_not_raised() -> None:
    """A replayed report must still persist; Play's 400 is success."""
    publisher = _FakePublisher()
    publisher.ack_error = RuntimeError("The purchase has already been acknowledged.")
    gateway, publisher = _play_gateway(publisher)
    persisted: list[object] = []

    facts = gateway.verify_play_purchase(
        purchase_token=_TOKEN, product_id=_SUBSCRIPTION_ID, user_id=_USER
    )
    persist_then_acknowledge(gateway, facts, lambda: persisted.append(facts))

    assert persisted == [facts]
    assert len(publisher.acks) == 1


def test_anything_that_is_not_an_envelope_is_a_verification_failure() -> None:
    """The endpoint is public, so all of these are ordinary things to receive."""
    for payload in (b"", b"not json", b"{}", b'{"message": {}}', b'{"message": {"data": "!!"}}'):
        with pytest.raises(StoreVerificationError):
            _decode_pubsub_envelope(payload)
