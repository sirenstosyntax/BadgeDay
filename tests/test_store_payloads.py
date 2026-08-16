"""Reading each store's own vocabulary.

These payloads are transcribed from Google's RTDN reference and Apple's App Store Server
Notifications V2 documentation. They are the closest this suite can get to the real thing:
the container cannot talk to either store, and CI has no credentials by design, so the
shape of the payload is pinned here rather than discovered in production.

Two failure modes are worth stating, because both are silent:

  * A notification type missing from the table returns None, which reads in a log exactly
    like a type we deliberately ignore. So the ignored ones are asserted explicitly.
  * Play's test notification is sent the moment the Pub/Sub topic is configured. Treating
    it as a purchase would grant a subscription to nobody, on a row bound to nobody, at the
    exact moment somebody is watching the logs to see whether the wiring worked.
"""

from datetime import UTC, datetime

from app.billing.store_payloads import parse_appstore_payload, parse_play_notification

# --- Google Play -------------------------------------------------------------


def _play_subscription(notification_type: int) -> dict:
    return {
        "version": "1.0",
        "packageName": "com.badgeday.app",
        "eventTimeMillis": "1755300000000",
        "subscriptionNotification": {
            "version": "1.0",
            "notificationType": notification_type,
            "purchaseToken": "token-abc",
            "subscriptionId": "badgeday.promote.monthly",
        },
    }


def test_a_new_play_subscription_is_read_as_purchased() -> None:
    parsed = parse_play_notification(_play_subscription(4))
    assert parsed is not None
    assert parsed.state == "purchased"
    assert parsed.kind == "subscription"
    assert parsed.purchase_token == "token-abc"
    assert parsed.product_id == "badgeday.promote.monthly"


def test_a_play_renewal_is_read_as_purchased() -> None:
    parsed = parse_play_notification(_play_subscription(2))
    assert parsed is not None and parsed.state == "purchased"


def test_play_cancellation_leaves_the_paid_days_intact() -> None:
    """CANCELED means renewal is off, not that the subscription has ended today."""
    parsed = parse_play_notification(_play_subscription(3))
    assert parsed is not None and parsed.state == "auto_renew_off"


def test_play_grace_period_and_hold_are_distinguished() -> None:
    """Both are a failing card; only one still has the store serving the subscription."""
    assert parse_play_notification(_play_subscription(6)).state == "grace_period"
    assert parse_play_notification(_play_subscription(5)).state == "on_hold"


def test_a_play_revocation_is_a_refund_and_ends_access_now() -> None:
    parsed = parse_play_notification(_play_subscription(12))
    assert parsed is not None and parsed.state == "revoked"


def test_a_paused_play_subscription_stops_granting_access() -> None:
    parsed = parse_play_notification(_play_subscription(10))
    assert parsed is not None and parsed.state == "expired"


def test_a_play_price_change_says_nothing_about_access() -> None:
    """Deliberately ignored, and asserted so that 'ignored' cannot decay into 'forgotten'."""
    assert parse_play_notification(_play_subscription(8)) is None
    assert parse_play_notification(_play_subscription(11)) is None


def test_the_play_test_notification_is_not_a_purchase() -> None:
    """Sent the moment the Pub/Sub topic is wired up, before any product exists."""
    payload = {
        "version": "1.0",
        "packageName": "com.badgeday.app",
        "eventTimeMillis": "1755300000000",
        "testNotification": {"version": "1.0"},
    }
    assert parse_play_notification(payload) is None


def test_a_play_one_time_purchase_is_read_as_a_pass() -> None:
    payload = {
        "version": "1.0",
        "packageName": "com.badgeday.app",
        "oneTimeProductNotification": {
            "version": "1.0",
            "notificationType": 1,
            "purchaseToken": "token-pass",
            "sku": "badgeday.promote.intensive90",
        },
    }
    parsed = parse_play_notification(payload)
    assert parsed is not None
    assert parsed.kind == "pass"
    assert parsed.state == "purchased"


def test_a_play_notification_missing_its_token_grants_nothing() -> None:
    payload = _play_subscription(4)
    del payload["subscriptionNotification"]["purchaseToken"]
    assert parse_play_notification(payload) is None


# --- Apple -------------------------------------------------------------------

EXPIRES_MILLIS = 1790000000000
EXPIRES_AT = datetime.fromtimestamp(EXPIRES_MILLIS / 1000, tz=UTC)

SUBSCRIPTIONS = frozenset({"badgeday.promote.monthly"})


def _transaction(**overrides: object) -> dict:
    base: dict = {
        "originalTransactionId": "2000000012345678",
        "productId": "badgeday.promote.monthly",
        "type": "Auto-Renewable Subscription",
        "expiresDate": EXPIRES_MILLIS,
        "appAccountToken": "55555555-5555-5555-5555-555555555555",
    }
    base.update(overrides)
    return base


def test_a_new_apple_subscription_carries_its_expiry_and_its_candidate() -> None:
    facts = parse_appstore_payload(
        {"notificationType": "SUBSCRIBED", "subtype": "INITIAL_BUY"},
        _transaction(),
        subscription_products=SUBSCRIPTIONS,
    )
    assert facts is not None
    assert facts.state == "purchased"
    assert facts.platform == "appstore"
    assert facts.purchase_identifier == "2000000012345678"
    assert facts.expires_at == EXPIRES_AT
    assert facts.user_id == "55555555-5555-5555-5555-555555555555"


def test_an_unknown_apple_subtype_keeps_the_types_established_meaning() -> None:
    """Apple adds subtypes to existing types. A renewal must not stop granting access.

    Falling back to the unqualified type is what stops a new tag on DID_RENEW from turning
    a paying candidate's renewal into a notification we silently ignore.
    """
    facts = parse_appstore_payload(
        {"notificationType": "DID_RENEW", "subtype": "SOMETHING_NEW"},
        _transaction(),
        subscription_products=SUBSCRIPTIONS,
    )
    assert facts is not None and facts.state == "purchased"


def test_apple_auto_renew_off_is_not_a_revocation() -> None:
    facts = parse_appstore_payload(
        {"notificationType": "DID_CHANGE_RENEWAL_STATUS", "subtype": "AUTO_RENEW_DISABLED"},
        _transaction(),
        subscription_products=SUBSCRIPTIONS,
    )
    assert facts is not None
    assert facts.state == "auto_renew_off"
    assert facts.expires_at == EXPIRES_AT


def test_apple_failure_to_renew_splits_on_whether_there_is_a_grace_period() -> None:
    with_grace = parse_appstore_payload(
        {"notificationType": "DID_FAIL_TO_RENEW", "subtype": "GRACE_PERIOD"},
        _transaction(),
        subscription_products=SUBSCRIPTIONS,
    )
    without = parse_appstore_payload(
        {"notificationType": "DID_FAIL_TO_RENEW", "subtype": None},
        _transaction(),
        subscription_products=SUBSCRIPTIONS,
    )
    assert with_grace is not None and with_grace.state == "grace_period"
    assert without is not None and without.state == "on_hold"


def test_an_apple_refund_is_a_revocation() -> None:
    facts = parse_appstore_payload(
        {"notificationType": "REFUND", "subtype": None},
        _transaction(),
        subscription_products=SUBSCRIPTIONS,
    )
    assert facts is not None and facts.state == "revoked"


def test_apple_bookkeeping_notifications_say_nothing_about_access() -> None:
    for kind in ("CONSUMPTION_REQUEST", "PRICE_INCREASE", "DID_CHANGE_RENEWAL_PREF", "TEST"):
        assert (
            parse_appstore_payload(
                {"notificationType": kind, "subtype": None},
                _transaction(),
                subscription_products=SUBSCRIPTIONS,
            )
            is None
        )


def test_a_one_time_apple_product_is_a_pass_not_a_subscription() -> None:
    """The configured product list decides, because Apple's `type` is not always usable."""
    facts = parse_appstore_payload(
        {"notificationType": "ONE_TIME_CHARGE", "subtype": None},
        _transaction(
            productId="badgeday.promote.intensive90",
            type="Non-Consumable",
            expiresDate=None,
        ),
        subscription_products=SUBSCRIPTIONS,
    )
    assert facts is not None
    assert facts.kind == "pass"
    assert facts.expires_at is None


def test_an_apple_purchase_with_no_account_token_is_left_unattributed() -> None:
    """It updates an existing row by transaction id; it never invents a candidate."""
    facts = parse_appstore_payload(
        {"notificationType": "DID_RENEW", "subtype": None},
        _transaction(appAccountToken=""),
        subscription_products=SUBSCRIPTIONS,
    )
    assert facts is not None and facts.user_id is None
