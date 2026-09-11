"""What a Stripe event means for Recruit entitlement — as a pure decision.

Sibling of `plan.plan_changes`. Promote still writes profiles; Recruit writes
`entitlements(user, 'recruit')`. A Recruit price must never emit a profiles
subscription or pass, and a Promote price must never emit a Recruit row.

`user_id` is resolved by the webhook — checkout `client_reference_id`,
subscription `metadata.user_id`, or `profiles.stripe_customer_id` after
link — and passed in. This module does not look up profiles. It will still
use an id the event itself carries if the webhook passed none.
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


def stripe_object_id(value: object) -> str:
    """Stripe id whether the field is a string or an expanded object."""
    if isinstance(value, str) and value:
        return value
    if isinstance(value, dict):
        ident = value.get("id")
        if isinstance(ident, str) and ident:
            return ident
    return ""


def user_id_carried_on_object(obj: dict) -> str | None:
    """user_id the Stripe object itself names — checkout ref or metadata.

    Does not look up `profiles.stripe_customer_id`. The webhook does that
    after this returns None.
    """
    metadata = obj.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
    for candidate in (obj.get("client_reference_id"), metadata.get("user_id")):
        if isinstance(candidate, str) and candidate:
            return candidate
    return None


def recruit_plan_changes(
    event: dict,
    *,
    settings: Settings,
    user_id: str | None,
    now: datetime,
) -> list[RecruitChange]:
    """The Recruit writes a verified Stripe event implies. Empty if not Recruit.

    A missing user id on a subscription event yields no entitlement write: we
    cannot attribute it. Checkout links the customer when both ids exist, and
    a paid or complete subscription checkout also writes the Recruit row —
    access must not wait solely on `subscription.*`.
    """
    price_id = stripe_price_id_from_event(event)
    plan = plan_for_stripe_price(settings, price_id)
    if plan is None or not plan.startswith("recruit_"):
        return []

    kind = event.get("type", "")
    obj = event.get("data", {}).get("object", {}) or {}
    resolved_user = user_id or user_id_carried_on_object(obj)

    if kind == "checkout.session.completed":
        return _from_checkout(
            obj, plan=plan, user_id=resolved_user, settings=settings, now=now
        )

    stripe_status = obj.get("status", "")
    status = _subscription_status(stripe_status)
    if kind in ("customer.subscription.created", "customer.subscription.updated"):
        if not resolved_user or not stripe_status:
            return []
        # incomplete means the first invoice has not cleared. Writing canceled
        # here would undo a same-second checkout.session.completed grant.
        if stripe_status == "incomplete":
            return []
        return [
            SetModuleSubscription(user_id=resolved_user, module="recruit", status=status)
        ]

    if kind == "customer.subscription.deleted":
        if not resolved_user:
            return []
        return [
            SetModuleSubscription(user_id=resolved_user, module="recruit", status="canceled")
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
    resolved_user = user_id or user_id_carried_on_object(session)
    customer_id = stripe_object_id(session.get("customer"))
    if not (resolved_user and customer_id):
        return []

    changes: list[RecruitChange] = [
        LinkCustomer(user_id=resolved_user, customer_id=customer_id)
    ]

    paid = session.get("payment_status") == "paid"
    complete = session.get("status") == "complete"

    if session.get("mode") == "payment" and paid:
        days = pass_days_for_plan(settings, plan)
        if days:
            changes.append(
                GrantModulePass(
                    user_id=resolved_user,
                    module="recruit",
                    expires_at=now + timedelta(days=days),
                )
            )

    # Promote still waits on subscription.* for monthly access. Recruit must
    # not: production paid monthly linked the customer and left entitlements
    # empty when those events were missing or unordered.
    if session.get("mode") == "subscription" and (paid or complete):
        changes.append(
            SetModuleSubscription(
                user_id=resolved_user, module="recruit", status="active"
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
