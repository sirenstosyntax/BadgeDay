"""What a Stripe event means for entitlement — the one place a mistake mis-grants access.

The function is pure, so every case it has to get right is a plain input here: which events
grant a pass, which only link a customer, which Stripe statuses count as access, and which
events it must ignore rather than act on. If this file is thorough, the webhook cannot
quietly hand out access, because the webhook does nothing this function did not decide.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.billing.plan import (
    GrantPass,
    LinkCustomer,
    SetSubscription,
    plan_changes,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)
USER = "44444444-4444-4444-4444-444444444444"
CUSTOMER = "cus_test123"


def _changes(event: dict) -> list:
    return plan_changes(event, pass_days=90, now=NOW)


# --- Checkout ----------------------------------------------------------------


def test_a_paid_pass_checkout_links_the_customer_and_grants_the_pass() -> None:
    changes = _changes(
        {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": USER,
                    "customer": CUSTOMER,
                    "mode": "payment",
                    "payment_status": "paid",
                }
            },
        }
    )
    assert changes == [
        LinkCustomer(user_id=USER, customer_id=CUSTOMER),
        GrantPass(customer_id=CUSTOMER, expires_at=NOW + timedelta(days=90)),
    ]


def test_the_pass_length_is_the_configured_number_of_days() -> None:
    (_, grant) = plan_changes(
        {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": USER,
                    "customer": CUSTOMER,
                    "mode": "payment",
                    "payment_status": "paid",
                }
            },
        },
        pass_days=30,
        now=NOW,
    )
    assert grant.expires_at == NOW + timedelta(days=30)


def test_a_subscription_checkout_only_links_the_customer() -> None:
    """A subscription's access arrives on its own subscription.* events, not here."""
    changes = _changes(
        {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": USER,
                    "customer": CUSTOMER,
                    "mode": "subscription",
                    "payment_status": "paid",
                }
            },
        }
    )
    assert changes == [LinkCustomer(user_id=USER, customer_id=CUSTOMER)]


def test_an_unpaid_pass_checkout_grants_nothing_beyond_the_link() -> None:
    changes = _changes(
        {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": USER,
                    "customer": CUSTOMER,
                    "mode": "payment",
                    "payment_status": "unpaid",
                }
            },
        }
    )
    assert changes == [LinkCustomer(user_id=USER, customer_id=CUSTOMER)]


@pytest.mark.parametrize(
    "obj",
    [
        {"customer": CUSTOMER, "mode": "payment", "payment_status": "paid"},  # no user
        {"client_reference_id": USER, "mode": "payment", "payment_status": "paid"},  # no cust
    ],
)
def test_a_checkout_missing_an_id_is_not_attributed_to_anyone(obj: dict) -> None:
    """Without both ids the payment cannot be credited to a candidate — no-op, don't guess."""
    assert _changes({"type": "checkout.session.completed", "data": {"object": obj}}) == []


# --- Subscription lifecycle --------------------------------------------------


@pytest.mark.parametrize(
    ("stripe_status", "expected"),
    [
        ("trialing", "active"),
        ("active", "active"),
        ("past_due", "past_due"),
        ("unpaid", "past_due"),
        ("canceled", "canceled"),
        ("incomplete", "canceled"),
        ("incomplete_expired", "canceled"),
        ("paused", "canceled"),
        ("some_status_stripe_adds_in_2027", "canceled"),
    ],
)
def test_every_stripe_status_maps_to_a_column_value(stripe_status: str, expected: str) -> None:
    (change,) = _changes(
        {
            "type": "customer.subscription.updated",
            "data": {"object": {"customer": CUSTOMER, "status": stripe_status}},
        }
    )
    assert change == SetSubscription(customer_id=CUSTOMER, status=expected)


def test_a_created_subscription_sets_status_too() -> None:
    (change,) = _changes(
        {
            "type": "customer.subscription.created",
            "data": {"object": {"customer": CUSTOMER, "status": "active"}},
        }
    )
    assert change == SetSubscription(customer_id=CUSTOMER, status="active")


def test_a_deleted_subscription_cancels() -> None:
    (change,) = _changes(
        {
            "type": "customer.subscription.deleted",
            "data": {"object": {"customer": CUSTOMER, "status": "active"}},
        }
    )
    assert change == SetSubscription(customer_id=CUSTOMER, status="canceled")


# --- Everything else ---------------------------------------------------------


@pytest.mark.parametrize(
    "kind",
    [
        "invoice.paid",
        "payment_intent.succeeded",
        "customer.updated",
        "charge.refunded",
    ],
)
def test_an_event_we_do_not_act_on_changes_nothing(kind: str) -> None:
    assert _changes({"type": kind, "data": {"object": {"customer": CUSTOMER}}}) == []
