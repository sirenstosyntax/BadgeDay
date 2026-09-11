"""The second and third tills: purchases made inside the Android and iOS apps.

`api/billing.py` is the Stripe route. These endpoints are its store-side counterpart,
and they come in two kinds:

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

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from app.api.deps import CurrentUserDep, ServiceDbDep, SettingsDep, StoreGatewayDep
from app.billing.module import module_for_store_product, pass_days_for_store_product
from app.billing.play_gateway import persist_then_acknowledge
from app.billing.recruit_plan import recruit_entitlement_from_store
from app.billing.store import PurchaseFacts, RecordPurchase, store_changes
from app.billing.store_gateway import StoreNotConfigured, StoreVerificationError
from app.config import Settings
from app.storage.entitlements import apply_entitlement
from app.storage.store import apply_store_change, user_id_for_purchase

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
    settings: SettingsDep,
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

    _persist_play_purchase(service, gateway, facts, settings)
    return Unlocked(entitled=facts.state == "purchased", product_id=facts.product_id)


@router.post("/billing/store/appstore/purchase")
def appstore_purchase(
    body: AppStorePurchase,
    user: CurrentUserDep,
    service: ServiceDbDep,
    gateway: StoreGatewayDep,
    settings: SettingsDep,
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

    _apply_store_facts(service, facts, settings)

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

    _persist_play_purchase(service, gateway, facts, settings)
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

    _apply_store_facts(service, facts, settings)
    return {"received": True}


def _persist_play_purchase(
    service, gateway, facts: PurchaseFacts, settings: Settings
) -> None:
    """Record the verified purchase, then acknowledge. Ack-before-write is a leak."""
    persist_then_acknowledge(
        gateway,
        facts,
        lambda: _apply_store_facts(service, facts, settings),
    )


def _apply_store_facts(service, facts: PurchaseFacts, settings: Settings) -> None:
    module = module_for_store_product(settings, facts.product_id)
    stamped = facts
    if (
        module == "recruit"
        and facts.kind == "pass"
        and facts.expires_at is None
        and facts.state == "purchased"
    ):
        days = pass_days_for_store_product(settings, facts.product_id)
        if days:
            stamped = facts.model_copy(
                update={"expires_at": datetime.now(UTC) + timedelta(days=days)}
            )

    for change in store_changes(stamped):
        if isinstance(change, RecordPurchase) and module:
            change = change.model_copy(update={"module": module})
        apply_store_change(service, change)

    if module != "recruit":
        return

    user_id = stamped.user_id or user_id_for_purchase(
        service, stamped.platform, stamped.purchase_identifier
    )
    if not user_id:
        return
    for change in recruit_entitlement_from_store(stamped, user_id):
        apply_entitlement(service, change)
