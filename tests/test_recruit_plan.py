"""Recruit Stripe events write entitlements(user, 'recruit'), never profiles."""

from datetime import UTC, datetime, timedelta

from app.billing.plan import (
    GrantPass,
    LinkCustomer,
    SetSubscription,
    plan_changes,
    stripe_price_id_from_event,
)
from app.billing.recruit_plan import recruit_entitlement_from_store, recruit_plan_changes
from app.billing.store import PurchaseFacts
from app.config import Settings
from app.storage.entitlements import GrantModulePass, SetModuleSubscription

NOW = datetime(2026, 1, 1, tzinfo=UTC)
USER = "44444444-4444-4444-4444-444444444444"
CUSTOMER = "cus_recruit"

SETTINGS = Settings(
    stripe_price_id_monthly="price_promote_mo",
    stripe_price_id_intensive_90day="price_promote_90",
    stripe_price_id_recruit_monthly="price_recruit_mo",
    stripe_price_id_recruit_intensive_90day="price_recruit_90",
    stripe_price_id_recruit_6month="price_recruit_6mo",
    stripe_price_id_recruit_annual="price_recruit_yr",
    intensive_pass_days=90,
    recruit_6month_pass_days=183,
)


def _recruit(event: dict, user_id: str | None = USER):
    return recruit_plan_changes(event, settings=SETTINGS, user_id=user_id, now=NOW)


def test_price_id_is_read_from_subscription_items() -> None:
    event = {
        "type": "customer.subscription.updated",
        "data": {
            "object": {
                "items": {"data": [{"price": {"id": "price_recruit_mo"}}]},
            }
        },
    }
    assert stripe_price_id_from_event(event) == "price_recruit_mo"


def test_price_id_is_read_from_checkout_metadata() -> None:
    event = {
        "type": "checkout.session.completed",
        "data": {"object": {"metadata": {"price_id": "price_recruit_6mo"}}},
    }
    assert stripe_price_id_from_event(event) == "price_recruit_6mo"


def test_a_recruit_6month_checkout_grants_183_days_on_recruit() -> None:
    changes = _recruit(
        {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": USER,
                    "customer": CUSTOMER,
                    "mode": "payment",
                    "payment_status": "paid",
                    "metadata": {"price_id": "price_recruit_6mo"},
                }
            },
        }
    )
    assert changes[0] == LinkCustomer(user_id=USER, customer_id=CUSTOMER)
    assert changes[1] == GrantModulePass(
        user_id=USER, module="recruit", expires_at=NOW + timedelta(days=183)
    )


def test_a_recruit_90day_checkout_uses_intensive_pass_days() -> None:
    changes = _recruit(
        {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": USER,
                    "customer": CUSTOMER,
                    "mode": "payment",
                    "payment_status": "paid",
                    "metadata": {"price_id": "price_recruit_90"},
                }
            },
        }
    )
    assert isinstance(changes[1], GrantModulePass)
    assert changes[1].expires_at == NOW + timedelta(days=90)


def test_a_paid_recruit_subscription_checkout_grants_the_recruit_row() -> None:
    """Do not wait on subscription.* — paid checkout must write entitlements."""
    changes = _recruit(
        {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": USER,
                    "customer": CUSTOMER,
                    "mode": "subscription",
                    "payment_status": "paid",
                    "metadata": {"price_id": "price_recruit_mo"},
                }
            },
        }
    )
    assert changes == [
        LinkCustomer(user_id=USER, customer_id=CUSTOMER),
        SetModuleSubscription(user_id=USER, module="recruit", status="active"),
    ]


def test_a_complete_recruit_subscription_checkout_grants_without_paid_status() -> None:
    changes = _recruit(
        {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": USER,
                    "customer": CUSTOMER,
                    "mode": "subscription",
                    "status": "complete",
                    "metadata": {"price_id": "price_recruit_yr"},
                }
            },
        }
    )
    assert changes == [
        LinkCustomer(user_id=USER, customer_id=CUSTOMER),
        SetModuleSubscription(user_id=USER, module="recruit", status="active"),
    ]


def test_an_unpaid_open_recruit_subscription_checkout_only_links() -> None:
    changes = _recruit(
        {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "client_reference_id": USER,
                    "customer": CUSTOMER,
                    "mode": "subscription",
                    "payment_status": "unpaid",
                    "status": "open",
                    "metadata": {"price_id": "price_recruit_mo"},
                }
            },
        }
    )
    assert changes == [LinkCustomer(user_id=USER, customer_id=CUSTOMER)]


def test_subscription_event_uses_metadata_user_id_when_webhook_passes_none() -> None:
    changes = _recruit(
        {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": CUSTOMER,
                    "status": "active",
                    "metadata": {"price_id": "price_recruit_mo", "user_id": USER},
                    "items": {"data": [{"price": {"id": "price_recruit_mo"}}]},
                }
            },
        },
        user_id=None,
    )
    assert changes == [
        SetModuleSubscription(user_id=USER, module="recruit", status="active")
    ]


def test_subscription_event_without_a_user_id_writes_nothing() -> None:
    assert (
        _recruit(
            {
                "type": "customer.subscription.updated",
                "data": {
                    "object": {
                        "customer": CUSTOMER,
                        "status": "active",
                        "items": {"data": [{"price": {"id": "price_recruit_mo"}}]},
                    }
                },
            },
            user_id=None,
        )
        == []
    )


def test_incomplete_subscription_does_not_cancel_recruit() -> None:
    """Same-second subscription.created(incomplete) must not undo a checkout grant."""
    assert (
        _recruit(
            {
                "type": "customer.subscription.created",
                "data": {
                    "object": {
                        "customer": CUSTOMER,
                        "status": "incomplete",
                        "items": {"data": [{"price": {"id": "price_recruit_mo"}}]},
                    }
                },
            }
        )
        == []
    )


def test_a_recruit_subscription_event_sets_the_recruit_row() -> None:
    changes = _recruit(
        {
            "type": "customer.subscription.updated",
            "data": {
                "object": {
                    "customer": CUSTOMER,
                    "status": "active",
                    "items": {"data": [{"price": {"id": "price_recruit_yr"}}]},
                }
            },
        }
    )
    assert changes == [
        SetModuleSubscription(user_id=USER, module="recruit", status="active")
    ]


def test_a_recruit_deleted_subscription_cancels_recruit() -> None:
    changes = _recruit(
        {
            "type": "customer.subscription.deleted",
            "data": {
                "object": {
                    "customer": CUSTOMER,
                    "items": {"data": [{"price": {"id": "price_recruit_mo"}}]},
                }
            },
        }
    )
    assert changes == [
        SetModuleSubscription(user_id=USER, module="recruit", status="canceled")
    ]


def test_a_promote_price_is_ignored_by_recruit_plan_changes() -> None:
    assert (
        _recruit(
            {
                "type": "customer.subscription.updated",
                "data": {
                    "object": {
                        "customer": CUSTOMER,
                        "status": "active",
                        "items": {"data": [{"price": {"id": "price_promote_mo"}}]},
                    }
                },
            }
        )
        == []
    )


def test_plan_changes_still_grants_a_promote_pass_without_a_price_id() -> None:
    """Legacy Promote webhooks do not name a price. That path must stay intact."""
    changes = plan_changes(
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
        pass_days=90,
        now=NOW,
    )
    assert changes == [
        LinkCustomer(user_id=USER, customer_id=CUSTOMER),
        GrantPass(customer_id=CUSTOMER, expires_at=NOW + timedelta(days=90)),
    ]


def test_plan_changes_still_mirrors_a_promote_subscription() -> None:
    (change,) = plan_changes(
        {
            "type": "customer.subscription.updated",
            "data": {"object": {"customer": CUSTOMER, "status": "active"}},
        },
        pass_days=90,
        now=NOW,
    )
    assert change == SetSubscription(customer_id=CUSTOMER, status="active")


def test_a_recruit_store_subscription_mirrors_onto_entitlements() -> None:
    expires = datetime(2026, 12, 1, tzinfo=UTC)
    changes = recruit_entitlement_from_store(
        PurchaseFacts(
            platform="play",
            product_id="badgeday.recruit.monthly",
            purchase_identifier="token-r",
            kind="subscription",
            state="purchased",
            expires_at=expires,
            user_id=USER,
        ),
        USER,
    )
    assert changes[0] == SetModuleSubscription(
        user_id=USER, module="recruit", status="active"
    )
    assert changes[1] == GrantModulePass(
        user_id=USER, module="recruit", expires_at=expires
    )


def test_a_recruit_store_pass_grants_only_the_expiry() -> None:
    expires = datetime(2026, 7, 1, tzinfo=UTC)
    (change,) = recruit_entitlement_from_store(
        PurchaseFacts(
            platform="play",
            product_id="badgeday.recruit.90day",
            purchase_identifier="token-p",
            kind="pass",
            state="purchased",
            expires_at=expires,
            user_id=USER,
        ),
        USER,
    )
    assert change == GrantModulePass(user_id=USER, module="recruit", expires_at=expires)
