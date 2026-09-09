"""The second and third tills: purchases made inside the Android and iOS apps.

`api/billing.py` is the Stripe route and is unchanged by any of this. These endpoints are
its store-side counterpart, and they come in two kinds:

**The app reports its own purchase** (`/billing/store/{platform}/purchase`). Authenticated
as the candidate. It exists so the unlock is immediate: a store notification can be seconds
or minutes behind the purchase, and a candidate who has just paid should not be looking at
a paywall while it catches up. The client tells us *what to check*, never what to believe —
the token goes straight to the store's own API, and a purchase the store does not confirm
grants nothing.

**The store reports it** (`/billing/store/{platform}/notifications`). Unauthenticated, for
the same reason the Stripe webhook is: the caller is Google or Apple, and the signature is
the credential. This is the path that carries renewals, cancellations, refunds and
expiries — everything that happens after the one moment the app was watching.

Both paths converge on the same two pure functions and the same table, so a purchase
recorded by the app and the notification that follows it cannot disagree: the notification
updates the row the app wrote, keyed on the store's own identifier.
"""

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.api.deps import CurrentUserDep, ServiceDbDep, SettingsDep, StoreGatewayDep
from app.billing.play_gateway import persist_then_acknowledge
from app.billing.store import PurchaseFacts, store_changes
from app.billing.store_gateway import StoreNotConfigured, StoreVerificationError
from app.storage.store import apply_store_change

router = APIRouter(tags=["billing"])


class PlayPurchase(BaseModel):
    purchase_token: str
    product_id: str


class AppStorePurchase(BaseModel):
    transaction_id: str


class Unlocked(BaseModel):
    """What the app should do next. `entitled` is what the paywall actually reads."""

    entitled: bool
    product_id: str


@router.post("/billing/store/play/purchase")
def play_purchase(
    body: PlayPurchase,
    user: CurrentUserDep,
    service: ServiceDbDep,
    gateway: StoreGatewayDep,
) -> Unlocked:
    """Confirm and record a Play Billing purchase the Android app has just completed."""
    try:
        facts = gateway.verify_play_purchase(
            purchase_token=body.purchase_token,
            product_id=body.product_id,
            user_id=user.id,
        )
    except StoreNotConfigured as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Play billing is not configured yet."
        ) from exc
    except StoreVerificationError as exc:
        # Not a server error. The overwhelmingly likely cause is a token for a purchase
        # that did not complete, and the candidate should be told that rather than shown a
        # crash — but nothing is granted on it either way.
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            "Google could not confirm that purchase.",
        ) from exc

    _persist_play_purchase(service, gateway, facts)
    return Unlocked(entitled=facts.state == "purchased", product_id=facts.product_id)


@router.post("/billing/store/appstore/purchase")
def appstore_purchase(
    body: AppStorePurchase,
    user: CurrentUserDep,
    service: ServiceDbDep,
    gateway: StoreGatewayDep,
) -> Unlocked:
    """Confirm and record a StoreKit purchase the iOS app has just completed."""
    try:
        facts = gateway.verify_appstore_purchase(
            transaction_id=body.transaction_id, user_id=user.id
        )
    except StoreNotConfigured as exc:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "App Store billing is not configured yet."
        ) from exc
    except StoreVerificationError as exc:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            "Apple could not confirm that purchase.",
        ) from exc

    for change in store_changes(facts):
        apply_store_change(service, change)

    return Unlocked(entitled=facts.state == "purchased", product_id=facts.product_id)


@router.post("/billing/store/play/notifications")
async def play_notifications(
    request: Request,
    service: ServiceDbDep,
    gateway: StoreGatewayDep,
    settings: SettingsDep,
) -> dict:
    """Google's account of what happened to a purchase after it was made.

    Answers 200 for anything it successfully verified, including notifications that change
    no entitlement. Pub/Sub redelivers anything it does not get a 2xx for, with backoff,
    for as long as the subscription's retention allows — so a notification we merely have
    nothing to do about must not be answered with an error.
    """
    if not settings.play_configured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Play billing is not configured yet."
        )

    payload = await request.body()
    try:
        facts = gateway.read_play_notification(
            payload=payload, authorization=request.headers.get("authorization", "")
        )
    except (StoreVerificationError, StoreNotConfigured) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid notification.") from exc

    if facts is None:
        return {"received": True}

    _persist_play_purchase(service, gateway, facts)
    return {"received": True}


@router.post("/billing/store/appstore/notifications")
async def appstore_notifications(
    request: Request,
    service: ServiceDbDep,
    gateway: StoreGatewayDep,
    settings: SettingsDep,
) -> dict:
    """Apple's account of the same. Same contract, different signature scheme."""
    if not settings.appstore_configured:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "App Store billing is not configured yet."
        )

    payload = await request.body()
    try:
        facts = gateway.read_appstore_notification(payload=payload)
    except (StoreVerificationError, StoreNotConfigured) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid notification.") from exc

    if facts is None:
        return {"received": True}

    for change in store_changes(facts):
        apply_store_change(service, change)
    return {"received": True}


def _persist_play_purchase(service, gateway, facts: PurchaseFacts) -> None:
    """Record the verified purchase, then acknowledge. Ack-before-write is a leak."""
    persist_then_acknowledge(
        gateway,
        facts,
        lambda: _apply_store_facts(service, facts),
    )


def _apply_store_facts(service, facts: PurchaseFacts) -> None:
    for change in store_changes(facts):
        apply_store_change(service, change)
