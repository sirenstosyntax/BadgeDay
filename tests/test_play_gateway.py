"""The parts of the Play gateway that do not need Google.

Verifying a push token and calling the Developer API cannot be tested here. Everything
between them can: unwrapping the Pub/Sub envelope, reading Google's timestamps, and picking
the expiry out of a subscription. All three are places where a quiet wrong answer becomes a
wrong entitlement rather than an error anybody sees.

The timestamp one is the sharpest. Google emits nanosecond precision and
`datetime.fromisoformat` accepts six digits, so the obvious implementation returns None on
every real expiry Google sends — which reads downstream as "this purchase has no
paid-through date" and cuts off a candidate who has one.
"""

from datetime import UTC, datetime

import pytest

from app.billing.play_gateway import (
    _decode_pubsub_envelope,
    _latest_expiry,
    _parse_rfc3339,
)
from app.billing.store_gateway import StoreVerificationError

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


def test_anything_that_is_not_an_envelope_is_a_verification_failure() -> None:
    """The endpoint is public, so all of these are ordinary things to receive."""
    for payload in (b"", b"not json", b"{}", b'{"message": {}}', b'{"message": {"data": "!!"}}'):
        with pytest.raises(StoreVerificationError):
            _decode_pubsub_envelope(payload)
