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

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUserDep, DbDep, GatewayDep, ServiceDbDep
from app.storage.account import purge_account
from app.storage.billing import Entitlement, customer_id_for, entitlement
from app.storage.store import managed_elsewhere

router = APIRouter(tags=["account"])


class Account(Entitlement):
    id: str
    email: str | None = None
    # Which store, if any, holds what they are paying for — 'play', 'appstore', or absent
    # for Stripe and for candidates who have never paid. The account screen needs it to
    # send someone to the right place to cancel: a subscription bought through the App
    # Store cannot be cancelled from our billing portal, and offering that candidate a
    # portal button is how a cancellation becomes a chargeback.
    managed_by: str | None = None


@router.get("/me")
def me(user: CurrentUserDep, db: DbDep) -> Account:
    state = entitlement(db, user.id)
    store = managed_elsewhere(db, user.id)
    return Account(
        id=user.id,
        email=user.email,
        managed_by=store.platform if store else None,
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
