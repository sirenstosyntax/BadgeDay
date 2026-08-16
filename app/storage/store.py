"""Writing store purchases to the database, and reading back who manages the billing.

The sibling of `storage/billing.py`, and it inherits that module's two rules verbatim:

  * The entitlement RULE is not here. It is `has_access` in migration 0008, which the
    insert policies on documents and practice_sessions also call, so the API and the
    database cannot disagree about who has paid.
  * Writes need a service-role client. store_purchases is not candidate-writable — 0008
    revokes the privilege for the same reason 0005 revoked it on profiles — and the writer
    of these rows is a store notification we have verified, not a signed-in candidate.
"""

import logging

from pydantic import BaseModel
from supabase import Client

from app.billing.store import Platform, RecordPurchase, SetPurchaseStatus, StoreChange

logger = logging.getLogger(__name__)


class ManagedElsewhere(BaseModel):
    """Where a candidate goes to change or cancel what they are paying for.

    The account screen needs this and cannot infer it. A subscription bought through the
    App Store is cancelled in the App Store; sending that candidate to Stripe's billing
    portal shows them an empty page, and sending them nowhere is how a cancellation becomes
    a chargeback.
    """

    platform: Platform
    product_id: str
    status: str


def apply_store_change(db: Client, change: StoreChange) -> None:
    """Write one store change. Requires a service-role client.

    A change that matches no row is logged, not raised, on the same reasoning as
    `billing.apply_change`: both stores retry a notification until it is answered 200, so
    an unmatched update must not wedge the endpoint. Unmatched here means a notification
    for a purchase we have no record of — which is worth a human's attention and is exactly
    what an unattributable purchase looks like.
    """
    if isinstance(change, RecordPurchase):
        row = {
            "user_id": change.user_id,
            "platform": change.platform,
            "product_id": change.product_id,
            "purchase_identifier": change.purchase_identifier,
            "kind": change.kind,
            "status": change.status,
            "expires_at": change.expires_at.isoformat() if change.expires_at else None,
        }
        # Upsert on the store's own identifier, because this same path runs on the client's
        # report of a purchase AND on the notification that follows it, in either order.
        # Whichever arrives second must update the row rather than collide with the unique
        # constraint and 500 at a store that will simply retry.
        result = (
            db.table("store_purchases")
            .upsert(row, on_conflict="platform,purchase_identifier")
            .execute()
        )
        _warn_if_unmatched(result, f"record {change.platform} purchase for user {change.user_id}")
        return

    if isinstance(change, SetPurchaseStatus):
        update: dict[str, object] = {"status": change.status}
        # Three-way, and the distinction is the point. A refund clears the expiry so access
        # ends now; an event carrying a new paid-through date writes it; an event that says
        # nothing about expiry leaves the column alone rather than nulling it, which would
        # cut off a candidate mid-period on a notification that was never about expiry.
        if change.clear_expiry:
            update["expires_at"] = None
        elif change.expires_at is not None:
            update["expires_at"] = change.expires_at.isoformat()

        result = (
            db.table("store_purchases")
            .update(update)
            .eq("platform", change.platform)
            .eq("purchase_identifier", change.purchase_identifier)
            .execute()
        )
        _warn_if_unmatched(
            result,
            f"set status on {change.platform} purchase {_redact(change.purchase_identifier)}",
        )
        return


def managed_elsewhere(db: Client, user_id: str) -> ManagedElsewhere | None:
    """The candidate's live store purchase, if they have one. None means Stripe or nothing.

    'Live' is deliberately wider than 'granting access': a purchase that has lapsed is
    still the one the candidate manages in the store, and the account screen should keep
    pointing there rather than silently switching its advice the day a card fails.
    """
    rows = (
        db.table("store_purchases")
        .select("platform,product_id,status")
        .eq("user_id", user_id)
        .neq("status", "canceled")
        .order("updated_at", desc=True)
        .limit(1)
        .execute()
        .data
    )
    if not rows:
        return None
    return ManagedElsewhere(**rows[0])


def _redact(identifier: str) -> str:
    """Purchase tokens are bearer-ish — enough to query a store about somebody's purchase.

    Logs are read by more people and kept longer than the database is, so the log gets
    enough to correlate two lines about the same purchase and not enough to be the token.
    """
    return f"…{identifier[-6:]}" if len(identifier) > 6 else "…"


def _warn_if_unmatched(result: object, what: str) -> None:
    if not getattr(result, "data", None):
        logger.warning("store change matched no purchase row: %s", what)
