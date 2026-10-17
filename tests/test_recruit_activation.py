"""BD-RECRUIT-ACT-001: /start tag, one results email, one reminder, unsubscribe.

The store is the real Supabase adapter against an in-memory table. No network.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.activation import router as activation_router
from app.api.deps import CurrentUser, current_user, service_db
from app.config import Settings
from app.recruit.followup import (
    FORBIDDEN_WORDS,
    PRACTICE_NOTE,
    RESULTS_SUBJECT,
    BoardSummary,
    FollowUpState,
    apply_signup_attribution,
    apply_signup_src,
    apply_test_date,
    render_results,
)
from app.recruit.mail import LogSender, ResendSender, SendResult, build_sender
from app.storage.activation import run_followup, store_signup_src, store_test_date

ROOT = Path(__file__).resolve().parents[1]
USER = "44444444-4444-4444-4444-444444444444"
NOW = datetime(2026, 10, 15, 15, tzinfo=UTC)
ADDRESS = "Sirens to Syntax LLC\n1433 201st Drive\nSeward, NE 68434"
PRICE = "paid plans from $24.99/mo"
NOTE = "You named a specific crew and what you did there."
QUESTION = "Why do you want to be a firefighter?"
C1 = "Across these five answers — how they were built. Not a score on any one of them."


class FakeQuery:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows
        self._filters: list[tuple] = []
        self._op = "select"
        self._patch: dict | None = None
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    def select(self, *_args):
        self._op = "select"
        return self

    def update(self, patch: dict):
        self._op = "update"
        self._patch = patch
        return self

    def eq(self, key, value):
        self._filters.append(("eq", key, value))
        return self

    def is_(self, key, value):
        self._filters.append(("is", key, value))
        return self

    def lte(self, key, value):
        self._filters.append(("lte", key, value))
        return self

    def gte(self, key, value):
        self._filters.append(("gte", key, value))
        return self

    def order(self, key, desc=False):
        self._order = (key, desc)
        return self

    def limit(self, count):
        self._limit = count
        return self

    def _match(self, row: dict) -> bool:
        for kind, key, value in self._filters:
            have = row.get(key)
            if kind == "eq" and have != value:
                return False
            if kind == "is" and value == "null" and have is not None:
                return False
            if kind == "lte" and (have is None or have > value):
                return False
            if kind == "gte" and (have is None or have < value):
                return False
        return True

    def execute(self):
        matched = [row for row in self._rows if self._match(row)]
        if self._order:
            key, desc = self._order
            matched.sort(key=lambda row: (row.get(key) is None, str(row.get(key))), reverse=desc)
        if self._limit is not None:
            matched = matched[: self._limit]
        if self._op == "update" and self._patch is not None:
            for row in matched:
                row.update(self._patch)
        return SimpleNamespace(data=[dict(row) for row in matched])


class FakeDb:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict]] = {
            "profiles": [],
            "recruit_boards": [],
            "recruit_attempts": [],
        }

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self.tables.setdefault(name, []))


class RecordingSender:
    configured = True

    def __init__(self) -> None:
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        return SendResult(delivered=True)


def _settings(**overrides) -> Settings:
    values = {
        "mailing_address": ADDRESS,
        "public_web_url": "https://app.badgeday.com",
        "recruit_free_sessions": 1,
        "recruit_price_line": PRICE,
        "resend_api_key": "re_test",
        "email_from": "hello@badgeday.com",
    }
    values.update(overrides)
    return Settings(**values)


def _profile(**extra) -> dict:
    row = {
        "id": USER,
        "email": "candidate@example.com",
        "created_at": NOW.isoformat(),
        "signup_src": None,
        "recruit_test_on": None,
        "recruit_reminder_due_at": None,
        "recruit_reminder_sent_for": None,
        "recruit_reminder_claimed_at": None,
        "recruit_results_ready_at": None,
        "recruit_results_sent_at": None,
        "recruit_results_claimed_at": None,
        "recruit_unsubscribed_at": None,
        "recruit_email_token": None,
    }
    row.update(extra)
    return row


def _finished_board(db: FakeDb, *, when: datetime = NOW, user_id: str = USER) -> None:
    db.tables["recruit_boards"].append(
        {
            "id": "board-1",
            "user_id": user_id,
            "status": "completed",
            "notes_released": True,
            "c1_candidate_lines": [C1],
            "completed_at": when.isoformat(),
        }
    )
    db.tables["recruit_attempts"].append(
        {
            "id": "attempt-1",
            "board_id": "board-1",
            "user_id": user_id,
            "slot_index": 0,
            "status": "completed",
            "question_text": QUESTION,
            "candidate_lines": [NOTE, ""],
        }
    )


def _db() -> FakeDb:
    db = FakeDb()
    db.tables["profiles"].append(_profile())
    _finished_board(db)
    return db


def _row(db: FakeDb) -> dict:
    return db.tables["profiles"][0]


def test_price_line_is_the_live_monthly_line_and_nothing_else() -> None:
    doc = (ROOT / "badgeday_pricing.md").read_text()
    assert "$24.99/mo" in doc
    assert Settings().recruit_price_line == PRICE
    followup = (ROOT / "app/recruit/followup.py").read_text()
    mail = (ROOT / "app/recruit/mail.py").read_text()
    assert "24.99" not in followup
    assert "24.99" not in mail
    for name in ("Grant",):
        assert name not in followup
        assert name not in mail
        assert name not in (ROOT / "app/api/activation.py").read_text()


def test_signup_src_is_stored_once_and_a_missing_tag_writes_nothing() -> None:
    db = FakeDb()
    db.tables["profiles"].append(_profile())
    store_signup_src(db, USER, None, NOW)
    assert _row(db)["signup_src"] is None
    store_signup_src(db, USER, "a@b.com", NOW)
    store_signup_src(db, USER, " ", NOW)
    assert _row(db)["signup_src"] is None

    store_signup_src(db, USER, "test1", NOW)
    assert _row(db)["signup_src"] == "test1"
    store_signup_src(db, USER, "nebraska-nov", NOW)
    assert _row(db)["signup_src"] == "test1"

    old = FakeDb()
    old.tables["profiles"].append(
        _profile(created_at=(NOW - timedelta(days=30)).isoformat())
    )
    store_signup_src(old, USER, "test1", NOW)
    assert old.tables["profiles"][0]["signup_src"] is None

    # The pure rule matches: no tag, no write; a second tag does not replace.
    assert apply_signup_src(FollowUpState(), None).signup_src is None
    once = apply_signup_src(FollowUpState(), "test1")
    assert apply_signup_src(once, "other").signup_src == "test1"


def test_first_touch_keeps_src_and_stores_referrer_and_utm_once() -> None:
    db = FakeDb()
    db.tables["profiles"].append(_profile())
    store_signup_src(
        db,
        USER,
        "test1",
        NOW,
        referrer_domain="news.ycombinator.com",
        utm_source="hn",
        utm_medium="social",
        utm_campaign="oct",
    )
    row = _row(db)
    assert row["signup_src"] == "test1"
    assert row["signup_referrer_domain"] == "news.ycombinator.com"
    assert row["signup_utm_source"] == "hn"
    assert row["signup_utm_medium"] == "social"
    assert row["signup_utm_campaign"] == "oct"

    # A later landing does not replace the first write, and src stays the tag.
    store_signup_src(
        db,
        USER,
        "other",
        NOW,
        referrer_domain="bing.com",
        utm_source="bing",
        utm_medium="cpc",
        utm_campaign="later",
    )
    assert _row(db)["signup_src"] == "test1"
    assert _row(db)["signup_referrer_domain"] == "news.ycombinator.com"
    assert _row(db)["signup_utm_source"] == "hn"

    # No ?src= still records the touch, and does not invent a signup_src.
    bare = FakeDb()
    bare.tables["profiles"].append(_profile())
    store_signup_src(
        bare,
        USER,
        None,
        NOW,
        referrer_domain="google.com",
        utm_source="newsletter",
        utm_medium="email",
        utm_campaign="oct-16",
    )
    assert _row(bare)["signup_src"] is None
    assert _row(bare)["signup_referrer_domain"] == "google.com"
    assert _row(bare)["signup_utm_source"] == "newsletter"

    # Path, own hosts, IPs, and tags that fail the src rule are dropped.
    dropped = FakeDb()
    dropped.tables["profiles"].append(_profile())
    store_signup_src(
        dropped,
        USER,
        None,
        NOW,
        referrer_domain="https://news.ycombinator.com/item?id=1",
        utm_source="has space",
        utm_medium="email",
        utm_campaign="x" * 65,
    )
    assert _row(dropped)["signup_src"] is None
    assert _row(dropped)["signup_referrer_domain"] is None
    assert _row(dropped)["signup_utm_source"] is None
    assert _row(dropped)["signup_utm_medium"] == "email"
    assert _row(dropped)["signup_utm_campaign"] is None

    for host in (
        "app.badgeday.com",
        "www.badgeday.com",
        "BADGEDAY.COM",
        "api.badgeday.com",
        "badgeday.app",
        "www.badgeday.app",
        "sirenstosyntax.com",
        "WWW.SIRENSTOSYNTAX.COM",
        "8.8.8.8",
        "2001:db8::1",
    ):
        again = FakeDb()
        again.tables["profiles"].append(_profile())
        store_signup_src(again, USER, None, NOW, referrer_domain=host)
        assert again.tables["profiles"][0].get("signup_referrer_domain") is None
        assert again.tables["profiles"][0]["signup_src"] is None

    old = FakeDb()
    old.tables["profiles"].append(
        _profile(created_at=(NOW - timedelta(days=30)).isoformat())
    )
    store_signup_src(old, USER, None, NOW, referrer_domain="google.com", utm_source="hn")
    assert old.tables["profiles"][0].get("signup_referrer_domain") is None
    assert old.tables["profiles"][0].get("signup_utm_source") is None

    tagged = apply_signup_attribution(
        FollowUpState(),
        src="test1",
        referrer_domain="google.com",
    )
    assert tagged.signup_src == "test1"
    assert tagged.signup_referrer_domain == "google.com"
    assert apply_signup_attribution(tagged, src="other", referrer_domain="bing.com") == tagged

    migration = (ROOT / "supabase/migrations/0018_signup_first_touch.sql").read_text()
    assert "add column if not exists signup_referrer_domain text" in migration
    assert "add column if not exists signup_utm_source text" in migration
    assert "add column if not exists signup_utm_medium text" in migration
    assert "add column if not exists signup_utm_campaign text" in migration
    assert "profiles_signup_referrer_domain_shape" in migration
    assert "if not exists" in migration
    assert "create table" not in migration.lower()


def test_finishing_the_free_board_sends_one_results_email_within_five_minutes() -> None:
    db = _db()
    settings = _settings()
    run_followup(db, settings, sender=LogSender(), now=NOW)
    assert _row(db)["recruit_results_ready_at"] == NOW.isoformat()
    assert _row(db)["recruit_results_sent_at"] is None

    sender = RecordingSender()
    later = NOW + timedelta(minutes=4)
    report = run_followup(db, settings, sender=sender, now=later)
    assert report.results_sent == 1
    assert len(sender.messages) == 1
    again = run_followup(db, settings, sender=sender, now=later + timedelta(minutes=1))
    assert again.results_sent == 0
    assert len(sender.messages) == 1

    message = sender.messages[0]
    text = message.text
    assert message.subject == RESULTS_SUBJECT
    assert QUESTION in text
    assert NOTE in text
    assert C1 in text
    assert "Continue: https://app.badgeday.com/start" in text
    assert "When is your test? https://app.badgeday.com/recruit/test-date" in text
    assert "Unsubscribe: https://app.badgeday.com/email/unsubscribe?token=" in text
    assert "1433 201st Drive" in text
    assert "Sirens to Syntax LLC" in text
    assert "BadgeDay" in text
    assert PRICE in text
    assert text.count("$") == 1
    for needle in ("$59", "$119", "$179", "$29", "$129"):
        assert needle not in text
    assert FORBIDDEN_WORDS.search(text) is None
    token = _row(db)["recruit_email_token"]
    assert token
    assert f"token={token}" in text
    assert message.headers["List-Unsubscribe"] == (
        f"<https://app.badgeday.com/email/unsubscribe?token={token}>"
    )
    assert message.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "Grant" not in text


def test_results_email_states_it_was_practice() -> None:
    message = render_results(
        BoardSummary(answers=[], c1_lines=[]),
        continue_url="https://app.badgeday.com/start",
        test_date_url="https://app.badgeday.com/recruit/test-date",
        unsub_url="https://app.badgeday.com/email/unsubscribe?token=t",
        address=ADDRESS,
        price_line=PRICE,
    )
    assert message.subject == "Your BadgeDay practice board notes"
    assert message.subject == RESULTS_SUBJECT
    assert PRACTICE_NOTE in message.text
    assert message.text.index(PRACTICE_NOTE) > message.text.index("Board complete")
    assert FORBIDDEN_WORDS.search(message.text) is None
    assert FORBIDDEN_WORDS.search(message.subject) is None


def test_a_second_board_does_not_send_another_results_email() -> None:
    db = _db()
    db.tables["recruit_boards"].append(
        {
            "id": "board-2",
            "user_id": USER,
            "status": "completed",
            "notes_released": True,
            "c1_candidate_lines": ["Second board."],
            "completed_at": NOW.isoformat(),
        }
    )
    sender = RecordingSender()
    report = run_followup(db, _settings(), sender=sender, now=NOW)
    assert report.results_sent == 0
    assert sender.messages == []


def test_thirty_days_out_reminds_once_seven_days_prior_and_three_days_does_not() -> None:
    db = _db()
    settings = _settings()
    run_followup(db, settings, sender=RecordingSender(), now=NOW)

    far = date(2026, 11, 14)
    store_test_date(db, USER, far, NOW)
    assert _row(db)["recruit_test_on"] == far.isoformat()
    assert _row(db)["recruit_reminder_due_at"] == datetime(2026, 11, 7, tzinfo=UTC).isoformat()

    sender = RecordingSender()
    day_before = datetime(2026, 11, 6, 12, tzinfo=UTC)
    assert run_followup(db, settings, sender=sender, now=day_before).reminders_sent == 0
    due = datetime(2026, 11, 7, 0, tzinfo=UTC)
    assert run_followup(db, settings, sender=sender, now=due).reminders_sent == 1
    later = run_followup(db, settings, sender=sender, now=due + timedelta(hours=3))
    assert later.reminders_sent == 0
    assert len(sender.messages) == 1
    reminder = sender.messages[0]
    assert reminder.subject == "Practice before your test"
    assert "Practice: https://app.badgeday.com/start" in reminder.text
    assert "2026-11-14" in reminder.text
    assert "Unsubscribe:" in reminder.text
    assert "1433 201st Drive" in reminder.text
    assert "$" not in reminder.text
    assert FORBIDDEN_WORDS.search(reminder.text) is None
    assert reminder.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert _row(db)["recruit_reminder_sent_for"] == far.isoformat()
    assert _row(db)["recruit_reminder_due_at"] is None

    # Same date again does not schedule a second reminder.
    store_test_date(db, USER, far, due)
    assert _row(db)["recruit_reminder_due_at"] is None

    near = _db()
    run_followup(near, settings, sender=RecordingSender(), now=NOW)
    soon = date(2026, 10, 18)
    store_test_date(near, USER, soon, NOW)
    assert near.tables["profiles"][0]["recruit_reminder_due_at"] is None
    quiet = RecordingSender()
    on_the_day = datetime(2026, 10, 18, 12, tzinfo=UTC)
    assert run_followup(near, settings, sender=quiet, now=on_the_day).reminders_sent == 0
    assert quiet.messages == []
    assert apply_test_date(FollowUpState(), soon, NOW).reminder_due_at is None


def test_unsubscribe_cancels_the_pending_reminder() -> None:
    db = _db()
    settings = _settings()
    run_followup(db, settings, sender=RecordingSender(), now=NOW)
    store_test_date(db, USER, date(2026, 11, 14), NOW)
    token = _row(db)["recruit_email_token"]

    app = FastAPI()
    app.include_router(activation_router)
    app.dependency_overrides[service_db] = lambda: db
    client = TestClient(app)
    page = client.get(f"/email/unsubscribe?token={token}")
    assert page.status_code == 200
    assert "unsubscribed" in page.text.lower()
    assert FORBIDDEN_WORDS.search(page.text) is None
    assert _row(db)["recruit_unsubscribed_at"] is not None
    assert _row(db)["recruit_reminder_due_at"] is None

    sender = RecordingSender()
    due = datetime(2026, 11, 7, tzinfo=UTC)
    assert run_followup(db, settings, sender=sender, now=due).reminders_sent == 0
    assert sender.messages == []

    # The mail client's one-click POST is the same cancellation, and it is idempotent.
    posted = client.post(
        f"/email/unsubscribe?token={token}",
        content="List-Unsubscribe=One-Click",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert posted.status_code == 200
    assert client.get("/email/unsubscribe?token=nope").status_code == 404


def test_deleting_the_account_removes_the_date_and_cancels_the_reminder() -> None:
    migration = (ROOT / "supabase/migrations/0017_recruit_activation.sql").read_text()
    initial = (ROOT / "supabase/migrations/0001_initial_schema.sql").read_text()
    assert "alter table public.profiles" in migration
    assert "recruit_test_on" in migration
    assert "recruit_reminder_due_at" in migration
    assert "create table" not in migration.lower()
    assert "id uuid primary key references auth.users(id) on delete cascade" in initial

    db = _db()
    settings = _settings()
    run_followup(db, settings, sender=RecordingSender(), now=NOW)
    store_test_date(db, USER, date(2026, 11, 14), NOW)
    assert _row(db)["recruit_test_on"] == "2026-11-14"
    db.tables["profiles"].clear()
    sender = RecordingSender()
    report = run_followup(db, settings, sender=sender, now=datetime(2026, 11, 7, tzinfo=UTC))
    assert report.reminders_sent == 0
    assert report.results_sent == 0
    assert sender.messages == []


def test_empty_mailing_address_and_missing_sender_do_not_deliver() -> None:
    db = _db()
    sender = RecordingSender()
    report = run_followup(db, _settings(mailing_address="  "), sender=sender, now=NOW)
    assert report.skipped == "mailing_address"
    assert sender.messages == []
    assert _row(db)["recruit_results_sent_at"] is None

    unconfigured = run_followup(db, _settings(), sender=LogSender(), now=NOW)
    assert unconfigured.skipped == "sender"
    assert _row(db)["recruit_results_sent_at"] is None
    assert build_sender(Settings()) is not None
    assert build_sender(Settings()).configured is False
    assert isinstance(
        build_sender(Settings(resend_api_key="re_test", email_from="hello@badgeday.com")),
        ResendSender,
    )


def test_resend_posts_the_list_unsubscribe_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode())
        captured["auth"] = request.get_header("Authorization")
        # urllib stores names via str.capitalize(), so "User-Agent" is "User-agent".
        captured["user_agent"] = request.get_header("User-agent")
        captured["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    sender = build_sender(Settings(resend_api_key="re_test", email_from="hello@badgeday.com"))
    from app.recruit.mail import OutboundEmail

    result = sender.send(
        OutboundEmail(
            to="candidate@example.com",
            subject="Your oral board notes",
            text="notes",
            headers={
                "List-Unsubscribe": "<https://app.badgeday.com/email/unsubscribe?token=abc>",
                "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
            },
        )
    )
    assert result.delivered is True
    assert captured["url"] == "https://api.resend.com/emails"
    assert captured["auth"] == "Bearer re_test"
    assert captured["user_agent"] == "BadgeDay/1.0 (+https://app.badgeday.com)"
    assert captured["body"]["from"] == "BadgeDay <hello@badgeday.com>"
    assert captured["body"]["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "re_test" not in json.dumps(captured["body"])


def test_signup_and_test_date_routes_write_the_signed_in_account() -> None:
    db = FakeDb()
    db.tables["profiles"].append(_profile(created_at=datetime.now(UTC).isoformat()))
    app = FastAPI()
    app.include_router(activation_router)
    app.dependency_overrides[current_user] = lambda: CurrentUser(
        id=USER, email="candidate@example.com", access_token="t"
    )
    app.dependency_overrides[service_db] = lambda: db
    client = TestClient(app)

    assert client.post("/me/signup-src", json={}).status_code == 204
    assert _row(db)["signup_src"] is None
    assert client.post("/me/signup-src", json={"src": "test1"}).status_code == 204
    assert _row(db)["signup_src"] == "test1"
    assert (
        client.post(
            "/me/signup-src",
            json={
                "src": "other",
                "referrer_domain": "google.com",
                "utm_source": "newsletter",
                "utm_medium": "has space",
            },
        ).status_code
        == 204
    )
    assert _row(db)["signup_src"] == "test1"
    assert _row(db)["signup_referrer_domain"] == "google.com"
    assert _row(db)["signup_utm_source"] == "newsletter"
    assert _row(db)["signup_utm_medium"] is None

    assert client.put("/me/recruit-test-date", json={"test_on": "2026-11-14"}).status_code == 204
    assert _row(db)["recruit_test_on"] == "2026-11-14"
    assert client.put("/me/recruit-test-date", json={"test_on": None}).status_code == 204
    assert _row(db)["recruit_test_on"] is None
    assert _row(db)["recruit_reminder_due_at"] is None


def test_followup_hook_is_on_the_c1_worker_and_the_sweep() -> None:
    pipeline = (ROOT / "app/worker/pipeline.py").read_text()
    runner = (ROOT / "app/worker/runner.py").read_text()
    assert "on_free_board_completed" in pipeline
    assert "run_followup" in pipeline
    assert "run_followup" in runner
