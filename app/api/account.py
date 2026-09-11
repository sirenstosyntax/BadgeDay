"""The candidate's own account: what they are entitled to, and deleting it.

`/me` is polled by the app to decide whether to show the paywall. It reports entitlement
rather than a plan name, because entitlement is what every gate in the system actually asks
about — a subscription and a 90-day pass are different purchases and the same answer to
"can this person work today".

`DELETE /me` is the deletion promise the privacy constraint makes: a candidate can remove
themselves and everything that is theirs. Billing is stopped first, deliberately — a
deleted account that keeps being charged, with the portal that could stop it now gone, is
the worst outcome here, so a failure to reach Stripe aborts the whole delete rather than
pressing on.
"""

from datetime import datetime

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.api.deps import CurrentUserDep, DbDep, GatewayDep, ServiceDbDep, SettingsDep
from app.billing.module import store_product_ids_for
from app.storage.account import purge_account
from app.storage.billing import Entitlement, customer_id_for, entitlement
from app.storage.entitlements import module_entitlement
from app.storage.store import managed_elsewhere, managed_elsewhere_for

router = APIRouter(tags=["account"])


class PlayProducts(BaseModel):
    """Play product ids as configured. Empty strings become null — never invented."""

    monthly: str | None = None
    intensive_90day: str | None = None
    recruit_monthly: str | None = None
    recruit_intensive_90day: str | None = None
    recruit_6month: str | None = None
    recruit_annual: str | None = None


class RecruitModule(BaseModel):
    """Recruit-only entitlement. `entitled` is has_recruit_access — the practice gate.

    The Oral-board exhausted money block reads this nest, never Promote
    entitled / subscription_status, so a Lieutenant plan plus a used free
    Recruit session cannot open Recruit pause / Manage billing.
    """

    entitled: bool
    subscription_status: str
    access_expires_at: datetime | None = None
    managed_by: str | None = None


class Account(Entitlement):
    id: str
    email: str | None = None
    # Which store, if any, holds what they are paying for — 'play', 'appstore', or absent
    # for Stripe and for candidates who have never paid. The account screen needs it to
    # send someone to the right place to cancel: a subscription bought through the App
    # Store cannot be cancelled from our billing portal, and offering that candidate a
    # portal button is how a cancellation becomes a chargeback.
    managed_by: str | None = None
    play_products: PlayProducts
    recruit: RecruitModule


@router.get("/me")
def me(user: CurrentUserDep, db: DbDep, settings: SettingsDep) -> Account:
    state = entitlement(db, user.id)
    store = managed_elsewhere(db, user.id)
    recruit_state = module_entitlement(db, user.id, "recruit")
    recruit_store = managed_elsewhere_for(
        db, user.id, product_ids=store_product_ids_for(settings, "recruit")
    )
    return Account(
        id=user.id,
        email=user.email,
        managed_by=store.platform if store else None,
        play_products=PlayProducts(
            monthly=settings.play_product_id_monthly or None,
            intensive_90day=settings.play_product_id_intensive_90day or None,
            recruit_monthly=settings.play_product_id_recruit_monthly or None,
            recruit_intensive_90day=settings.play_product_id_recruit_intensive_90day
            or None,
            recruit_6month=settings.play_product_id_recruit_6month or None,
            recruit_annual=settings.play_product_id_recruit_annual or None,
        ),
        recruit=RecruitModule(
            entitled=recruit_state.entitled,
            subscription_status=recruit_state.subscription_status,
            access_expires_at=recruit_state.access_expires_at,
            managed_by=recruit_store.platform if recruit_store else None,
        ),
        **state.model_dump(),
    )


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(
    user: CurrentUserDep,
    db: DbDep,
    service: ServiceDbDep,
    gateway: GatewayDep,
) -> None:
    """Hard-delete the candidate and everything of theirs, after stopping their billing."""
    customer_id = customer_id_for(db, user.id)
    if customer_id:
        # Before anything is removed. If this raises, the account is left intact and the
        # candidate can try again — far better than deleting them while a subscription bills
        # on with no portal left to cancel it.
        try:
            gateway.delete_customer(customer_id)
        except Exception as exc:
            raise HTTPException(
                status.HTTP_502_BAD_GATEWAY,
                "Could not stop billing just now, so nothing was deleted. Please try again.",
            ) from exc

    purge_account(db, service, user.id)
