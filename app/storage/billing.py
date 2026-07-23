"""Entitlement, as the application sees it.

The rule itself is not here. It is `has_access` in migration 0005, which the insert
policies on documents and practice_sessions also call — so the API and the database
cannot disagree about who is entitled. This module asks that question and translates the
database's refusal into something an HTTP layer can act on.

Reading entitlement is deliberately a round trip rather than a local computation over the
profile row. Recomputing "active, or an expiry in the future" in Python would be a second
definition of the rule, and the two would drift the first time one of them learns about a
grace period.
"""

import logging
from datetime import datetime

from postgrest.exceptions import APIError
from pydantic import BaseModel
from supabase import Client

from app.billing.plan import Change, GrantPass, LinkCustomer, SetSubscription

logger = logging.getLogger(__name__)

# What PostgREST returns when a row-level security policy refuses a write. For documents
# and practice_sessions after 0005, the overwhelmingly likely reason is that the candidate
# is not entitled — they cannot reach another candidate's rows to be refused for any other
# reason, because the policy scopes to auth.uid() as well.
RLS_DENIED = "42501"


class SubscriptionRequired(Exception):
    """The action needs an active subscription or an unexpired pass."""


class Entitlement(BaseModel):
    entitled: bool
    subscription_status: str
    access_expires_at: datetime | None = None


def entitlement(db: Client, user_id: str) -> Entitlement:
    entitled = db.rpc("has_access", {"candidate": user_id}).execute().data
    profile = (
        db.table("profiles")
        .select("subscription_status,access_expires_at")
        .eq("id", user_id)
        .limit(1)
        .execute()
        .data
    )
    row = profile[0] if profile else {"subscription_status": "none", "access_expires_at": None}
    return Entitlement(
        entitled=bool(entitled),
        subscription_status=row["subscription_status"],
        access_expires_at=row["access_expires_at"],
    )


def customer_id_for(db: Client, user_id: str) -> str | None:
    """The candidate's Stripe customer id, if they have ever begun checkout."""
    rows = (
        db.table("profiles")
        .select("stripe_customer_id")
        .eq("id", user_id)
        .limit(1)
        .execute()
        .data
    )
    return rows[0]["stripe_customer_id"] if rows else None


def apply_change(db: Client, change: Change) -> None:
    """Write one entitlement change to profiles. Requires a service-role client.

    Profiles is not candidate-writable (0005 revoked that privilege precisely so a
    candidate cannot mark themselves paid). The writer of these columns is Stripe, speaking
    through a webhook we have verified — so this bypasses row-level security by design, the
    same trusted-writer footing as the ingestion worker, and never runs on behalf of a
    candidate's own token.

    A change that matches no profile row is logged, not raised: a webhook must answer 200
    or Stripe retries it forever, and a mismatch means an event arrived for a customer we
    have no record of — worth seeing in the logs, not worth wedging the webhook.
    """
    if isinstance(change, LinkCustomer):
        result = (
            db.table("profiles")
            .update({"stripe_customer_id": change.customer_id})
            .eq("id", change.user_id)
            .execute()
        )
        _warn_if_unmatched(result, f"link customer to user {change.user_id}")
        return

    if isinstance(change, SetSubscription):
        result = (
            db.table("profiles")
            .update({"subscription_status": change.status})
            .eq("stripe_customer_id", change.customer_id)
            .execute()
        )
        _warn_if_unmatched(result, f"set subscription for customer {change.customer_id}")
        return

    if isinstance(change, GrantPass):
        result = (
            db.table("profiles")
            .update({"access_expires_at": change.expires_at.isoformat()})
            .eq("stripe_customer_id", change.customer_id)
            .execute()
        )
        _warn_if_unmatched(result, f"grant pass to customer {change.customer_id}")
        return


def _warn_if_unmatched(result: object, what: str) -> None:
    if not getattr(result, "data", None):
        logger.warning("billing change matched no profile row: %s", what)


def as_subscription_required(exc: APIError) -> Exception:
    """Turn an RLS refusal into something the API can answer with.

    Anything else is returned unchanged. Guessing that every database error means "pay us"
    would turn an outage into a payment demand, which is a bad failure in both directions:
    the candidate is asked for money they already gave, and we never hear that the database
    was down.
    """
    if exc.code == RLS_DENIED or "row-level security" in (exc.message or ""):
        return SubscriptionRequired(exc.message or "")
    return exc
