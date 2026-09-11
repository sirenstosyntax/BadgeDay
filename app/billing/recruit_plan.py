"""What a Stripe event means for Recruit entitlement — as a pure decision.

Sibling of `plan.plan_changes`. Promote still writes profiles; Recruit writes
`entitlements(user, 'recruit')`. A Recruit price must never emit a profiles
subscription or pass, and a Promote price must never emit a Recruit row.

`user_id` is resolved by the webhook (checkout client_reference_id, subscription
metadata, or profiles.stripe_customer_id) and passed in. This module does not
guess whose account to credit.
"""

from datetime import datetime, timedelta

from app.billing.module import (
    pass_days_for_plan,
    plan_for_stripe_price,
)
from app.billing.plan import (
    LinkCustomer,
    Plan,
    stripe_price_id_from_event,
)
from app.billing.store import PurchaseFacts, status_for
from app.config import Settings
from app.storage.entitlements import (
    ClearModulePass,
    EntitlementChange,
    GrantModulePass,
    SetModuleSubscription,
)

# Same Stripe status map as plan._SUBSCRIPTION_STATUS — duplicated so a Recruit
# event cannot inherit a profiles write by calling plan_changes.
_SUBSCRIPTION_STATUS: dict[str, str] = {
    "trialing": "active",
    "active": "active",
    "past_due": "past_due",
    "unpaid": "past_due",
    "canceled": "canceled",
    "incomplete": "canceled",
    "incomplete_expired": "canceled",
    "paused": "canceled",
}

RecruitChange = LinkCustomer | EntitlementChange


def recruit_plan_changes(
    event: dict,
    *,
    settings: Settings,
    user_id: str | None,
    now: datetime,
) -> list[RecruitChange]:
    """The Recruit writes a verified Stripe event implies. Empty if not Recruit.

    A missing user id on a subscription event yields no entitlement write: we
    cannot attribute it. Checkout still links the customer when both ids exist.
    """
    price_id = stripe_price_id_from_event(event)
    plan = plan_for_stripe_price(settings, price_id)
    if plan is None or not plan.startswith("recruit_"):
        return []

    kind = event.get("type", "")
    obj = event.get("data", {}).get("object", {}) or {}

    if kind == "checkout.session.completed":
        return _from_checkout(obj, plan=plan, user_id=user_id, settings=settings, now=now)

    status = _subscription_status(obj.get("status", ""))
    if kind in ("customer.subscription.created", "customer.subscription.updated"):
        if not user_id or not obj.get("status"):
            return []
        return [
            SetModuleSubscription(user_id=user_id, module="recruit", status=status)
        ]

    if kind == "customer.subscription.deleted":
        if not user_id:
            return []
        return [
            SetModuleSubscription(user_id=user_id, module="recruit", status="canceled")
        ]

    return []


def _from_checkout(
    session: dict,
    *,
    plan: Plan,
    user_id: str | None,
    settings: Settings,
    now: datetime,
) -> list[RecruitChange]:
    resolved_user = user_id or session.get("client_reference_id")
    customer_id = session.get("customer")
    if not (resolved_user and customer_id):
        return []

    changes: list[RecruitChange] = [
        LinkCustomer(user_id=resolved_user, customer_id=customer_id)
    ]

    if session.get("mode") == "payment" and session.get("payment_status") == "paid":
        days = pass_days_for_plan(settings, plan)
        if days:
            changes.append(
                GrantModulePass(
                    user_id=resolved_user,
                    module="recruit",
                    expires_at=now + timedelta(days=days),
                )
            )

    return changes


def _subscription_status(stripe_status: str) -> str:
    return _SUBSCRIPTION_STATUS.get(stripe_status, "canceled")


def recruit_entitlement_from_store(
    facts: PurchaseFacts, user_id: str
) -> list[EntitlementChange]:
    """Mirror a verified Play / App Store purchase onto entitlements(user, 'recruit')."""
    status = status_for(facts.state)
    revoked = facts.state == "revoked"
    changes: list[EntitlementChange] = []

    if facts.kind == "subscription":
        changes.append(
            SetModuleSubscription(user_id=user_id, module="recruit", status=status)
        )
        if revoked:
            changes.append(ClearModulePass(user_id=user_id, module="recruit"))
        elif facts.expires_at is not None:
            changes.append(
                GrantModulePass(
                    user_id=user_id, module="recruit", expires_at=facts.expires_at
                )
            )
        return changes

    if revoked or facts.state == "expired":
        changes.append(ClearModulePass(user_id=user_id, module="recruit"))
        return changes

    if facts.expires_at is not None:
        changes.append(
            GrantModulePass(
                user_id=user_id, module="recruit", expires_at=facts.expires_at
            )
        )
    return changes
