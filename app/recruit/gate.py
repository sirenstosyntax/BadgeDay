"""Whether this candidate may start a Recruit attempt.

Auth is the caller's problem (`CurrentUserDep`). This module answers the two
questions that remain after they have signed in:

1. Have they already used today's ceiling?
2. Are they still inside the free first session(s), or do they have Recruit
   entitlement?

Promote's `has_access` is a different product and is never consulted. Paid
Recruit access is `has_recruit_access`, which reads entitlements(user,
'recruit'). A Promote row, or a Promote subscription on profiles, does not
grant Recruit.
"""

from dataclasses import dataclass

from supabase import Client

from app.config import Settings
from app.storage.entitlements import has_recruit_access


class RecruitAccessDenied(Exception):
    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


@dataclass(frozen=True)
class RecruitGate:
    """The decision, and the HTTP answer when it is no."""

    allowed: bool
    status_code: int | None = None
    detail: str | None = None


def evaluate_recruit_gate(
    *,
    today_count: int,
    lifetime_count: int,
    daily_limit: int,
    free_sessions: int,
    entitled: bool,
) -> RecruitGate:
    """Pure decision. Counts are attempts already started, not including this one."""
    if daily_limit <= 0:
        raise ValueError("recruit daily attempt limit must be positive")
    if free_sessions < 0:
        raise ValueError("recruit free sessions cannot be negative")

    if today_count >= daily_limit:
        return RecruitGate(
            allowed=False,
            status_code=429,
            detail=(
                f"You have reached today's limit of {daily_limit} practice "
                "attempts. Try again tomorrow."
            ),
        )
    if entitled or lifetime_count < free_sessions:
        return RecruitGate(allowed=True)
    if free_sessions == 1:
        used = "Your free oral-board session is used."
    else:
        used = f"Your {free_sessions} free oral-board sessions are used."
    return RecruitGate(
        allowed=False,
        status_code=402,
        detail=f"{used} A Recruit plan is required for more practice.",
    )


def recruit_entitled(db: Client, user_id: str) -> bool:
    """Paid Recruit access, from entitlements(user, 'recruit').

    Empty Stripe / Play / App Store Recruit price IDs in Settings must not be
    treated as a grant — they are held placeholders. The table is the grant.
    """
    return has_recruit_access(db, user_id)


def check_recruit_access(
    db: Client,
    user_id: str,
    settings: Settings,
    *,
    today_count: int,
    lifetime_count: int,
) -> None:
    decision = evaluate_recruit_gate(
        today_count=today_count,
        lifetime_count=lifetime_count,
        daily_limit=settings.recruit_daily_attempt_limit,
        free_sessions=settings.recruit_free_sessions,
        entitled=recruit_entitled(db, user_id),
    )
    if not decision.allowed:
        assert decision.status_code is not None and decision.detail is not None
        raise RecruitAccessDenied(decision.status_code, decision.detail)
