"""Profile columns for /start and the two follow-up emails.

Writes use the service role. profiles UPDATE is revoked from the candidate
(0005), and these columns sit next to billing fields that must stay
unwritable. Reads of the public slice (src, test date, free-board flag)
go through the candidate's own client.
"""

from __future__ import annotations

import secrets
from datetime import UTC, date, datetime, timedelta

from supabase import Client

from app.config import Settings
from app.recruit.followup import (
    CLAIM_STALE,
    BoardAnswerNote,
    BoardSummary,
    DueReminder,
    DueResults,
    FollowUpState,
    apply_signup_attribution,
    apply_test_date,
    apply_unsubscribe,
    dispatch_due,
)
from app.recruit.mail import EmailSender, build_sender
from app.storage.boards import notes_were_released, worker_board_attempts

_PROFILE_FIELDS = (
    "id,email,created_at,signup_src,signup_referrer_domain,"
    "signup_utm_source,signup_utm_medium,signup_utm_campaign,"
    "recruit_test_on,recruit_reminder_due_at,"
    "recruit_reminder_sent_for,recruit_reminder_claimed_at,"
    "recruit_results_ready_at,recruit_results_sent_at,recruit_results_claimed_at,"
    "recruit_unsubscribed_at,recruit_email_token"
)

# The tag is stored at sign-up, not on a later visit to /start.
_SIGNUP_SRC_WINDOW = timedelta(hours=24)


def _parse_ts(value: object) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    text = str(value).replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _parse_date(value: object) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _dump_ts(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(UTC).isoformat()


def _dump_date(value: date | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _claim_open(claimed_at: object, now: datetime) -> bool:
    parsed = _parse_ts(claimed_at)
    if parsed is None:
        return True
    return parsed <= now - CLAIM_STALE


def _state_from_row(row: dict) -> FollowUpState:
    return FollowUpState(
        signup_src=row.get("signup_src"),
        signup_referrer_domain=row.get("signup_referrer_domain"),
        signup_utm_source=row.get("signup_utm_source"),
        signup_utm_medium=row.get("signup_utm_medium"),
        signup_utm_campaign=row.get("signup_utm_campaign"),
        test_on=_parse_date(row.get("recruit_test_on")),
        reminder_due_at=_parse_ts(row.get("recruit_reminder_due_at")),
        reminder_sent_for=_parse_date(row.get("recruit_reminder_sent_for")),
        unsubscribed_at=_parse_ts(row.get("recruit_unsubscribed_at")),
    )


def _profile(db: Client, user_id: str) -> dict | None:
    rows = (
        db.table("profiles")
        .select(_PROFILE_FIELDS)
        .eq("id", user_id)
        .limit(1)
        .execute()
        .data
        or []
    )
    return rows[0] if rows else None


def _write_state(db: Client, user_id: str, state: FollowUpState) -> None:
    db.table("profiles").update(
        {
            "signup_src": state.signup_src,
            "signup_referrer_domain": state.signup_referrer_domain,
            "signup_utm_source": state.signup_utm_source,
            "signup_utm_medium": state.signup_utm_medium,
            "signup_utm_campaign": state.signup_utm_campaign,
            "recruit_test_on": _dump_date(state.test_on),
            "recruit_reminder_due_at": _dump_ts(state.reminder_due_at),
            "recruit_reminder_sent_for": _dump_date(state.reminder_sent_for),
            "recruit_unsubscribed_at": _dump_ts(state.unsubscribed_at),
        }
    ).eq("id", user_id).execute()


class ActivationPublic:
    """The slice /me is allowed to show. No email token."""

    def __init__(
        self,
        *,
        free_board_open: bool,
        signup_src: str | None,
        recruit_test_on: date | None,
    ) -> None:
        self.free_board_open = free_board_open
        self.signup_src = signup_src
        self.recruit_test_on = recruit_test_on


def read_activation_public(db: Client, settings: Settings) -> ActivationPublic:
    """Candidate client. RLS scopes both tables to the signed-in user."""
    from app.storage.boards import count_completed_boards

    rows = (
        db.table("profiles").select("signup_src,recruit_test_on").limit(1).execute().data or []
    )
    row = rows[0] if rows else {}
    completed = count_completed_boards(db)
    return ActivationPublic(
        free_board_open=completed < settings.recruit_free_sessions,
        signup_src=row.get("signup_src"),
        recruit_test_on=_parse_date(row.get("recruit_test_on")),
    )


def store_signup_src(
    db: Client,
    user_id: str,
    raw: str | None,
    now: datetime | None = None,
    *,
    referrer_domain: str | None = None,
    utm_source: str | None = None,
    utm_medium: str | None = None,
    utm_campaign: str | None = None,
) -> None:
    """First valid tag and first-touch columns, only while the account is still new."""
    row = _profile(db, user_id)
    if row is None:
        return
    moment = now or datetime.now(UTC)
    created = _parse_ts(row.get("created_at"))
    if created is None or moment - created > _SIGNUP_SRC_WINDOW:
        return
    state = _state_from_row(row)
    updated = apply_signup_attribution(
        state,
        src=raw,
        referrer_domain=referrer_domain,
        utm_source=utm_source,
        utm_medium=utm_medium,
        utm_campaign=utm_campaign,
    )
    if updated == state:
        return
    _write_state(db, user_id, updated)


def store_test_date(db: Client, user_id: str, test_on: date | None, now: datetime) -> None:
    row = _profile(db, user_id)
    if row is None:
        return
    state = apply_test_date(_state_from_row(row), test_on, now)
    _write_state(db, user_id, state)
    db.table("profiles").update({"recruit_reminder_claimed_at": None}).eq("id", user_id).execute()


def unsubscribe_token(db: Client, token: str, now: datetime) -> bool:
    text = token.strip()
    if not text:
        return False
    rows = (
        db.table("profiles")
        .select("id")
        .eq("recruit_email_token", text)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        return False
    user_id = rows[0]["id"]
    row = _profile(db, user_id)
    if row is None:
        return False
    state = apply_unsubscribe(_state_from_row(row), now)
    _write_state(db, user_id, state)
    db.table("profiles").update(
        {"recruit_reminder_claimed_at": None, "recruit_results_claimed_at": None}
    ).eq("id", user_id).execute()
    return True


def completed_released_count(db: Client, user_id: str) -> int:
    """Service role. Filter by user — RLS is not in force on this client."""
    rows = (
        db.table("recruit_boards")
        .select("id,status,notes_released,c1_candidate_lines")
        .eq("user_id", user_id)
        .eq("status", "completed")
        .execute()
        .data
        or []
    )
    return sum(
        1
        for row in rows
        if notes_were_released(
            row.get("status") or "",
            row.get("notes_released"),
            row.get("c1_candidate_lines"),
        )
    )


def load_summary(db: Client, user_id: str) -> BoardSummary | None:
    """The lines the board screen already showed. No rubric fields."""
    rows = (
        db.table("recruit_boards")
        .select("id,status,notes_released,c1_candidate_lines,completed_at")
        .eq("user_id", user_id)
        .eq("status", "completed")
        .order("completed_at")
        .execute()
        .data
        or []
    )
    chosen = next(
        (
            row
            for row in rows
            if notes_were_released(
                row.get("status") or "",
                row.get("notes_released"),
                row.get("c1_candidate_lines"),
            )
        ),
        None,
    )
    if chosen is None:
        return None
    answers: list[BoardAnswerNote] = []
    for row in worker_board_attempts(db, chosen["id"]):
        raw_lines = row.get("candidate_lines") or []
        if not isinstance(raw_lines, list):
            raw_lines = []
        answers.append(
            BoardAnswerNote(
                question_index=int(row.get("slot_index") or 0) + 1,
                question_text=str(row.get("question_text") or ""),
                lines=[str(line) for line in raw_lines],
            )
        )
    answers.sort(key=lambda item: item.question_index)
    c1 = chosen.get("c1_candidate_lines") or []
    if not isinstance(c1, list):
        c1 = []
    return BoardSummary(answers=answers, c1_lines=[str(line) for line in c1])


def mark_free_board_ready(db: Client, user_id: str, now: datetime) -> None:
    row = _profile(db, user_id)
    if row is None:
        return
    if row.get("recruit_results_sent_at") or row.get("recruit_results_ready_at"):
        return
    token = row.get("recruit_email_token") or secrets.token_urlsafe(32)
    (
        db.table("profiles")
        .update(
            {
                "recruit_results_ready_at": _dump_ts(now),
                "recruit_email_token": token,
            }
        )
        .eq("id", user_id)
        .is_("recruit_results_ready_at", "null")
        .execute()
    )


def on_free_board_completed(db: Client, settings: Settings, user_id: str, now: datetime) -> None:
    """The first released board is the free one. Later boards do not email."""
    if settings.recruit_free_sessions < 1:
        return
    if completed_released_count(db, user_id) != 1:
        return
    mark_free_board_ready(db, user_id, now)


def backfill_recent_free_boards(db: Client, settings: Settings, now: datetime) -> None:
    """Catch a completion whose hook did not mark the row. Not a history blast."""
    if settings.recruit_free_sessions < 1:
        return
    cutoff = _dump_ts(now - timedelta(hours=24))
    rows = (
        db.table("recruit_boards")
        .select("user_id,completed_at,status")
        .eq("status", "completed")
        .gte("completed_at", cutoff)
        .limit(100)
        .execute()
        .data
        or []
    )
    seen: list[str] = []
    for row in rows:
        user_id = row.get("user_id")
        if user_id and user_id not in seen:
            seen.append(str(user_id))
    for user_id in seen:
        if completed_released_count(db, user_id) == 1:
            mark_free_board_ready(db, user_id, now)


class SupabaseFollowUpRepo:
    def __init__(self, db: Client) -> None:
        self._db = db

    def due_results(self, now: datetime) -> list[DueResults]:
        rows = (
            self._db.table("profiles")
            .select(_PROFILE_FIELDS)
            .is_("recruit_results_sent_at", "null")
            .is_("recruit_unsubscribed_at", "null")
            .lte("recruit_results_ready_at", _dump_ts(now))
            .limit(50)
            .execute()
            .data
            or []
        )
        due: list[DueResults] = []
        for row in rows:
            if not row.get("recruit_results_ready_at"):
                continue
            if not _claim_open(row.get("recruit_results_claimed_at"), now):
                continue
            email = (row.get("email") or "").strip()
            token = (row.get("recruit_email_token") or "").strip()
            if not email or not token:
                continue
            summary = load_summary(self._db, row["id"])
            if summary is None:
                continue
            due.append(DueResults(user_id=row["id"], email=email, token=token, summary=summary))
        return due

    def due_reminders(self, now: datetime) -> list[DueReminder]:
        rows = (
            self._db.table("profiles")
            .select(_PROFILE_FIELDS)
            .is_("recruit_unsubscribed_at", "null")
            .lte("recruit_reminder_due_at", _dump_ts(now))
            .limit(50)
            .execute()
            .data
            or []
        )
        due: list[DueReminder] = []
        for row in rows:
            if not row.get("recruit_reminder_due_at"):
                continue
            if not _claim_open(row.get("recruit_reminder_claimed_at"), now):
                continue
            test_on = _parse_date(row.get("recruit_test_on"))
            sent_for = _parse_date(row.get("recruit_reminder_sent_for"))
            email = (row.get("email") or "").strip()
            token = (row.get("recruit_email_token") or "").strip()
            if test_on is None or sent_for == test_on or not email or not token:
                continue
            due.append(
                DueReminder(user_id=row["id"], email=email, token=token, test_on=test_on)
            )
        return due

    def claim_results(self, user_id: str, now: datetime) -> bool:
        # One results email per account. A sent row is not claimable again.
        return self._claim(
            user_id, now, "recruit_results_claimed_at", sent_key="recruit_results_sent_at"
        )

    def claim_reminder(self, user_id: str, now: datetime) -> bool:
        # sent_for records which date already got its one reminder. A later
        # date is still claimable, so this lock is only the claim column.
        return self._claim(user_id, now, "recruit_reminder_claimed_at", sent_key=None)

    def _claim(
        self, user_id: str, now: datetime, claim_key: str, *, sent_key: str | None
    ) -> bool:
        stamped = _dump_ts(now)
        fresh_query = (
            self._db.table("profiles")
            .update({claim_key: stamped})
            .eq("id", user_id)
            .is_(claim_key, "null")
        )
        if sent_key is not None:
            fresh_query = fresh_query.is_(sent_key, "null")
        if fresh_query.execute().data:
            return True
        row = _profile(self._db, user_id)
        if row is None or not _claim_open(row.get(claim_key), now):
            return False
        if sent_key is not None and row.get(sent_key):
            return False
        old = row.get(claim_key)
        if old is None:
            return False
        steal = (
            self._db.table("profiles")
            .update({claim_key: stamped})
            .eq("id", user_id)
            .eq(claim_key, old)
        )
        if sent_key is not None:
            steal = steal.is_(sent_key, "null")
        return bool(steal.execute().data)

    def mark_results_sent(self, user_id: str, now: datetime) -> None:
        self._db.table("profiles").update(
            {
                "recruit_results_sent_at": _dump_ts(now),
                "recruit_results_claimed_at": None,
            }
        ).eq("id", user_id).execute()

    def mark_reminder_sent(self, user_id: str, test_on: date, now: datetime) -> None:
        del now
        self._db.table("profiles").update(
            {
                "recruit_reminder_sent_for": _dump_date(test_on),
                "recruit_reminder_due_at": None,
                "recruit_reminder_claimed_at": None,
            }
        ).eq("id", user_id).execute()

    def clear_results_claim(self, user_id: str) -> None:
        self._db.table("profiles").update({"recruit_results_claimed_at": None}).eq(
            "id", user_id
        ).execute()

    def clear_reminder_claim(self, user_id: str) -> None:
        self._db.table("profiles").update({"recruit_reminder_claimed_at": None}).eq(
            "id", user_id
        ).execute()


def run_followup(
    db: Client,
    settings: Settings,
    *,
    sender: EmailSender | None = None,
    now: datetime | None = None,
):
    moment = now or datetime.now(UTC)
    backfill_recent_free_boards(db, settings, moment)
    return dispatch_due(
        SupabaseFollowUpRepo(db),
        sender if sender is not None else build_sender(settings),
        settings,
        moment,
    )
