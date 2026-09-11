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

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.api.deps import CurrentUserDep, DbDep, GatewayDep, ServiceDbDep, SettingsDep
from app.billing.gateway import WebhookVerificationError
from app.billing.module import (
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
from app.billing.recruit_plan import recruit_plan_changes
from app.storage.billing import apply_change, customer_id_for, user_id_for_customer
from app.storage.entitlements import apply_entitlement

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

    # Fail closed: a missing or unknown price must not fall open to Promote
    # plan_changes. Only a mapped Promote price writes profiles; only a
    # mapped Recruit price writes entitlements. Anything else is ack-and-ignore.
    if module == "recruit":
        obj = event.get("data", {}).get("object", {}) or {}
        user_id = (
            obj.get("client_reference_id")
            or (obj.get("metadata") or {}).get("user_id")
            or user_id_for_customer(service, obj.get("customer") or "")
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
