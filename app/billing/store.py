"""What an app-store purchase means for a candidate's entitlement — as a pure decision.

The sibling of `plan.py`, and deliberately the same shape: this module never touches a
store or the database. It takes facts that have already been verified (the gateway does
the signature checking and the store lookup) and returns the writes they imply, so the one
place where a mistake mis-grants access is a plain function a test can enumerate.

WHY THIS IS NOT plan.py WITH MORE BRANCHES. Stripe's webhook carries the subscription's
status in the event body, so `plan_changes` can read a dict and decide. Neither store
works that way:

  * Google's Real-time Developer Notification carries a notification *type* and a purchase
    token, and nothing else — no status, no expiry. The paid-through date only exists on
    the other end of a Play Developer API call.
  * Apple's App Store Server Notification V2 does carry the facts, but inside two nested
    JWS blobs that have to be verified against Apple's certificate chain first.

So the gateway's job is to turn either of those into `PurchaseFacts` — the same handful of
fields regardless of which store produced them — and this module's job is to decide what
those facts mean. That split is what lets the whole mapping below be tested with no store
account, no service-account key, and no network, which is the only way it gets exercised
at all before launch: the container cannot talk to Play, and CI has no App Store Connect
credentials.

See mobile_release_plan.md for why store billing exists at all rather than Stripe
everywhere, and what each store charges for it.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from app.billing.module import Module

Platform = Literal["play", "appstore"]

# A subscription renews until stopped; a pass is bought once and runs out. The same two
# shapes Stripe sells, because the store is a different till and not a different product
# line — a candidate who buys the 90-day intensive on their phone should get the 90-day
# intensive, not a store-shaped variant of it.
PurchaseKind = Literal["subscription", "pass"]

# ---------------------------------------------------------------------------
# The normalised store vocabulary.
#
# Both stores describe the same lifecycle with different words and, in Play's case, with
# integers. Rather than let either store's vocabulary spread through the codebase, the
# gateway translates into these names and everything downstream speaks only this.
#
# The mapping from each store's own vocabulary lives in the gateway next to the code that
# parses that store's payload; the mapping from these names to OUR entitlement column is
# here, because that is the decision rather than the parsing.
# ---------------------------------------------------------------------------
StoreState = Literal[
    "purchased",  # bought, or renewed, or recovered from a failed payment
    "grace_period",  # payment failing, store is retrying, access usually still granted
    "on_hold",  # payment failed for long enough that the store suspended it
    "auto_renew_off",  # candidate turned off renewal; still paid through expires_at
    "expired",  # ran its course
    "revoked",  # refunded or charged back — access ends NOW, not at expires_at
]

# StoreState -> profiles-vocabulary status. Deliberately enumerated rather than passed
# through, the same discipline `plan._SUBSCRIPTION_STATUS` applies to Stripe's statuses: a
# state either store adds later must not silently grant entitlement.
_STATUS: dict[str, str] = {
    "purchased": "active",
    # Access during a grace period is granted by the store — the candidate is still using
    # the app while their bank sorts itself out — but we mirror 0005's stance and treat it
    # as unpaid HERE, because expires_at is what actually keeps them running. A candidate
    # inside their paid-through date keeps access through the expiry clause regardless of
    # this column, and one whose paid-through date has passed genuinely has not paid.
    "grace_period": "past_due",
    "on_hold": "past_due",
    # NOT a revocation. Turning off auto-renew on the 3rd of a month paid through the 30th
    # buys the rest of the month; both stores keep serving it and so do we. The expiry
    # clause in has_access is what grants those days, which is why this can safely be a
    # non-granting status.
    "auto_renew_off": "canceled",
    "expired": "canceled",
    "revoked": "canceled",
}

# A refund is the one event that must cut access off mid-period. Every other terminal state
# leaves expires_at alone and lets the date do the work.
_CLEARS_EXPIRY = frozenset({"revoked"})


class PurchaseFacts(BaseModel):
    """One store purchase, as the gateway has verified it.

    `user_id` is present only when the store gave us one. Both stores carry an opaque
    developer-supplied token on the purchase — Play's `obfuscatedExternalAccountId`, Apple's
    `appAccountToken` — which the app sets to the candidate's id at purchase time. That is
    the entire link between a purchase and an account, so a purchase that arrives without
    one cannot be attributed and must not be guessed at; see `store_changes`.
    """

    platform: Platform
    product_id: str
    purchase_identifier: str
    kind: PurchaseKind
    state: StoreState
    expires_at: datetime | None = None
    user_id: str | None = None


class RecordPurchase(BaseModel):
    """Create or update the row for a purchase, and bind it to a candidate.

    Carries the user id, so it is the only change that can establish the link. Emitted when
    the facts include one — on the client's own report of a completed purchase, and on any
    store notification whose payload carried the account token through.
    """

    kind_: Literal["record"] = "record"
    user_id: str
    platform: Platform
    product_id: str
    purchase_identifier: str
    kind: PurchaseKind
    status: str
    expires_at: datetime | None = None
    # Required. An unknown product must not default to promote — that is how
    # an unmapped Play SKU would satisfy has_access.
    module: Module


class SetPurchaseStatus(BaseModel):
    """Update an existing purchase's status and expiry, keyed on the store's identifier.

    The renewal-and-cancellation workhorse. Carries no user id because the row already
    knows whose it is, which is what makes a notification arriving months later — long
    after whatever session bought it — safe to apply.
    """

    kind_: Literal["status"] = "status"
    platform: Platform
    purchase_identifier: str
    status: str
    expires_at: datetime | None = None
    clear_expiry: bool = False


StoreChange = RecordPurchase | SetPurchaseStatus


def status_for(state: StoreState) -> str:
    """Our entitlement status for a normalised store state.

    An unrecognised state collapses to 'canceled' for the same reason an unrecognised
    Stripe status does: it withholds access, it is reversible by the next real event, and
    it is the only value that cannot be wrong in the expensive direction.
    """
    return _STATUS.get(state, "canceled")


def store_changes(facts: PurchaseFacts, *, module: Module | None) -> list[StoreChange]:
    """The writes a verified store purchase implies.

    `module` is resolved server-side from the configured product IDs. None
    (blank, unknown, or unconfigured) emits nothing — an unmapped SKU must
    not open Promote via a defaulted `module='promote'` row.

    Two cases when the module is known, and the difference is whether we can
    say whose purchase this is:

      * The facts carry a user id — the candidate just bought it, or the store
        passed the account token through on the notification. Record the row
        and bind it.
      * They do not. Update the existing row by its store identifier. If no
        such row exists the update matches nothing, which the storage layer
        logs rather than raises.

    What is deliberately NOT here: attributing an unattributable purchase by
    guessing.
    """
    if module is None:
        return []

    status = status_for(facts.state)
    clears = facts.state in _CLEARS_EXPIRY

    if facts.user_id:
        return [
            RecordPurchase(
                user_id=facts.user_id,
                platform=facts.platform,
                product_id=facts.product_id,
                purchase_identifier=facts.purchase_identifier,
                kind=facts.kind,
                status=status,
                # A refund cuts access off now, so the expiry the store last told us about
                # is not carried onto the row it is being written to.
                expires_at=None if clears else facts.expires_at,
                module=module,
            )
        ]

    return [
        SetPurchaseStatus(
            platform=facts.platform,
            purchase_identifier=facts.purchase_identifier,
            status=status,
            expires_at=None if clears else facts.expires_at,
            # Distinguishes "this event says nothing about the expiry, leave it" from "this
            # event ends access now". Without the flag, a None expiry on a renewal
            # notification we failed to read fully would look identical to a refund.
            clear_expiry=clears,
        )
    ]
