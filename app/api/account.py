"""The candidate's own account state.

One endpoint, and the app polls it to decide whether to show the paywall. It reports
entitlement rather than a plan name, because entitlement is what every gate in the system
actually asks about — a subscription and a 90-day pass are different purchases and the
same answer to "can this person work today".
"""

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, DbDep
from app.storage.billing import Entitlement, entitlement

router = APIRouter(tags=["account"])


class Account(Entitlement):
    id: str
    email: str | None = None


@router.get("/me")
def me(user: CurrentUserDep, db: DbDep) -> Account:
    state = entitlement(db, user.id)
    return Account(id=user.id, email=user.email, **state.model_dump())
