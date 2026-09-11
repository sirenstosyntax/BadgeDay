"""BD-R-002: available vs exhausted discriminant on GET /recruit/question.

Exhaustion is a 200 milestone, not a 404. Tests force the empty/seen bank with
a fixture — the full ~290 launch bank is not required. No new read-model
migration: answered_count and bank_size come from published_items + attempt
scenario ids.
"""

from pathlib import Path
from types import SimpleNamespace

from app.api.recruit import RecruitQuestionAvailable, RecruitQuestionExhausted
from app.recruit.bank import (
    AvailableIssue,
    BankItem,
    ExhaustedIssue,
    issue,
    published_items,
)
from app.storage.recruit import (
    completed_scenario_ids,
    count_delivered_attempts,
    critique_was_delivered,
)
from tests.test_recruit_attempts import _client, _settings

WEB = Path(__file__).resolve().parents[1] / "web" / "src"


def _published_ids() -> list[str]:
    return [item.scenario_id for item in published_items()]


def test_live_bank_is_the_reviewed_non_c2_set() -> None:
    items = published_items()
    assert len(items) == 272
    assert items[0].scenario_id == "MOT-1.1"
    assert items[0].question_text == "Why do you want to be a firefighter?"
    assert items[0].criterion_id == "c2"
    assert any(item.criterion_id == "c3" for item in items)
    assert any(item.criterion_id == "c1" for item in items)
    assert "c2" not in (item.scenario_id for item in items)


def test_issue_available_when_bank_has_an_unseen_item() -> None:
    decision = issue([])
    assert isinstance(decision, AvailableIssue)
    assert decision.scenario_id == "MOT-1.1"
    assert decision.question_text == "Why do you want to be a firefighter?"
    assert decision.criterion_id == "c2"


def test_issue_exhausted_when_every_published_item_was_seen() -> None:
    ids = _published_ids()
    decision = issue(ids, completed_scenario_ids=ids)
    assert isinstance(decision, ExhaustedIssue)
    assert decision.answered_count == 272
    assert decision.bank_size == 272
    assert decision.next_eligible_at is None


def test_issue_answered_count_ignores_non_completed() -> None:
    """AC3: queued / failed / abandoned ids exhaust novelty but do not count as answered."""
    ids = _published_ids()
    decision = issue(ids, completed_scenario_ids=[])
    assert isinstance(decision, ExhaustedIssue)
    assert decision.answered_count == 0
    assert decision.bank_size == 272


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
    exhausted = issue(["a", "b"], bank=bank, completed_scenario_ids=["a", "b"])
    assert isinstance(exhausted, ExhaustedIssue)
    assert exhausted.answered_count == 2
    assert exhausted.bank_size == 2
    unfinished = issue(["a", "b"], bank=bank, completed_scenario_ids=["a"])
    assert isinstance(unfinished, ExhaustedIssue)
    assert unfinished.answered_count == 1


def test_question_and_submit_share_the_same_access_check() -> None:
    """A later edit must not re-open GET while leaving POST gated."""
    source = (
        Path(__file__).resolve().parents[1] / "app" / "api" / "recruit.py"
    ).read_text()
    assert source.count("_enforce_recruit_access(") >= 2
    assert "lifetime_count=count_completed_boards(db)" in source
    assert "lifetime_count=count_attempts(db)" not in source
    assert "lifetime_count=count_delivered_attempts(db)" not in source


def test_get_question_is_402_when_the_free_critique_was_delivered(monkeypatch) -> None:
    """GET /question uses the same access check as submit. No recording into a 402."""
    response = _client(_settings(), monkeypatch, delivered_count=1).get("/recruit/question")
    assert response.status_code == 402
    assert "free oral-board session is used" in response.json()["detail"]
    assert "Recruit plan" in response.json()["detail"]


def test_get_question_available(monkeypatch) -> None:
    response = _client(_settings(), monkeypatch).get("/recruit/question")
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "available"
    assert body["scenario_id"] == "MOT-1.1"
    assert body["question_text"] == "Why do you want to be a firefighter?"
    assert "answered_count" not in body
    RecruitQuestionAvailable.model_validate(body)


def test_get_question_exhausted_is_200_not_404(monkeypatch) -> None:
    ids = _published_ids()
    response = _client(
        _settings(),
        monkeypatch,
        seen_scenario_ids=ids,
        completed_scenario_ids=ids,
    ).get("/recruit/question")
    assert response.status_code == 200
    assert response.status_code != 404
    body = response.json()
    assert body["state"] == "exhausted"
    assert body["answered_count"] == 272
    assert body["bank_size"] == 272
    assert body["next_eligible_at"] is None
    assert "scenario_id" not in body
    RecruitQuestionExhausted.model_validate(body)


def test_critique_was_delivered_requires_completed_nonempty_lines() -> None:
    assert critique_was_delivered("completed", ["WHAT YOU DID WELL", "You named one thing."])
    assert critique_was_delivered("completed", []) is False
    assert critique_was_delivered("completed", ["", "  "]) is False
    assert critique_was_delivered("completed", None) is False
    assert critique_was_delivered("queued", ["WHAT YOU DID WELL"]) is False
    assert critique_was_delivered("critique_failed", ["WHAT YOU DID WELL"]) is False
    assert critique_was_delivered("abandoned", ["WHAT YOU DID WELL"]) is False


def test_count_delivered_attempts_ignores_empty_lines_and_unfinished() -> None:
    recorded: list[tuple[str, object]] = []

    class _Query:
        def select(self, columns: str) -> "_Query":
            recorded.append(("select", columns))
            return self

        def eq(self, column: str, value: object) -> "_Query":
            recorded.append(("eq", (column, value)))
            return self

        def execute(self) -> SimpleNamespace:
            return SimpleNamespace(
                data=[
                    {"id": "empty", "status": "completed", "candidate_lines": []},
                    {
                        "id": "shown",
                        "status": "completed",
                        "candidate_lines": [
                            "WHAT YOU DID WELL",
                            "You named one thing you have done.",
                        ],
                    },
                ]
            )

    class _Db:
        def table(self, name: str) -> _Query:
            recorded.append(("table", name))
            return _Query()

    assert count_delivered_attempts(_Db()) == 1
    assert ("table", "recruit_attempts") in recorded
    assert ("eq", ("status", "completed")) in recorded


def test_completed_scenario_ids_filters_to_completed_status() -> None:
    recorded: list[tuple[str, object]] = []

    class _Query:
        def select(self, columns: str) -> "_Query":
            recorded.append(("select", columns))
            return self

        def eq(self, column: str, value: object) -> "_Query":
            recorded.append(("eq", (column, value)))
            return self

        def execute(self) -> SimpleNamespace:
            return SimpleNamespace(
                data=[
                    {"scenario_id": "c2"},
                    {"scenario_id": "c2"},
                ]
            )

    class _Db:
        def table(self, name: str) -> _Query:
            recorded.append(("table", name))
            return _Query()

    assert completed_scenario_ids(_Db()) == ["c2"]
    assert ("eq", ("status", "completed")) in recorded


def test_get_question_exhausted_answered_count_ignores_non_completed(
    monkeypatch,
) -> None:
    """A queued or failed attempt consumes novelty; it does not inflate answered_count."""
    ids = _published_ids()
    response = _client(
        _settings(),
        monkeypatch,
        seen_scenario_ids=ids,
        completed_scenario_ids=[],
    ).get("/recruit/question")
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "exhausted"
    assert body["answered_count"] == 0
    assert body["bank_size"] == 272


def test_get_question_empty_bank_fixture_is_exhausted_200(monkeypatch) -> None:
    monkeypatch.setattr("app.recruit.bank.published_items", lambda: ())
    response = _client(
        _settings(), monkeypatch, seen_scenario_ids=[], resume_open=False
    ).get("/recruit/question")
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

    monkeypatch.setattr("app.api.recruit.create_queued_attempt", fake_create)

    response = _client(_settings(), monkeypatch, seen_scenario_ids=_published_ids()).post(
        "/recruit/attempts",
        files={"audio": ("answer.webm", b"fake-audio", "audio/webm")},
    )
    assert 400 <= response.status_code < 500
    assert response.status_code == 409
    assert created == []


def test_post_attempt_still_202_when_available(monkeypatch) -> None:
    from tests.test_recruit_attempts import _record

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


def _milestone_billing(account: dict | None) -> str:
    """Mirror of web/src/lib/recruitMilestone.ts milestoneBilling.

    AC17–19: has_recruit_access (`recruit.entitled`), then how that Recruit
    entitlement is billed. Promote entitled / subscription_status are ignored.
    """
    recruit = None if account is None else account.get("recruit")
    if not recruit or not recruit.get("entitled"):
        return "none"
    if recruit.get("managed_by") in ("play", "appstore"):
        return "store"
    if recruit.get("subscription_status") != "none":
        return "stripe"
    return "none"


def _recruit_store_action(account: dict | None) -> str:
    if _milestone_billing(account) != "store":
        return "none"
    recruit = None if account is None else account.get("recruit") or {}
    if recruit.get("managed_by") == "play":
        return "play"
    if recruit.get("managed_by") == "appstore":
        return "account"
    return "none"


def _recruit_jsx(app_source: str) -> str:
    _before, sep, rest = app_source.partition("<Recruit")
    assert sep
    block, end, _tail = rest.partition("/>")
    assert end
    return block


def test_promote_subscriber_without_recruit_does_not_get_stripe_pause() -> None:
    """AC19: Promote paying + Recruit free-exhausted must not open pause / portal."""
    promote_paying_recruit_free = {
        "entitled": True,
        "subscription_status": "active",
        "managed_by": None,
        "recruit": {
            "entitled": False,
            "subscription_status": "none",
            "managed_by": None,
        },
    }
    assert _milestone_billing(promote_paying_recruit_free) == "none"
    # Promote-only shape with no recruit nest — the original failure mode.
    assert _milestone_billing({"entitled": True, "subscription_status": "active"}) == "none"
    # A stale Recruit status row without has_recruit_access is still AC19.
    assert (
        _milestone_billing(
            {
                "entitled": True,
                "subscription_status": "active",
                "recruit": {
                    "entitled": False,
                    "subscription_status": "canceled",
                    "managed_by": None,
                },
            }
        )
        == "none"
    )

    copy = (WEB / "lib" / "recruitMilestone.ts").read_text()
    assert "account.subscription_status" not in copy
    assert "account.managed_by" not in copy
    assert "account.entitled" not in copy
    assert "!recruit?.entitled" in copy
    assert "account?.recruit" in copy
    assert "recruit.subscription_status" in copy
    assert "recruit.managed_by" in copy


def test_milestone_billing_omits_pause_for_free_and_skips_stripe_for_store() -> None:
    copy = (WEB / "lib" / "recruitMilestone.ts").read_text()
    screen = (WEB / "ui" / "RecruitMilestone.tsx").read_text()
    assert _milestone_billing(None) == "none"
    assert (
        _milestone_billing(
            {
                "recruit": {
                    "entitled": False,
                    "subscription_status": "none",
                    "managed_by": None,
                }
            }
        )
        == "none"
    )
    # Store till without Recruit access is not AC18.
    assert (
        _milestone_billing(
            {
                "recruit": {
                    "entitled": False,
                    "subscription_status": "none",
                    "managed_by": "play",
                }
            }
        )
        == "none"
    )
    # Recruit pass: practice access, not a Stripe-managed sub — no pause CTA.
    assert (
        _milestone_billing(
            {
                "recruit": {
                    "entitled": True,
                    "subscription_status": "none",
                    "managed_by": None,
                }
            }
        )
        == "none"
    )
    assert (
        _milestone_billing(
            {
                "entitled": False,
                "subscription_status": "none",
                "recruit": {
                    "entitled": True,
                    "subscription_status": "active",
                    "managed_by": None,
                },
            }
        )
        == "stripe"
    )
    assert (
        _milestone_billing(
            {
                "recruit": {
                    "entitled": True,
                    "subscription_status": "active",
                    "managed_by": "play",
                }
            }
        )
        == "store"
    )
    assert "!recruit?.entitled" in copy
    assert "recruit.subscription_status !== 'none'" in copy
    assert "recruit.managed_by === 'play'" in copy
    assert "recruit.managed_by === 'appstore'" in copy
    assert "billing !== 'none'" in screen
    assert "api.billing.portal" in screen
    assert "caught.status === 409" in screen
    assert "Nothing was paused" in copy
    assert "onOpenAccount" in screen
    assert "onManageBilling" not in screen
    assert "openRecruitStore" in screen
    assert "recruitStoreAction" in screen


def test_recruit_store_cta_does_not_open_stripe_when_promote_is_stripe() -> None:
    """AC18: Recruit Play + Promote Stripe must not hit App.manageBilling / portal."""
    mixed = {
        "entitled": True,
        "subscription_status": "active",
        "managed_by": None,
        "recruit": {
            "entitled": True,
            "subscription_status": "active",
            "managed_by": "play",
        },
    }
    assert _milestone_billing(mixed) == "store"
    assert _recruit_store_action(mixed) == "play"

    appstore_mixed = {
        **mixed,
        "recruit": {**mixed["recruit"], "managed_by": "appstore"},
    }
    assert _milestone_billing(appstore_mixed) == "store"
    assert _recruit_store_action(appstore_mixed) == "account"

    copy = (WEB / "lib" / "recruitMilestone.ts").read_text()
    screen = (WEB / "ui" / "RecruitMilestone.tsx").read_text()
    app = (WEB / "App.tsx").read_text()
    recruit = (WEB / "ui" / "Recruit.tsx").read_text()
    assert "recruitStoreAction" in copy
    assert "account?.recruit?.managed_by" in copy
    assert "api.billing.portal" not in copy
    assert "onClick={openRecruitStore}" in screen
    assert "onManageBilling" not in screen
    assert "onManageBilling" not in recruit
    assert "onManageBilling={() => void manageBilling()}" not in _recruit_jsx(app)
    assert "onClick={() => void openStripePortal()}" in screen
    assert "onClick={openRecruitStore}" in screen
    assert "manageBilling" not in screen
    assert "api.billing.portal" not in screen.split("function openRecruitStore")[1].split(
        "async function openStripePortal"
    )[0]


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
    """answered_count / bank_size come from the live bank plus completed attempt rows."""
    storage = (
        Path(__file__).resolve().parents[1] / "app" / "storage" / "recruit.py"
    ).read_text()
    assert "def attempted_scenario_ids" in storage
    assert "def completed_scenario_ids" in storage
    assert '.eq("status", "completed")' in storage
    bank = (Path(__file__).resolve().parents[1] / "app" / "recruit" / "bank.py").read_text()
    assert "answered_count=len(completed & bank_ids)" in bank
