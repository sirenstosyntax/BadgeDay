"""Recruit follow-up: one results email, one reminder, then stop.

Results copy is what the board already showed (the same lines, the same
framing). No second wording of the notes. Red reviews the fixed lines in
this file once.

Dates are UTC calendar days. A reminder is due at 00:00 UTC seven days
before the test date, and only when the date was at least seven days out
at the moment it was saved. Each test date is reminded once.
"""

from __future__ import annotations

import ipaddress
import logging
import re
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from typing import Protocol

from app.config import Settings
from app.recruit.copy import BOARD_FRAMING
from app.recruit.mail import EmailSender, OutboundEmail

logger = logging.getLogger(__name__)

SRC_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
# Hosts we own. A referrer from one of these is our own page, not a source.
# badgeday_infrastructure_map.md, the TWA origin (app.badgeday.com), and the
# redirect alternates in app/redirect.py.
OWN_REFERRER_HOSTS = frozenset(
    {
        "badgeday.com",
        "www.badgeday.com",
        "app.badgeday.com",
        "api.badgeday.com",
        "badgeday.app",
        "www.badgeday.app",
        "sirenstosyntax.com",
        "www.sirenstosyntax.com",
    }
)
FORBIDDEN_WORDS = re.compile(
    r"\b(pass|passed|passing|hired|guarantee|guaranteed)\b",
    re.IGNORECASE,
)

# Fixed lines. The notes under them are the candidate's own board summary.
RESULTS_SUBJECT = "Your BadgeDay practice board notes"
PRACTICE_NOTE = (
    "This was practice. It does not predict how a real board will score you. "
    "Panels, questions, and scoring vary by department."
)
REMINDER_SUBJECT = "Practice before your test"
SENDER_NAME = "BadgeDay"
SENDER_ORG = "Sirens to Syntax LLC"

REMINDER_LEAD_DAYS = 7
CLAIM_STALE = timedelta(minutes=10)

_logged: set[str] = set()


def log_once(key: str, message: str) -> None:
    if key in _logged:
        return
    _logged.add(key)
    logger.warning(message)


def valid_signup_src(raw: str | None) -> str | None:
    """A short tag from the link. No spaces, no addresses, nothing personal."""
    if raw is None:
        return None
    text = raw.strip()
    if not text or SRC_RE.fullmatch(text) is None:
        return None
    return text


def valid_referrer_domain(raw: str | None) -> str | None:
    """A hostname that passes the src rule. A URL, an IP, or our own host is dropped."""
    if raw is None:
        return None
    text = raw.strip().lower().rstrip(".")
    if not text or text in OWN_REFERRER_HOSTS or _is_ip_address(text):
        return None
    return valid_signup_src(text)


def _is_ip_address(text: str) -> bool:
    try:
        ipaddress.ip_address(text)
    except ValueError:
        return False
    return True


def reminder_due_at(test_on: date, now: datetime) -> datetime | None:
    """None when the date is already inside the seven-day window."""
    today = now.astimezone(UTC).date()
    if (test_on - today).days < REMINDER_LEAD_DAYS:
        return None
    send_on = test_on - timedelta(days=REMINDER_LEAD_DAYS)
    return datetime(send_on.year, send_on.month, send_on.day, tzinfo=UTC)


@dataclass
class FollowUpState:
    signup_src: str | None = None
    signup_referrer_domain: str | None = None
    signup_utm_source: str | None = None
    signup_utm_medium: str | None = None
    signup_utm_campaign: str | None = None
    test_on: date | None = None
    reminder_due_at: datetime | None = None
    reminder_sent_for: date | None = None
    unsubscribed_at: datetime | None = None


def apply_signup_src(state: FollowUpState, raw: str | None) -> FollowUpState:
    """Store the first valid tag. A missing or invalid tag changes nothing."""
    parsed = valid_signup_src(raw)
    if parsed is None or state.signup_src is not None:
        return state
    return replace(state, signup_src=parsed)


def apply_signup_attribution(
    state: FollowUpState,
    *,
    src: str | None = None,
    referrer_domain: str | None = None,
    utm_source: str | None = None,
    utm_medium: str | None = None,
    utm_campaign: str | None = None,
) -> FollowUpState:
    """First value wins on each column. An explicit src never comes from the referrer."""
    state = apply_signup_src(state, src)
    incoming = {
        "signup_referrer_domain": valid_referrer_domain(referrer_domain),
        "signup_utm_source": valid_signup_src(utm_source),
        "signup_utm_medium": valid_signup_src(utm_medium),
        "signup_utm_campaign": valid_signup_src(utm_campaign),
    }
    changes: dict[str, str] = {}
    for field, parsed in incoming.items():
        if parsed is None or getattr(state, field) is not None:
            continue
        changes[field] = parsed
    if not changes:
        return state
    return replace(state, **changes)


def apply_test_date(
    state: FollowUpState, test_on: date | None, now: datetime
) -> FollowUpState:
    """Save the date. Schedule one reminder, or none when it is too soon."""
    if test_on is None or state.unsubscribed_at is not None:
        return replace(state, test_on=test_on, reminder_due_at=None)
    if state.reminder_sent_for == test_on:
        return replace(state, test_on=test_on, reminder_due_at=None)
    return replace(state, test_on=test_on, reminder_due_at=reminder_due_at(test_on, now))


def apply_unsubscribe(state: FollowUpState, now: datetime) -> FollowUpState:
    return replace(state, unsubscribed_at=now, reminder_due_at=None)


@dataclass(frozen=True)
class BoardAnswerNote:
    question_index: int
    question_text: str
    lines: list[str]


@dataclass(frozen=True)
class BoardSummary:
    answers: list[BoardAnswerNote]
    c1_lines: list[str]


def unsubscribe_headers(url: str) -> dict[str, str]:
    return {
        "List-Unsubscribe": f"<{url}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


def join_url(base: str, path: str) -> str:
    return base.rstrip("/") + path


def unsubscribe_url(base: str, token: str) -> str:
    return join_url(base, f"/email/unsubscribe?token={token}")


def _footer(unsub_url: str, address: str) -> list[str]:
    return [
        f"Unsubscribe: {unsub_url}",
        "",
        SENDER_NAME,
        SENDER_ORG,
        address.strip(),
    ]


def render_results(
    summary: BoardSummary,
    *,
    continue_url: str,
    test_date_url: str,
    unsub_url: str,
    address: str,
    price_line: str,
) -> OutboundEmail:
    """The results email. Notes are copied from the board, not rewritten."""
    parts: list[str] = [BOARD_FRAMING, PRACTICE_NOTE, ""]
    for answer in summary.answers:
        parts.append(f"Question {answer.question_index}")
        question = answer.question_text.strip()
        if question:
            parts.append(question)
        for line in answer.lines:
            text = line.strip()
            if text:
                parts.append(text)
        parts.append("")
    for line in summary.c1_lines:
        text = line.strip()
        if text:
            parts.append(text)
    parts.append("")
    parts.append(f"Continue: {continue_url}")
    parts.append(f"When is your test? {test_date_url}")
    price = price_line.strip()
    if price:
        parts.append("")
        parts.append(price)
    parts.append("")
    parts.extend(_footer(unsub_url, address))
    return OutboundEmail(
        to="",
        subject=RESULTS_SUBJECT,
        text="\n".join(parts).strip() + "\n",
        headers=unsubscribe_headers(unsub_url),
    )


def render_reminder(
    test_on: date,
    *,
    continue_url: str,
    unsub_url: str,
    address: str,
) -> OutboundEmail:
    parts = [
        f"Your test date is {test_on.isoformat()}. Practice before then.",
        "",
        f"Practice: {continue_url}",
        "",
        *_footer(unsub_url, address),
    ]
    return OutboundEmail(
        to="",
        subject=REMINDER_SUBJECT,
        text="\n".join(parts).strip() + "\n",
        headers=unsubscribe_headers(unsub_url),
    )


@dataclass(frozen=True)
class DueResults:
    user_id: str
    email: str
    token: str
    summary: BoardSummary


@dataclass(frozen=True)
class DueReminder:
    user_id: str
    email: str
    token: str
    test_on: date


class FollowUpRepo(Protocol):
    def due_results(self, now: datetime) -> list[DueResults]: ...

    def due_reminders(self, now: datetime) -> list[DueReminder]: ...

    def claim_results(self, user_id: str, now: datetime) -> bool: ...

    def claim_reminder(self, user_id: str, now: datetime) -> bool: ...

    def mark_results_sent(self, user_id: str, now: datetime) -> None: ...

    def mark_reminder_sent(self, user_id: str, test_on: date, now: datetime) -> None: ...

    def clear_results_claim(self, user_id: str) -> None: ...

    def clear_reminder_claim(self, user_id: str) -> None: ...


@dataclass
class DispatchReport:
    results_sent: int = 0
    reminders_sent: int = 0
    skipped: str | None = None


def dispatch_due(
    repo: FollowUpRepo,
    sender: EmailSender,
    settings: Settings,
    now: datetime,
) -> DispatchReport:
    """Send what is due. An empty postal address or an unconfigured sender sends nothing."""
    address = settings.mailing_address.strip()
    if not address:
        log_once(
            "mailing-address",
            "MAILING_ADDRESS is empty; recruit follow-up email will not send",
        )
        return DispatchReport(skipped="mailing_address")
    if not sender.configured:
        log_once(
            "sender",
            "RESEND_API_KEY or EMAIL_FROM is unset; recruit follow-up email will not send",
        )
        return DispatchReport(skipped="sender")

    report = DispatchReport()
    base = settings.public_web_url
    continue_url = join_url(base, "/start")
    test_date_url = join_url(base, "/recruit/test-date")

    for item in repo.due_results(now):
        if not repo.claim_results(item.user_id, now):
            continue
        message = render_results(
            item.summary,
            continue_url=continue_url,
            test_date_url=test_date_url,
            unsub_url=unsubscribe_url(base, item.token),
            address=address,
            price_line=settings.recruit_price_line,
        )
        message = replace_to(message, item.email)
        if _deliver(sender, repo.clear_results_claim, item.user_id, message):
            repo.mark_results_sent(item.user_id, now)
            report.results_sent += 1

    for item in repo.due_reminders(now):
        if not repo.claim_reminder(item.user_id, now):
            continue
        message = render_reminder(
            item.test_on,
            continue_url=continue_url,
            unsub_url=unsubscribe_url(base, item.token),
            address=address,
        )
        message = replace_to(message, item.email)
        if _deliver(sender, repo.clear_reminder_claim, item.user_id, message):
            repo.mark_reminder_sent(item.user_id, item.test_on, now)
            report.reminders_sent += 1

    return report


def replace_to(message: OutboundEmail, to: str) -> OutboundEmail:
    return OutboundEmail(to=to, subject=message.subject, text=message.text, headers=message.headers)


def _deliver(sender: EmailSender, release, user_id: str, message: OutboundEmail) -> bool:
    try:
        result = sender.send(message)
    except Exception:
        logger.exception("recruit follow-up send failed for %s", user_id)
        release(user_id)
        return False
    if not result.delivered:
        release(user_id)
        return False
    return True
