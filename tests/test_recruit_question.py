"""BD-R-002: available vs exhausted discriminant on GET /recruit/question.

Exhaustion is a 200 milestone, not a 404. Tests force the empty/seen bank with
a fixture — the full ~290 launch bank is not required. No new read-model
migration: answered_count and bank_size come from published_items + attempt
scenario ids.
"""

from pathlib import Path

from app.api.recruit import RecruitQuestionAvailable, RecruitQuestionExhausted
from app.critique.cli import QUESTIONS
from app.recruit.bank import (
    AvailableIssue,
    BankItem,
    ExhaustedIssue,
    issue,
    published_items,
)
from tests.test_recruit_attempts import _client, _settings

WEB = Path(__file__).resolve().parents[1] / "web" / "src"


def test_live_bank_is_c2_only() -> None:
    items = published_items()
    assert [item.scenario_id for item in items] == ["c2"]
    assert items[0].question_text == QUESTIONS["c2"]
    assert 290 not in (item.scenario_id for item in items)


def test_issue_available_when_bank_has_an_unseen_item() -> None:
    decision = issue([])
    assert isinstance(decision, AvailableIssue)
    assert decision.scenario_id == "c2"
    assert decision.question_text == QUESTIONS["c2"]


def test_issue_exhausted_when_every_published_item_was_seen() -> None:
    decision = issue(["c2"])
    assert isinstance(decision, ExhaustedIssue)
    assert decision.answered_count == 1
    assert decision.bank_size == 1
    assert decision.next_eligible_at is None


def test_issue_exhausted_on_empty_bank_fixture() -> None:
    decision = issue([], bank=())
    assert isinstance(decision, ExhaustedIssue)
    assert decision.answered_count == 0
    assert decision.bank_size == 0
    assert decision.next_eligible_at is None


def test_issue_skips_seen_and_does_not_need_the_full_bank() -> None:
    bank = (
        BankItem(scenario_id="a", question_text="First novel prompt."),
        BankItem(scenario_id="b", question_text="Second novel prompt."),
    )
    decision = issue(["a"], bank=bank)
    assert isinstance(decision, AvailableIssue)
    assert decision.scenario_id == "b"
    exhausted = issue(["a", "b"], bank=bank)
    assert isinstance(exhausted, ExhaustedIssue)
    assert exhausted.answered_count == 2
    assert exhausted.bank_size == 2


def test_get_question_available(monkeypatch) -> None:
    response = _client(_settings(), monkeypatch).get("/recruit/question")
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "available"
    assert body["scenario_id"] == "c2"
    assert body["question_text"] == QUESTIONS["c2"]
    assert "answered_count" not in body
    RecruitQuestionAvailable.model_validate(body)


def test_get_question_exhausted_is_200_not_404(monkeypatch) -> None:
    response = _client(_settings(), monkeypatch, seen_scenario_ids=["c2"]).get(
        "/recruit/question"
    )
    assert response.status_code == 200
    assert response.status_code != 404
    body = response.json()
    assert body["state"] == "exhausted"
    assert body["answered_count"] == 1
    assert body["bank_size"] == 1
    assert body["next_eligible_at"] is None
    assert "scenario_id" not in body
    RecruitQuestionExhausted.model_validate(body)


def test_get_question_empty_bank_fixture_is_exhausted_200(monkeypatch) -> None:
    monkeypatch.setattr("app.recruit.bank.published_items", lambda: ())
    response = _client(_settings(), monkeypatch, seen_scenario_ids=[]).get(
        "/recruit/question"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "exhausted"
    assert body["answered_count"] == 0
    assert body["bank_size"] == 0


def test_unauthenticated_question_is_401(monkeypatch) -> None:
    response = _client(_settings(), monkeypatch, authed=False).get("/recruit/question")
    assert response.status_code == 401


def test_post_attempt_rejected_when_exhausted(monkeypatch) -> None:
    created: list[str] = []

    def fake_create(db, user_id, **kwargs):
        created.append(user_id)
        raise AssertionError("exhausted POST must not create an attempt")

    monkeypatch.setattr("app.api.recruit.count_attempts", lambda *a, **k: 0)
    monkeypatch.setattr("app.recruit.gate.recruit_entitled", lambda *a: True)
    monkeypatch.setattr("app.api.recruit.create_queued_attempt", fake_create)

    response = _client(_settings(), monkeypatch, seen_scenario_ids=["c2"]).post(
        "/recruit/attempts",
        files={"audio": ("answer.webm", b"fake-audio", "audio/webm")},
    )
    assert 400 <= response.status_code < 500
    assert response.status_code == 409
    assert created == []


def test_post_attempt_still_202_when_available(monkeypatch) -> None:
    from tests.test_recruit_attempts import _record

    monkeypatch.setattr("app.api.recruit.count_attempts", lambda *a, **k: 0)
    monkeypatch.setattr("app.recruit.gate.recruit_entitled", lambda *a: False)
    monkeypatch.setattr("app.api.recruit.create_queued_attempt", lambda *a, **k: _record())

    response = _client(_settings(), monkeypatch).post(
        "/recruit/attempts",
        files={"audio": ("answer.webm", b"fake-audio", "audio/webm")},
    )
    assert response.status_code == 202


def test_client_discriminates_state_and_never_records_on_exhausted() -> None:
    recruit = (WEB / "ui" / "Recruit.tsx").read_text()
    api = (WEB / "lib" / "api.ts").read_text()
    milestone = (WEB / "ui" / "RecruitMilestone.tsx").read_text()

    assert "RecruitQuestion" in api
    assert "state: 'available'" in api
    assert "state: 'exhausted'" in api
    assert "issued.state === 'exhausted'" in recruit
    assert "setPhase('milestone')" in recruit
    assert "phase === 'ready' && question" in recruit
    assert "Record answer" in recruit
    assert "Record" not in milestone
    assert "Stop" not in milestone
    assert "Submit" not in milestone
    assert "Could not load the question" not in milestone


def test_milestone_copy_is_signed_and_rejects_about_and_retirement() -> None:
    copy = (WEB / "lib" / "recruitMilestone.ts").read_text()
    screen = (WEB / "ui" / "RecruitMilestone.tsx").read_text()
    joined = copy + screen
    assert (
        "You've answered every question we have — ${answeredCount} of them, none twice."
        in copy
    )
    assert "about ${answeredCount}" not in joined
    assert "about {" not in joined
    assert "retirement" not in joined
    assert (
        "The tool has said what it can. Surprise is used up; rehearsed repeats "
        "train the wrong skill, so we won't offer them."
    ) in copy
    assert (
        "Looking back across your recent answers — what held and what still drops "
        "under pressure will show here once we have enough history to summarize. "
        "This is not a locked door."
    ) in copy
    assert (
        "Next reps belong in front of people — a mentor mock board, a station visit, "
        "or a ride-along. We name the routes; we don't book the provider."
    ) in copy
    assert (
        "Nothing new until we add questions or older ones come back into rotation."
        in copy
    )
    assert "Pause from your account page; we'll email when there's more." in copy
    assert "gap-plan" not in joined.lower()
    assert "custom entry" not in joined.lower()
    assert "BANK_EXHAUSTED_EVENT" in screen
    assert "answered_count: answeredCount" in screen
    assert "bank_size: bankSize" in screen


def test_milestone_billing_omits_pause_for_free_and_skips_stripe_for_store() -> None:
    copy = (WEB / "lib" / "recruitMilestone.ts").read_text()
    screen = (WEB / "ui" / "RecruitMilestone.tsx").read_text()
    assert "subscription_status !== 'none'" in copy
    assert "managed_by === 'play'" in copy
    assert "managed_by === 'appstore'" in copy
    assert "billing !== 'none'" in screen
    assert "api.billing.portal" in screen
    assert "caught.status === 409" in screen
    assert "Nothing was paused" in copy
    assert "onOpenAccount" in screen
    assert "onManageBilling" in screen


def test_analytics_fires_only_from_the_milestone_screen() -> None:
    helper = (WEB / "lib" / "analytics.ts").read_text()
    copy = (WEB / "lib" / "recruitMilestone.ts").read_text()
    assert "tracker()?.track" in helper
    recruit = (WEB / "ui" / "Recruit.tsx").read_text()
    milestone = (WEB / "ui" / "RecruitMilestone.tsx").read_text()
    assert "recruit_bank_exhausted_viewed" not in recruit
    assert "recruit_bank_exhausted_viewed" in copy
    assert "BANK_EXHAUSTED_EVENT" in milestone
    assert "api.recruit" in recruit
    assert ".question()" in recruit


def test_answered_count_is_computed_without_a_new_read_model() -> None:
    """answered_count / bank_size come from the live bank plus attempt rows."""
    storage = (
        Path(__file__).resolve().parents[1] / "app" / "storage" / "recruit.py"
    ).read_text()
    assert "def attempted_scenario_ids" in storage
    bank = (Path(__file__).resolve().parents[1] / "app" / "recruit" / "bank.py").read_text()
    assert "answered_count=len(seen & bank_ids)" in bank
