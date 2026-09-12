"""The way through the gate: checkout, the billing portal, and Stripe's webhook.

Creating work is gated on entitlement (migration 0005), and a candidate cannot grant
themselves entitlement. These three endpoints are how entitlement is actually acquired and
managed — the candidate is sent to Stripe to pay, and Stripe tells us the result here.

The webhook is the only endpoint in the app that writes profiles, and it does so with a
service-role client rather than the caller's token, because its caller is Stripe, not a
signed-in candidate. That is a deliberate exception to the rule in storage/client.py, and
it is safe for the same reason the worker's use is: the write is not on behalf of a
candidate's identity, and the request is authenticated — here by Stripe's signature, which
`read_event` verifies before a single change is applied.
"""

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.api.deps import CurrentUserDep, DbDep, GatewayDep, ServiceDbDep, SettingsDep
from app.billing.gateway import WebhookVerificationError
from app.billing.module import (
    module_for_plan,
    module_for_stripe_price,
    price_id_for_plan,
)
from app.billing.plan import (
    CHECKOUT_MODE,
    PROMOTE_PLANS,
    LinkCustomer,
    Plan,
    plan_changes,
    stripe_price_id_from_event,
)
from app.billing.recruit_plan import (
    recruit_plan_changes,
    stripe_object_id,
    user_id_carried_on_object,
)
from app.storage.billing import (
    apply_change,
    customer_id_for,
    entitlement,
    user_id_for_customer,
)
from app.storage.entitlements import apply_entitlement, module_entitlement

logger = logging.getLogger(__name__)

router = APIRouter(tags=["billing"])


class StartCheckout(BaseModel):
    plan: Plan


class Redirect(BaseModel):
    url: str


@router.post("/billing/checkout")
def checkout(
    body: StartCheckout,
    user: CurrentUserDep,
    db: DbDep,
    service: ServiceDbDep,
    gateway: GatewayDep,
    settings: SettingsDep,
) -> Redirect:
    """Begin paying for a plan, and return the Stripe URL to send the candidate to."""
    price_id = price_id_for_plan(settings, body.plan)
    # Promote's readiness check is unchanged: secret + both Promote prices.
    # Recruit needs the secret and *its* price; a blank Recruit ID is not for sale.
    if body.plan in PROMOTE_PLANS:
        if not settings.stripe_configured:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Billing is not configured yet."
            )
    elif not settings.stripe_secret_key or not price_id:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Billing is not configured yet."
        )
    if not price_id:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Billing is not configured yet."
        )

    # Already holding this module must not start another charge. Recruit and
    # Promote are separate: a Recruit subscriber can still buy Promote.
    # past_due is still a live Stripe subscription — send them to the portal.
    buying = module_for_plan(body.plan)
    held = (
        module_entitlement(db, user.id, "recruit")
        if buying == "recruit"
        else entitlement(db, user.id)
    )
    if held.entitled or held.subscription_status in ("active", "past_due"):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "You already have a plan for this. Manage billing from your account.",
        )

    # Create the Stripe customer now, and record the link before returning, so the customer
    # id is on the profile before any webhook can fire. Subscription events carry only the
    # customer id; without this a subscription.created racing ahead of checkout.completed
    # would find no profile to update.
    customer_id = customer_id_for(db, user.id)
    if not customer_id:
        customer_id = gateway.ensure_customer(email=user.email, user_id=user.id)
        apply_change(service, LinkCustomer(user_id=user.id, customer_id=customer_id))

    url = gateway.start_checkout(
        mode=CHECKOUT_MODE[body.plan],
        price_id=price_id,
        customer_id=customer_id,
        client_reference_id=user.id,
        success_url=f"{settings.public_web_url}/?checkout=success",
        cancel_url=f"{settings.public_web_url}/?checkout=cancelled",
        metadata={"plan": body.plan, "price_id": price_id, "user_id": user.id},
    )
    return Redirect(url=url)


@router.post("/billing/portal")
def portal(
    user: CurrentUserDep,
    db: DbDep,
    gateway: GatewayDep,
    settings: SettingsDep,
) -> Redirect:
    """Open Stripe's billing portal, where the candidate manages or cancels their plan."""
    customer_id = customer_id_for(db, user.id)
    if not customer_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "There is no billing account to manage yet. Start a plan first.",
        )
    url = gateway.open_portal(
        customer_id=customer_id, return_url=f"{settings.public_web_url}/account"
    )
    return Redirect(url=url)


@router.post("/billing/webhook")
async def webhook(
    request: Request,
    service: ServiceDbDep,
    gateway: GatewayDep,
    settings: SettingsDep,
) -> dict:
    """Receive Stripe's account of what happened, and update entitlement to match.

    Unauthenticated by design — the caller is Stripe, and the signature is the credential.
    """
    payload = await request.body()
    signature = request.headers.get("stripe-signature", "")
    try:
        event = gateway.read_event(payload=payload, signature=signature)
    except WebhookVerificationError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature.") from exc

    now = datetime.now(UTC)
    price_id = stripe_price_id_from_event(event)
    module = module_for_stripe_price(settings, price_id)

    # Grant paths fail closed: a missing or unknown price must not fall
    # open to Promote plan_changes. Only a mapped Promote price writes
    # profiles; only a mapped Recruit price writes entitlements.
    # customer.subscription.deleted is the exception (BD-BILL-001): an
    # unmapped price still clears Promote for a known customer, and
    # never clears Recruit without a Recruit price signal.
    if module == "recruit":
        obj = event.get("data", {}).get("object", {}) or {}
        # subscription.created/updated carry no client_reference_id. Prefer
        # metadata.user_id (copied onto the subscription at checkout), then
        # the profile linked by stripe_customer_id — including after this
        # request's checkout.session.completed LinkCustomer, or the one
        # written when checkout started.
        user_id = user_id_carried_on_object(obj) or user_id_for_customer(
            service, stripe_object_id(obj.get("customer"))
        )
        for change in recruit_plan_changes(
            event, settings=settings, user_id=user_id, now=now
        ):
            if isinstance(change, LinkCustomer):
                apply_change(service, change)
            else:
                apply_entitlement(service, change)
        return {"received": True}

    if module == "promote":
        for change in plan_changes(
            event, pass_days=settings.intensive_pass_days, now=now
        ):
            apply_change(service, change)
        return {"received": True}

    if event.get("type") == "customer.subscription.deleted":
        _clear_promote_on_unmapped_delete(
            event, service=service, settings=settings, now=now
        )

    return {"received": True}


def _clear_promote_on_unmapped_delete(event: dict, *, service, settings, now: datetime) -> None:
    """BD-BILL-001 path 3: unmapped delete clears Promote for a known user only."""
    obj = event.get("data", {}).get("object", {}) or {}
    customer_id = stripe_object_id(obj.get("customer"))
    subscription_id = stripe_object_id(obj.get("id"))
    user_id = user_id_for_customer(service, customer_id)
    logger.info(
        "subscription.deleted with no mappable price_id "
        "customer=%s subscription=%s user=%s",
        customer_id,
        subscription_id,
        user_id,
    )
    if not user_id:
        return
    for change in plan_changes(event, pass_days=settings.intensive_pass_days, now=now):
        apply_change(service, change)
