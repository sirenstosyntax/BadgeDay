"""Per-module entitlement: grant, read, and the question the Recruit gate asks.

The rule itself is not here. It is `has_module_access` in migration 0012, which
`has_recruit_access` wraps for the Recruit gate. This module writes the row and
asks that question. Recomputing "active, or an expiry in the future" in Python
would be a second definition, and the two would drift the first time one of them
learned about a grace period — the same reason `storage/billing.py` is a round
trip rather than a local check over profiles.

Writes need a service-role client. entitlements is not candidate-writable —
0012 revokes the privilege for the same reason 0005 revoked it on profiles —
and the writer of these rows is a verified payment, or a test, never a
signed-in candidate granting themselves a module.
"""

import logging
from datetime import datetime
from typing import Literal

from pydantic import BaseModel
from supabase import Client

logger = logging.getLogger(__name__)

Module = Literal["promote", "recruit"]
SubscriptionStatus = Literal["none", "active", "past_due", "canceled"]


class ModuleEntitlement(BaseModel):
    """What a candidate holds for one module. `entitled` is the gate's answer."""

    module: Module
    entitled: bool
    subscription_status: SubscriptionStatus
    access_expires_at: datetime | None = None


class SetModuleSubscription(BaseModel):
    """Mirror a subscription status onto one (user, module) row."""

    kind: Literal["subscription"] = "subscription"
    user_id: str
    module: Module
    status: SubscriptionStatus


class GrantModulePass(BaseModel):
    """Extend one module to a fixed expiry — the one-time pass."""

    kind: Literal["pass"] = "pass"
    user_id: str
    module: Module
    expires_at: datetime


class ClearModulePass(BaseModel):
    """End a pass now. Used for a refund; does not touch subscription_status."""

    kind: Literal["clear_pass"] = "clear_pass"
    user_id: str
    module: Module


EntitlementChange = SetModuleSubscription | GrantModulePass | ClearModulePass


def has_module_access(db: Client, user_id: str, module: Module) -> bool:
    """Ask the database whether this candidate holds this module today."""
    result = (
        db.rpc("has_module_access", {"candidate": user_id, "p_module": module})
        .execute()
        .data
    )
    return bool(result)


def has_recruit_access(db: Client, user_id: str) -> bool:
    """Paid Recruit access. Promote's `has_access` is a different product."""
    result = db.rpc("has_recruit_access", {"candidate": user_id}).execute().data
    return bool(result)


def module_entitlement(db: Client, user_id: str, module: Module) -> ModuleEntitlement:
    """The row plus the database's verdict. Missing row is 'none', not entitled."""
    entitled = has_module_access(db, user_id, module)
    rows = (
        db.table("entitlements")
        .select("subscription_status,access_expires_at")
        .eq("user_id", user_id)
        .eq("module", module)
        .limit(1)
        .execute()
        .data
    )
    row = rows[0] if rows else {"subscription_status": "none", "access_expires_at": None}
    return ModuleEntitlement(
        module=module,
        entitled=entitled,
        subscription_status=row["subscription_status"],
        access_expires_at=row["access_expires_at"],
    )


def apply_entitlement(db: Client, change: EntitlementChange) -> None:
    """Write one (user, module) change. Requires a service-role client.

    Upsert on (user_id, module) so a second grant updates rather than colliding.
    A change that matches no row is logged, not raised — the same footing as
    `billing.apply_change`: a webhook must answer 200, and a mismatch is worth
    a log line, not a retry loop.
    """
    if isinstance(change, SetModuleSubscription):
        result = (
            db.table("entitlements")
            .upsert(
                {
                    "user_id": change.user_id,
                    "module": change.module,
                    "subscription_status": change.status,
                },
                on_conflict="user_id,module",
            )
            .execute()
        )
        _warn_if_unmatched(
            result, f"set {change.module} subscription for user {change.user_id}"
        )
        return

    if isinstance(change, GrantModulePass):
        result = (
            db.table("entitlements")
            .upsert(
                {
                    "user_id": change.user_id,
                    "module": change.module,
                    "access_expires_at": change.expires_at.isoformat(),
                },
                on_conflict="user_id,module",
            )
            .execute()
        )
        _warn_if_unmatched(
            result, f"grant {change.module} pass to user {change.user_id}"
        )
        return

    if isinstance(change, ClearModulePass):
        result = (
            db.table("entitlements")
            .update({"access_expires_at": None})
            .eq("user_id", change.user_id)
            .eq("module", change.module)
            .execute()
        )
        _warn_if_unmatched(
            result, f"clear {change.module} pass for user {change.user_id}"
        )
        return


def _warn_if_unmatched(result: object, what: str) -> None:
    if not getattr(result, "data", None):
        logger.warning("entitlement change matched no row: %s", what)
