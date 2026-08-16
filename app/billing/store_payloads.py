"""Translating each store's own vocabulary into ours.

Pure functions over already-verified, already-decoded payloads. Verification — Apple's JWS
chain, Google's Pub/Sub push token — lives in `store_gateway.py`; this file assumes it has
happened and does nothing but read fields and map names.

The split exists so the mapping can be tested exhaustively with no credentials. That
matters more here than almost anywhere else in the codebase: these tables are the
difference between a candidate who cancelled keeping the days they paid for and being cut
off on the spot, and there is no way to discover a wrong row from inside the app. The
store never tells you twice.

Both mappings are enumerated in full, including the cases that mean nothing for
entitlement, which return None. Writing them out is the point — a notification type that
is missing from the table is indistinguishable from one deliberately ignored, and the
first is a silent bug while the second is a decision.
"""

from datetime import UTC, datetime

from app.billing.store import PurchaseFacts, StoreState

# ---------------------------------------------------------------------------
# Google Play — Real-time Developer Notifications
# ---------------------------------------------------------------------------
# https://developer.android.com/google/play/billing/rtdn-reference
#
# Integers, not names, and the numbering has gaps. The names are kept in the comments
# because a bare `5` in a log is unreadable at the moment you most need to read it.
_PLAY_SUBSCRIPTION: dict[int, StoreState | None] = {
    1: "purchased",  # RECOVERED — came back from a failed payment
    2: "purchased",  # RENEWED
    3: "auto_renew_off",  # CANCELED — renewal off; the paid-through days are still owed
    4: "purchased",  # PURCHASED — a new subscription
    5: "on_hold",  # ON_HOLD — payment failed long enough that Play suspended it
    6: "grace_period",  # IN_GRACE_PERIOD — Play is retrying the card
    7: "purchased",  # RESTARTED — resubscribed before it lapsed
    8: None,  # PRICE_CHANGE_CONFIRMED — money, not access
    9: "purchased",  # DEFERRED — we pushed the next billing date out; still entitled
    # PAUSED is not a cancellation and not a lapse: the candidate asked Play to stop the
    # subscription for a while, and access ends when the pause begins. 'expired' is the
    # honest mapping — no access, nothing owed, and the RESTARTED notification that ends a
    # pause maps straight back to 'purchased'.
    10: "expired",  # PAUSED
    11: None,  # PAUSE_SCHEDULE_CHANGED — the pause moved; access is unaffected today
    12: "revoked",  # REVOKED — refunded or charged back; access ends immediately
    13: "expired",  # EXPIRED — ran its course
    20: None,  # PENDING_PURCHASE_CANCELED — a purchase that never completed
}

_PLAY_ONE_TIME: dict[int, StoreState | None] = {
    1: "purchased",  # PURCHASED
    # CANCELED here means a *pending* purchase (cash at a kiosk, a parent's approval) was
    # abandoned. Nothing was ever granted, so there is nothing to revoke — but if a row
    # exists from the pending state, it must not keep granting access.
    2: "expired",  # CANCELED
}


class PlayNotification:
    """The parts of an RTDN we act on.

    Deliberately not a PurchaseFacts: a Play notification does NOT carry the paid-through
    date or the account token. Both live on the other end of a Play Developer API call
    keyed on this purchase token, which is the gateway's job. Returning a half-filled
    PurchaseFacts here would invite a caller to write an entitlement row with a null expiry
    and cut off a candidate who has paid.
    """

    def __init__(
        self,
        *,
        purchase_token: str,
        product_id: str,
        kind: str,
        state: StoreState,
    ) -> None:
        self.purchase_token = purchase_token
        self.product_id = product_id
        self.kind = kind
        self.state = state

    def __repr__(self) -> str:  # pragma: no cover - diagnostics only
        return (
            f"PlayNotification(product_id={self.product_id!r}, kind={self.kind!r}, "
            f"state={self.state!r})"
        )


def parse_play_notification(decoded: dict) -> PlayNotification | None:
    """Read a decoded RTDN. None when it says nothing about entitlement.

    None covers three genuinely different cases, none of which is an error: a test
    notification (Play sends one when you configure the topic, and it must not be treated
    as a purchase), a notification type that does not move entitlement, and a shape we do
    not handle such as a voided-purchase notification.
    """
    if "testNotification" in decoded:
        return None

    subscription = decoded.get("subscriptionNotification")
    if isinstance(subscription, dict):
        state = _PLAY_SUBSCRIPTION.get(subscription.get("notificationType"))
        token = subscription.get("purchaseToken")
        product = subscription.get("subscriptionId")
        if state and token and product:
            return PlayNotification(
                purchase_token=token, product_id=product, kind="subscription", state=state
            )
        return None

    one_time = decoded.get("oneTimeProductNotification")
    if isinstance(one_time, dict):
        state = _PLAY_ONE_TIME.get(one_time.get("notificationType"))
        token = one_time.get("purchaseToken")
        product = one_time.get("sku")
        if state and token and product:
            return PlayNotification(
                purchase_token=token, product_id=product, kind="pass", state=state
            )
        return None

    return None


# ---------------------------------------------------------------------------
# Apple — App Store Server Notifications V2
# ---------------------------------------------------------------------------
# https://developer.apple.com/documentation/appstoreservernotifications
#
# Apple's payload carries the facts inline, so unlike Play there is no second call to make.
# Several types are qualified by a subtype, and the subtype is the whole meaning — a
# DID_CHANGE_RENEWAL_STATUS without it says only "something about renewal changed".
_APPLE: dict[tuple[str, str | None], StoreState | None] = {
    ("SUBSCRIBED", None): "purchased",  # covers both INITIAL_BUY and RESUBSCRIBE
    ("DID_RENEW", None): "purchased",
    # A renewal that succeeded after a failed one. Same outcome as any other renewal.
    ("DID_RENEW", "BILLING_RECOVERY"): "purchased",
    ("OFFER_REDEEMED", None): "purchased",
    ("ONE_TIME_CHARGE", None): "purchased",
    # Renewal switched off. Not a revocation — the candidate keeps the days already paid
    # for, and expiresDate on the transaction is what serves them.
    ("DID_CHANGE_RENEWAL_STATUS", "AUTO_RENEW_DISABLED"): "auto_renew_off",
    ("DID_CHANGE_RENEWAL_STATUS", "AUTO_RENEW_ENABLED"): "purchased",
    # The card failed. With a grace period Apple keeps serving the subscription while it
    # retries; without one it is straight into billing retry with no access.
    ("DID_FAIL_TO_RENEW", "GRACE_PERIOD"): "grace_period",
    ("DID_FAIL_TO_RENEW", None): "on_hold",
    ("GRACE_PERIOD_EXPIRED", None): "on_hold",
    ("EXPIRED", None): "expired",
    ("REFUND", None): "revoked",
    ("REVOKE", None): "revoked",  # family sharing withdrawn
    # Acknowledged and ignored: they change money, metadata or Apple's own bookkeeping,
    # never whether this candidate may open a practice session today.
    ("CONSUMPTION_REQUEST", None): None,
    ("DID_CHANGE_RENEWAL_PREF", None): None,
    ("PRICE_INCREASE", None): None,
    ("RENEWAL_EXTENDED", None): None,
    ("RENEWAL_EXTENSION", None): None,
    ("REFUND_DECLINED", None): None,
    ("REFUND_REVERSED", None): None,
    ("TEST", None): None,
}


def _apple_state(notification_type: str, subtype: str | None) -> StoreState | None:
    """Look the pair up, falling back to the unqualified type.

    Apple adds subtypes to existing types over time. Falling back means a new subtype on a
    type we already handle keeps its established meaning instead of vanishing — the
    failure mode that fallback avoids is a renewal that stops granting access because
    Apple started tagging it.
    """
    if (notification_type, subtype) in _APPLE:
        return _APPLE[(notification_type, subtype)]
    return _APPLE.get((notification_type, None))


def millis_to_datetime(value: object) -> datetime | None:
    """Apple's dates are milliseconds since the epoch, as a number."""
    if not isinstance(value, int | float):
        return None
    return datetime.fromtimestamp(value / 1000, tz=UTC)


def parse_appstore_payload(
    payload: dict, transaction: dict, *, subscription_products: frozenset[str] = frozenset()
) -> PurchaseFacts | None:
    """Build the facts from a verified notification and its decoded transaction.

    `payload` is the decoded signedPayload (notificationType, subtype). `transaction` is the
    decoded signedTransactionInfo, which carries the identifiers and the expiry. They arrive
    as two arguments because they are two separately signed blobs, and the gateway verifies
    them separately.

    `subscription_products` names which of our product ids are subscriptions. Apple's
    transaction has a `type` field, but it is absent on some notification shapes, so the
    configured product list is the reliable answer and the field is the fallback.
    """
    state = _apple_state(payload.get("notificationType", ""), payload.get("subtype"))
    if state is None:
        return None

    original_transaction_id = transaction.get("originalTransactionId")
    product_id = transaction.get("productId")
    if not (original_transaction_id and product_id):
        return None

    if product_id in subscription_products:
        kind = "subscription"
    else:
        kind = "subscription" if "Renewable" in str(transaction.get("type", "")) else "pass"

    return PurchaseFacts(
        platform="appstore",
        product_id=product_id,
        purchase_identifier=original_transaction_id,
        kind=kind,
        state=state,
        expires_at=millis_to_datetime(transaction.get("expiresDate")),
        # Set by the app at purchase time to the candidate's id. Apple passes it through
        # untouched, which is what lets a notification arriving months later still be
        # attributed. Absent on purchases made before the app started setting it, and on
        # some server-initiated events.
        user_id=transaction.get("appAccountToken") or None,
    )
