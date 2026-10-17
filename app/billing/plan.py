"""What a Stripe event means for a candidate's entitlement — as a pure decision.

This module never touches Stripe or the database. It takes an already-verified event
(the endpoint does the signature check) and returns the profile writes it implies, so the
one place where a mistake mis-grants access is a plain function with plain inputs that a
test can enumerate. Applying the writes, and refusing an unverified event, live elsewhere.

Two ways to be entitled, matching `has_access` in migration 0005:

  * a monthly subscription, whose Stripe status we mirror onto profiles; only 'active'
    grants access (see the status map below), and
  * a one-time intensive pass, which sets an access_expires_at in the future.

The profiles.subscription_status column allows exactly {none, active, past_due, canceled}
(0001). Stripe's subscription status has more values than that, so every one of them is
mapped here deliberately rather than written through — an unmapped Stripe status must not
reach the database and fail its check constraint inside a webhook we have to answer 200.
"""

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel

# plan name (what the web app asks for) -> how Stripe should charge for it. Subscription is
# recurring; a pass is a single payment. The price ids themselves come from settings,
# never from the client — the client names a plan, not a price.
Plan = Literal[
    "monthly",
    "intensive_90day",
    "recruit_monthly",
    "recruit_intensive_90day",
    "recruit_6month",
    "recruit_annual",
]
PROMOTE_PLANS: frozenset[Plan] = frozenset({"monthly", "intensive_90day"})
RECRUIT_PLANS: frozenset[Plan] = frozenset(
    {
        "recruit_monthly",
        "recruit_intensive_90day",
        "recruit_6month",
        "recruit_annual",
    }
)
CHECKOUT_MODE: dict[Plan, Literal["subscription", "payment"]] = {
    "monthly": "subscription",
    "intensive_90day": "payment",
    "recruit_monthly": "subscription",
    "recruit_intensive_90day": "payment",
    "recruit_6month": "payment",
    "recruit_annual": "subscription",
}

# Stripe subscription.status -> our four-value column. trialing counts as active because a
# trial is access we chose to give; the past_due family is access withheld pending a card
# fix (0005 explains why that is the reversible direction); everything terminal is canceled.
# incomplete is a checkout whose first payment never cleared — no access was ever owed, so
# it collapses to canceled rather than inventing a fifth state.
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


class LinkCustomer(BaseModel):
    """Bind a Stripe customer to a candidate. The only event that carries both ids."""

    kind: Literal["link"] = "link"
    user_id: str
    customer_id: str


class SetSubscription(BaseModel):
    """Mirror a subscription's status onto the candidate identified by their customer id."""

    kind: Literal["subscription"] = "subscription"
    customer_id: str
    status: str


class GrantPass(BaseModel):
    """Extend access to a fixed expiry — the one-time intensive pass."""

    kind: Literal["pass"] = "pass"
    customer_id: str
    expires_at: datetime


Change = LinkCustomer | SetSubscription | GrantPass


def checkout_session_discounted(session: dict) -> bool:
    """True when the session carries a promotion or coupon.

    ``total_details.amount_discount > 0`` is a partial or full reduction.
    A non-empty ``discounts`` list counts even when the amount is absent:
    the code was applied. An empty list and a zero amount do not.
    """
    details = session.get("total_details")
    if isinstance(details, dict):
        amount = details.get("amount_discount")
        if type(amount) in (int, float) and amount > 0:
            return True
    discounts = session.get("discounts")
    return isinstance(discounts, list) and len(discounts) > 0


def discounted_checkout_must_not_grant(event: dict, *, module: str | None) -> bool:
    """Fail closed: a discounted checkout grants nothing unless the price is Recruit.

    Promote, and any price that does not map to Recruit, must not be entitled
    from a reduced checkout. The webhook acknowledges the event and writes
    nothing. A Recruit price is unchanged: the promotion is the product.
    """
    if event.get("type") != "checkout.session.completed" or module == "recruit":
        return False
    session = (event.get("data") or {}).get("object") or {}
    if not isinstance(session, dict):
        return False
    return checkout_session_discounted(session)


def checkout_session_entitles(session: dict) -> bool:
    """Whether a checkout.session.completed should grant the purchased access.

    Full price and a partial discount both arrive as payment_status ``paid``.
    A 100% promotion completes with ``no_payment_required``, and only once
    ``status`` is ``complete``. ``unpaid`` is an async method that has not
    cleared, so it does not grant access even when status is complete.
    A paid session that omits status still grants: the event type is already
    checkout.session.completed.
    """
    payment = session.get("payment_status")
    status = session.get("status")
    if payment == "unpaid":
        return False
    if status not in (None, "complete"):
        return False
    if payment == "paid":
        return True
    if payment == "no_payment_required":
        return status == "complete"
    return False


def _subscription_status(stripe_status: str) -> str:
    # An unknown status is treated as no access rather than passed through: a value Stripe
    # adds later must not silently grant entitlement, and it cannot be written to the column
    # anyway. canceled is the safe floor — it withholds access and is reversible by the next
    # real event.
    return _SUBSCRIPTION_STATUS.get(stripe_status, "canceled")


def plan_changes(event: dict, *, pass_days: int, now: datetime) -> list[Change]:
    """The profile writes a verified Stripe event implies. Empty for events we don't act on.

    Only the handful of event types that change entitlement are acted on; anything else is
    acknowledged and ignored, so Stripe sending more event types than we subscribed to is
    harmless rather than an error.
    """
    kind = event.get("type", "")
    obj = event.get("data", {}).get("object", {})

    if kind == "checkout.session.completed":
        return _from_checkout(obj, pass_days=pass_days, now=now)

    if kind in ("customer.subscription.created", "customer.subscription.updated"):
        customer_id = obj.get("customer")
        status = obj.get("status")
        if customer_id and status:
            return [SetSubscription(customer_id=customer_id, status=_subscription_status(status))]
        return []

    if kind == "customer.subscription.deleted":
        # Promote profiles write. The webhook calls this for a mapped Promote
        # price, and (BD-BILL-001) for an unmapped delete when the Stripe
        # customer maps to a known user. It does not clear Recruit.
        customer_id = obj.get("customer")
        if customer_id:
            return [SetSubscription(customer_id=customer_id, status="canceled")]
        return []

    return []


def stripe_price_id_from_event(event: dict) -> str:
    """The price Stripe charged, if the event names one.

    Checkout sessions do not include line items unless expanded, so the id we
    wrote onto session / subscription metadata is the reliable checkout path.
    Subscription events carry items.data[].price.id. Blank IDs are ignored —
    they are placeholders, not a shared product.
    """
    obj = event.get("data", {}).get("object", {}) or {}
    for candidate in (
        _price_id_from_items(obj.get("items")),
        _price_id_from_items(obj.get("lines")),
        (obj.get("metadata") or {}).get("price_id"),
    ):
        if candidate:
            return str(candidate)
    return ""


def _price_id_from_items(items: object) -> str:
    if not isinstance(items, dict):
        return ""
    for item in items.get("data") or []:
        if not isinstance(item, dict):
            continue
        price = item.get("price")
        if isinstance(price, str) and price:
            return price
        if isinstance(price, dict) and price.get("id"):
            return str(price["id"])
    return ""


def _from_checkout(session: dict, *, pass_days: int, now: datetime) -> list[Change]:
    user_id = session.get("client_reference_id")
    customer_id = session.get("customer")
    if not (user_id and customer_id):
        # Without both ids we cannot attribute the payment to a candidate. Better to no-op
        # and let a human notice an un-linked payment than to guess whose account to credit.
        return []

    changes: list[Change] = [LinkCustomer(user_id=user_id, customer_id=customer_id)]

    # A one-time pass is mode 'payment'; a subscription's access arrives later on its own
    # subscription.* events, so a subscription checkout only links the customer here.
    if session.get("mode") == "payment" and checkout_session_entitles(session):
        changes.append(
            GrantPass(customer_id=customer_id, expires_at=now + timedelta(days=pass_days))
        )

    return changes
