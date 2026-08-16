"""What a store purchase means for entitlement.

The store-side twin of test_billing.py, and it carries the same weight: these are the
functions that decide whether a candidate who paid can work, and whether one who stopped
paying still can. Neither store can be asked to resend a notification, so a wrong mapping
here is a wrong row that nothing later discovers.

The cases that matter most are the ones where "cancelled" does not mean "cut off". Turning
off auto-renew on the 3rd of a month paid through the 30th buys the rest of that month;
both stores keep serving it, and a mapping that revoked access on the spot would take
twenty-seven paid days away from someone who did nothing wrong. A refund is the one event
that genuinely ends access mid-period, and it is the only one allowed to clear the expiry.
"""

from datetime import UTC, datetime

from app.billing.store import (
    PurchaseFacts,
    RecordPurchase,
    SetPurchaseStatus,
    status_for,
    store_changes,
)

USER_ID = "55555555-5555-5555-5555-555555555555"
PAID_THROUGH = datetime(2026, 9, 30, tzinfo=UTC)


def _facts(state: str, **overrides: object) -> PurchaseFacts:
    base: dict = {
        "platform": "play",
        "product_id": "badgeday.promote.monthly",
        "purchase_identifier": "token-abc",
        "kind": "subscription",
        "state": state,
        "expires_at": PAID_THROUGH,
    }
    base.update(overrides)
    return PurchaseFacts(**base)


# --- The state table ---------------------------------------------------------


def test_a_live_purchase_grants_access() -> None:
    assert status_for("purchased") == "active"


def test_a_failing_card_does_not_grant_access_on_its_own() -> None:
    """0005's stance, applied to the stores: past_due is access withheld, not given.

    The candidate is not cut off by this — their paid-through date is what keeps them
    working, through the expiry clause in has_access. This only decides what happens once
    that date has passed, and at that point they genuinely have not paid.
    """
    assert status_for("grace_period") == "past_due"
    assert status_for("on_hold") == "past_due"


def test_turning_off_renewal_is_not_being_cut_off() -> None:
    """The status stops granting, and the expiry keeps serving the days already bought."""
    assert status_for("auto_renew_off") == "canceled"

    changes = store_changes(_facts("auto_renew_off"))
    assert changes[0].expires_at == PAID_THROUGH


def test_a_refund_ends_access_immediately() -> None:
    """The one case where the paid-through date must not be honoured."""
    assert status_for("revoked") == "canceled"

    change = store_changes(_facts("revoked", user_id=USER_ID))[0]
    assert isinstance(change, RecordPurchase)
    assert change.status == "canceled"
    assert change.expires_at is None


def test_an_unknown_state_withholds_access_rather_than_granting_it() -> None:
    """Same floor as an unmapped Stripe status, for the same reason: it is reversible.

    A state either store adds later must not silently grant a subscription. Being wrong in
    this direction costs a support email; being wrong in the other gives the product away.
    """
    assert status_for("something_google_invents_in_2027") == "canceled"  # type: ignore[arg-type]


# --- Which change is emitted -------------------------------------------------


def test_a_purchase_carrying_a_candidate_binds_the_row_to_them() -> None:
    change = store_changes(_facts("purchased", user_id=USER_ID))[0]
    assert isinstance(change, RecordPurchase)
    assert change.user_id == USER_ID
    assert change.status == "active"
    assert change.expires_at == PAID_THROUGH


def test_a_notification_without_a_candidate_updates_by_the_stores_own_identifier() -> None:
    """A renewal arriving months later has no session behind it and needs none.

    The row already knows whose purchase it is, which is exactly why the update is keyed on
    the store's identifier rather than on a user we would otherwise have to guess at.
    """
    change = store_changes(_facts("expired"))[0]
    assert isinstance(change, SetPurchaseStatus)
    assert change.purchase_identifier == "token-abc"
    assert change.platform == "play"
    assert change.status == "canceled"


def test_an_unattributable_purchase_is_never_guessed_at() -> None:
    """No user id in, no user id out — not the most recent signup, not a matching email.

    Attributing a purchase by inference hands one candidate's paid access to another, and
    the failure is silent on both sides: the payer sees a paywall, and a stranger gets a
    subscription neither of them can explain.
    """
    change = store_changes(_facts("purchased"))[0]
    assert isinstance(change, SetPurchaseStatus)
    assert not hasattr(change, "user_id")


def test_only_a_refund_clears_the_expiry() -> None:
    """The flag is what separates 'this event is silent about expiry' from 'end it now'."""
    assert store_changes(_facts("revoked"))[0].clear_expiry is True
    for quiet in ("expired", "auto_renew_off", "on_hold", "grace_period"):
        assert store_changes(_facts(quiet))[0].clear_expiry is False


def test_a_pass_and_a_subscription_travel_the_same_path() -> None:
    """The store is a different till, not a different product line."""
    change = store_changes(
        _facts("purchased", kind="pass", platform="appstore", user_id=USER_ID)
    )[0]
    assert isinstance(change, RecordPurchase)
    assert change.kind == "pass"
    assert change.platform == "appstore"
