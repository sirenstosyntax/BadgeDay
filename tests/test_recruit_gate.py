"""Ship gate #3 + #4: free first session(s), daily cap, entitlements gate.

Pure decisions — no database. The table check is `has_recruit_access` at the
HTTP layer in test_recruit_attempts.py; this file pins the numbers.
"""

import pytest

from app.recruit.gate import evaluate_recruit_gate


def test_first_attempt_is_free() -> None:
    gate = evaluate_recruit_gate(
        today_count=0,
        lifetime_count=0,
        daily_limit=10,
        free_sessions=1,
        entitled=False,
    )
    assert gate.allowed is True


def test_undelivered_history_is_still_inside_the_free_session() -> None:
    """lifetime_count is delivered critiques, so a blank completed row is 0."""
    gate = evaluate_recruit_gate(
        today_count=1,
        lifetime_count=0,
        daily_limit=10,
        free_sessions=1,
        entitled=False,
    )
    assert gate.allowed is True


def test_second_attempt_without_entitlement_is_402() -> None:
    gate = evaluate_recruit_gate(
        today_count=1,
        lifetime_count=1,
        daily_limit=10,
        free_sessions=1,
        entitled=False,
    )
    assert gate.allowed is False
    assert gate.status_code == 402
    assert gate.detail is not None
    assert "free oral-board session is used" in gate.detail
    assert "Recruit plan" in gate.detail


def test_entitled_candidate_is_not_blocked_after_the_free_session() -> None:
    gate = evaluate_recruit_gate(
        today_count=1,
        lifetime_count=4,
        daily_limit=10,
        free_sessions=1,
        entitled=True,
    )
    assert gate.allowed is True


def test_daily_cap_beats_entitlement() -> None:
    gate = evaluate_recruit_gate(
        today_count=10,
        lifetime_count=10,
        daily_limit=10,
        free_sessions=1,
        entitled=True,
    )
    assert gate.allowed is False
    assert gate.status_code == 429
    assert gate.detail is not None
    assert "today's limit of 10" in gate.detail


def test_daily_cap_beats_an_unused_free_session() -> None:
    """A leaked magic-link that somehow started 10 today is still stopped."""
    gate = evaluate_recruit_gate(
        today_count=10,
        lifetime_count=10,
        daily_limit=10,
        free_sessions=1,
        entitled=False,
    )
    assert gate.status_code == 429


def test_two_free_sessions_allow_the_second() -> None:
    gate = evaluate_recruit_gate(
        today_count=1,
        lifetime_count=1,
        daily_limit=10,
        free_sessions=2,
        entitled=False,
    )
    assert gate.allowed is True


def test_promote_entitlement_is_not_an_input() -> None:
    """The function has no has_access / Promote parameter on purpose."""
    assert "has_access" not in evaluate_recruit_gate.__code__.co_varnames
    assert "promote" not in evaluate_recruit_gate.__code__.co_varnames


def test_zero_daily_limit_is_rejected() -> None:
    with pytest.raises(ValueError, match="positive"):
        evaluate_recruit_gate(
            today_count=0,
            lifetime_count=0,
            daily_limit=0,
            free_sessions=1,
            entitled=False,
        )
