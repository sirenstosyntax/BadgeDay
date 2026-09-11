"""BD-R-003: five-question board, held notes, C1, board-unit entitlements.

No network. The HTTP handler never critiques. Draw, gate, and board-end
copy are pinned here so a later edit cannot quietly return a C2-only board
or release notes mid-session.
"""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import CurrentUser, current_user, get_settings, user_db
from app.api.recruit import router
from app.config import Settings
from app.critique.models import Critique, Point
from app.critique.render import board_answer_lines, board_end_leaks, c1_candidate_lines
from app.recruit.bank import (
    BankItem,
    DrawnBoard,
    DrawnSlot,
    ExhaustedIssue,
    draw_board,
    draw_is_c2_only,
    published_items,
)
from app.recruit.copy import (
    BOARD_FRAMING,
    C1_COSTS,
    C1_HELD,
    C1_INSUFFICIENT,
    C1_LEAD,
    C1_NOT_ANSWERED,
    C1_OUTSIDE,
    C1_OUTSIDE_BODY,
    NOTES_BLOCKED,
    PER_ANSWER_NOT_ANSWERED,
    PER_ANSWER_NOT_ASSESSABLE,
    SOFT_TIMER_SECONDS,
)
from app.recruit.families import DRAW_SLOTS
from app.storage.boards import RecruitBoardRecord
from app.storage.recruit import RecruitAttemptRecord
from tests.test_recruit_loop import USER_ID

WEB = Path(__file__).resolve().parents[1] / "web" / "src"
Q1 = "Why do you want to be a firefighter?"
Q2 = "Tell us about a crew you were on."
Q3 = "Tell us about a time you saw something that was not right."
Q4 = "What is the least appealing part of this job to you?"
Q5 = "Walk us through how you would handle the first five minutes."
BOARD = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _settings(**overrides) -> Settings:
    values = {
        "deepgram_api_key": "dg-test",
        "anthropic_api_key": "sk-test",
        "generation_model": "claude-sonnet-5",
        "generation_effort": "high",
        "recruit_free_sessions": 1,
        "recruit_daily_attempt_limit": 2,
    }
    values.update(overrides)
    return Settings(**values)


def _slots() -> tuple[DrawnSlot, ...]:
    return (
        DrawnSlot("MOT-1.1", Q1, "MOT-1", "c2", "A"),
        DrawnSlot("TEA-1.1", Q2, "TEA-1", "c3", "BC"),
        DrawnSlot("INT-1.1", Q3, "INT-1", "c4", "DEF"),
        DrawnSlot("JOB-1.1", Q4, "JOB-1", "c2", "GH"),
        DrawnSlot("OPN-1.1", Q5, "OPN-1", "c1", "J"),
    )


def _drawn() -> DrawnBoard:
    return DrawnBoard(slots=_slots())


def _board(**overrides) -> RecruitBoardRecord:
    first = _slots()[0]
    values = {
        "id": BOARD,
        "user_id": USER_ID,
        "started_at": datetime(2026, 9, 11, 18, 0, tzinfo=UTC),
        "status": "in_progress",
        "current_index": 0,
        "current_question_text": first.question_text,
        "current_scenario_id": first.scenario_id,
        "current_criterion_id": first.criterion_id,
        "current_family": first.family,
        "issued_families": [slot.family for slot in _slots()],
        "issued_scenario_ids": [slot.scenario_id for slot in _slots()],
        "notes_released": False,
        "c1_candidate_lines": [],
    }
    values.update(overrides)
    return RecruitBoardRecord(**values)


def _attempt(**overrides) -> RecruitAttemptRecord:
    values = {
        "id": str(uuid4()),
        "user_id": USER_ID,
        "scenario_id": "MOT-1.1",
        "question_text": Q1,
        "started_at": datetime(2026, 9, 11, 18, 0, tzinfo=UTC),
        "status": "completed",
        "board_id": BOARD,
        "slot_index": 0,
        "candidate_lines": [],
    }
    values.update(overrides)
    return RecruitAttemptRecord(**values)


def _client(
    monkeypatch,
    *,
    today_count: int = 0,
    delivered_count: int = 0,
    entitled: bool = False,
    open_board: RecruitBoardRecord | None = None,
    get_board_record: RecruitBoardRecord | None = None,
    attempts: list[RecruitAttemptRecord] | None = None,
    draw=None,
    notes_blocked: bool = False,
    abandon=None,
    get_board_fn=None,
) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[current_user] = lambda: CurrentUser(
        id=USER_ID, email="c@example.com", access_token="t"
    )
    app.dependency_overrides[get_settings] = lambda: _settings()
    app.dependency_overrides[user_db] = lambda: object()

    held: dict[str, RecruitBoardRecord | None] = {"open": open_board}

    def fake_start(db, user_id, drawn, started_at):
        first = drawn.slots[0]
        board = _board(
            user_id=user_id,
            started_at=started_at,
            current_question_text=first.question_text,
            current_scenario_id=first.scenario_id,
            current_criterion_id=first.criterion_id,
            current_family=first.family,
            issued_families=[slot.family for slot in drawn.slots],
            issued_scenario_ids=[slot.scenario_id for slot in drawn.slots],
        )
        held["open"] = board
        return board

    monkeypatch.setattr("app.api.recruit.attempted_scenario_ids", lambda db: [])
    monkeypatch.setattr("app.api.recruit.completed_scenario_ids", lambda db: [])
    monkeypatch.setattr("app.api.recruit.issued_scenario_ids", lambda db: [])
    monkeypatch.setattr("app.api.recruit.recent_board_families", lambda db, limit=8: [])
    monkeypatch.setattr(
        "app.api.recruit.count_boards_started",
        lambda db, started_on_or_after=None: today_count,
    )
    monkeypatch.setattr(
        "app.api.recruit.count_completed_boards",
        lambda db, started_on_or_after=None: delivered_count,
    )
    monkeypatch.setattr("app.api.recruit.get_open_board", lambda db: held["open"])
    monkeypatch.setattr(
        "app.api.recruit.get_board",
        get_board_fn
        if get_board_fn is not None
        else (lambda db, _id: get_board_record or held["open"] or _board(id=_id)),
    )
    monkeypatch.setattr("app.api.recruit.start_board", fake_start)
    monkeypatch.setattr("app.recruit.gate.recruit_entitled", lambda *a: entitled)
    monkeypatch.setattr(
        "app.api.recruit.draw_board",
        draw if draw is not None else (lambda *a, **k: _drawn()),
    )
    monkeypatch.setattr(
        "app.storage.boards.board_attempts",
        lambda db, board_id: list(attempts or []),
    )
    monkeypatch.setattr(
        "app.api.recruit.abandon_board",
        abandon if abandon is not None else (lambda db, board_id: None),
    )
    monkeypatch.setattr(
        "app.api.recruit.notes_blocked_for_board",
        lambda db, board: notes_blocked,
    )
    return TestClient(app)


def test_start_returns_only_question_one(monkeypatch) -> None:
    response = _client(monkeypatch).post("/recruit/boards")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["question_index"] == 1
    assert body["board_size"] == 5
    assert body["question_text"] == Q1
    assert body["scenario_id"] == "MOT-1.1"
    assert body["answers"] == []
    assert body["c1_lines"] == []
    assert body["framing"] is None
    joined = response.text
    assert Q2 not in joined
    assert Q3 not in joined
    assert Q4 not in joined
    assert Q5 not in joined


def test_in_progress_poll_holds_notes(monkeypatch) -> None:
    board = _board()
    attempt = _attempt(
        status="completed",
        candidate_lines=["WHAT YOU DID WELL", "You named one thing."],
    )
    monkeypatch.setattr("app.api.recruit.get_attempt", lambda db, _id: attempt)
    response = _client(monkeypatch, open_board=board).get(f"/recruit/attempts/{attempt.id}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["lines"] == []
    assert "score" not in body

    view = _client(monkeypatch, open_board=board, attempts=[attempt]).get(
        f"/recruit/boards/{BOARD}"
    )
    assert view.status_code == 200
    payload = view.json()
    assert payload["answers"] == []
    assert payload["c1_lines"] == []
    assert payload["framing"] is None
    assert payload["question_text"] == Q1


def test_complete_releases_five_notes_and_c1(monkeypatch) -> None:
    notes = [
        _attempt(
            slot_index=i,
            scenario_id=slot.scenario_id,
            question_text=slot.question_text,
            candidate_lines=[f"Note for question {i + 1}."],
        )
        for i, slot in enumerate(_slots())
    ]
    board = _board(
        status="completed",
        notes_released=True,
        current_index=4,
        current_question_text=Q5,
        current_scenario_id="OPN-1.1",
        c1_candidate_lines=[C1_LEAD, "", C1_HELD, "You finished each answer."],
    )
    response = _client(monkeypatch, get_board_record=board, attempts=notes).get(
        f"/recruit/boards/{BOARD}"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["framing"] == BOARD_FRAMING
    assert [item["question_index"] for item in body["answers"]] == [1, 2, 3, 4, 5]
    assert [item["question_text"] for item in body["answers"]] == [Q1, Q2, Q3, Q4, Q5]
    assert [item["lines"] for item in body["answers"]] == [
        [f"Note for question {i}."] for i in range(1, 6)
    ]
    assert body["c1_lines"][0] == C1_LEAD
    assert C1_HELD in body["c1_lines"]
    assert body["question_text"] is None


def test_abandon_returns_no_lines_and_no_c1(monkeypatch) -> None:
    board = _board(status="in_progress")
    leaked = [
        _attempt(candidate_lines=["WHAT YOU DID WELL"], slot_index=0),
    ]
    response = _client(monkeypatch, open_board=board, attempts=leaked).post(
        f"/recruit/boards/{BOARD}/abandon"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "abandoned"
    assert body["answers"] == []
    assert body["c1_lines"] == []
    assert body["framing"] is None
    assert body["question_text"] is None


def test_live_draw_is_not_c2_only() -> None:
    board = draw_board([])
    assert isinstance(board, DrawnBoard)
    assert [slot.draw_group for slot in board.slots] == ["A", "BC", "DEF", "GH", "J"]
    assert draw_is_c2_only(board) is False
    assert {slot.criterion_id for slot in board.slots} != {"c2"}


def test_c2_only_draw_is_a_500(monkeypatch) -> None:
    def fake_draw(*_a, **_k):
        return DrawnBoard(
            slots=tuple(
                DrawnSlot(f"MOT-1.{i}", f"C2 only {i}", "MOT-1", "c2", group)
                for i, group in enumerate(("A", "BC", "DEF", "GH", "J"), start=1)
            )
        )

    response = _client(monkeypatch, draw=fake_draw).post("/recruit/boards")
    assert response.status_code == 500
    assert "C2-only" in response.json()["detail"]


def test_free_complete_board_paywalls_the_next_start(monkeypatch) -> None:
    response = _client(monkeypatch, delivered_count=1, today_count=1).post(
        "/recruit/boards"
    )
    assert response.status_code == 402
    assert "free oral-board session is used" in response.json()["detail"]


def _completed_board_with_notes() -> tuple[RecruitBoardRecord, list[RecruitAttemptRecord]]:
    notes = [
        _attempt(
            slot_index=i,
            scenario_id=slot.scenario_id,
            question_text=slot.question_text,
            candidate_lines=[f"Note for question {i + 1}."],
        )
        for i, slot in enumerate(_slots())
    ]
    board = _board(
        status="completed",
        notes_released=True,
        current_index=4,
        current_question_text=Q5,
        current_scenario_id="OPN-1.1",
        c1_candidate_lines=[C1_LEAD, "", C1_HELD, "You finished each answer."],
    )
    return board, notes


def test_abandon_of_completed_board_returns_the_summary(monkeypatch) -> None:
    """Leave during holding must not rewrite a just-completed board to abandoned."""
    board, notes = _completed_board_with_notes()
    abandoned: list[str] = []
    response = _client(
        monkeypatch,
        get_board_record=board,
        attempts=notes,
        abandon=lambda db, board_id: abandoned.append(board_id),
    ).post(f"/recruit/boards/{BOARD}/abandon")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["framing"] == BOARD_FRAMING
    assert [item["question_index"] for item in body["answers"]] == [1, 2, 3, 4, 5]
    assert body["c1_lines"][0] == C1_LEAD
    assert abandoned == []


def test_abandon_race_returns_just_completed_summary(monkeypatch) -> None:
    """RPC refuses a completed board; return the summary instead of empty notes."""
    completed, notes = _completed_board_with_notes()
    scoring = _board(status="scoring", current_index=4, current_question_text=Q5)
    state = {"board": scoring}

    def fake_get(_db, _id):
        return state["board"]

    def fake_abandon(_db, _id):
        state["board"] = completed
        raise RuntimeError("board cannot be abandoned")

    response = _client(
        monkeypatch,
        attempts=notes,
        get_board_fn=fake_get,
        abandon=fake_abandon,
    ).post(f"/recruit/boards/{BOARD}/abandon")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["framing"] == BOARD_FRAMING
    assert body["answers"]
    assert body["c1_lines"][0] == C1_LEAD


def test_abandon_does_not_consume_the_free_board(monkeypatch) -> None:
    """lifetime_count is completed boards with released notes. Abandoned is 0."""
    response = _client(monkeypatch, today_count=1, delivered_count=0).post(
        "/recruit/boards"
    )
    assert response.status_code == 201
    assert response.json()["question_text"] == Q1


def test_third_board_start_the_same_utc_day_is_429(monkeypatch) -> None:
    response = _client(monkeypatch, today_count=2, entitled=True).post("/recruit/boards")
    assert response.status_code == 429
    assert "today's limit of 2" in response.json()["detail"]
    assert "boards" in response.json()["detail"]


def test_promote_entitlement_alone_cannot_start_a_board() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "app" / "api" / "recruit.py"
    ).read_text()
    gate = (Path(__file__).resolve().parents[1] / "app" / "recruit" / "gate.py").read_text()
    assert "has_access" not in source
    assert "has_recruit_access" in gate
    assert "has_access" not in gate.split("def evaluate_recruit_gate")[1].split("def ")[0]


def test_promote_subscriber_is_402_after_the_free_board(monkeypatch) -> None:
    """A Promote row is not Recruit entitlement. The second board is still 402."""
    response = _client(monkeypatch, delivered_count=1, entitled=False).post(
        "/recruit/boards"
    )
    assert response.status_code == 402


def test_legacy_question_wraps_the_board_and_does_not_preview(monkeypatch) -> None:
    response = _client(monkeypatch).get("/recruit/question")
    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "available"
    assert body["question_text"] == Q1
    assert body["question_index"] == 1
    assert body["board_size"] == 5
    assert body["soft_timer_seconds"] == 120
    assert Q2 not in response.text


def test_web_followup_helpers_are_wired() -> None:
    recruit = (WEB / "ui" / "Recruit.tsx").read_text()
    helper = (WEB / "lib" / "recruitBoard.ts").read_text()
    assert "boardPromptHeading" in recruit
    assert "leaveAfterAbandon" in recruit
    assert "shouldShowNotesBlockedPath" in recruit
    assert "NOTES_BLOCKED_COPY" in recruit
    assert NOTES_BLOCKED in helper
    assert "question || 'Loading…'" not in recruit


def test_soft_timer_is_display_only() -> None:
    assert SOFT_TIMER_SECONDS == 120
    recruit = (WEB / "ui" / "Recruit.tsx").read_text()
    helper = (WEB / "lib" / "recruitBoard.ts").read_text()
    assert "SOFT_TIMER_SECONDS" in recruit
    assert "It will not submit" in recruit
    assert "never auto-submit" in helper
    # Hitting 0:00 must not call submit. The timer effect only updates remaining.
    timer_effect = recruit.split("Soft timer. Display only")[1].split("function stopTracks")[0]
    assert "submit(" not in timer_effect
    assert "setRemaining" in timer_effect


def test_signed_board_end_copy_is_character_for_character() -> None:
    assert BOARD_FRAMING == (
        "Board complete. Notes held until the end on purpose — same as a real board."
    )
    assert PER_ANSWER_NOT_ASSESSABLE == (
        "From what you said, this has not come up yet — so there is nothing here to "
        "judge you on, and this is not a mark against you."
    )
    assert PER_ANSWER_NOT_ANSWERED == (
        "There was not enough in that answer to say anything useful about it yet."
    )
    assert C1_LEAD == (
        "Across these five answers — how they were built. Not a score on any one of them."
    )
    assert C1_HELD == "WHAT HELD ACROSS THE BOARD"
    assert C1_COSTS == "WHAT STILL COSTS YOU UNDER PRESSURE"
    assert C1_OUTSIDE == "OUTSIDE WHAT THIS TOOL CAN HEAR"
    assert C1_OUTSIDE_BODY == (
        "Presence, eye contact, and how you sit in the room are outside what this "
        "tool can hear. Work those with a mentor mock board, a station visit, or a "
        "ride-along — routes, not a booked provider."
    )
    assert C1_NOT_ANSWERED == (
        "There was not enough across these five answers to say anything useful "
        "about how they were built yet."
    )
    assert C1_INSUFFICIENT == (
        "From what you said across this board, there is not enough to judge how "
        "the answers were built — and that is not a mark against you."
    )


def test_c1_render_uses_signed_headings_and_omits_outside_without_presence() -> None:
    critique = Critique(
        criterion_id="c1",
        criterion_name="Answer Construction",
        outcome="scored",
        determination="internal only",
        internal_score=3,
        route="n/a",
        points=[
            Point(
                kind="rubric",
                improvement="none",
                observation="You finished each answer before the next one started.",
            ),
            Point(
                kind="rubric",
                improvement="answer",
                observation="Under pressure the ending still trails off.",
                ask="Where do you want that answer to stop?",
            ),
        ],
    )
    lines = c1_candidate_lines(critique)
    assert lines[0] == C1_LEAD
    assert C1_HELD in lines
    assert C1_COSTS in lines
    assert C1_OUTSIDE not in lines
    assert "3" not in " ".join(lines)
    assert "determination" not in " ".join(lines).lower()
    assert board_end_leaks(lines) == ()


def test_c1_outside_heading_only_when_presence_is_routed() -> None:
    critique = Critique(
        criterion_id="c1",
        criterion_name="Answer Construction",
        outcome="scored",
        internal_score=3,
        route="n/a",
        points=[
            Point(
                kind="rubric",
                improvement="risk",
                observation="Presence and eye contact still sit outside this recording.",
                ask="Work those with a mentor mock board.",
            )
        ],
    )
    lines = c1_candidate_lines(critique)
    assert C1_OUTSIDE in lines
    assert C1_OUTSIDE_BODY in lines


def test_per_answer_notes_use_signed_ac7_and_ac8() -> None:
    absent = Critique(
        criterion_id="c2",
        criterion_name="Motivation",
        outcome="not_assessable",
        internal_score=0,
        route="n/a",
        points=[],
    )
    silent = Critique(
        criterion_id="c2",
        criterion_name="Motivation",
        outcome="not_answered",
        internal_score=0,
        route="n/a",
        points=[],
    )
    assert board_answer_lines(absent)[0] == PER_ANSWER_NOT_ASSESSABLE
    assert board_answer_lines(silent)[0] == PER_ANSWER_NOT_ANSWERED
    # The older C2 wording must not ship on a board-end note.
    assert "working life" not in board_answer_lines(absent)[0]


def test_c1_empty_outcomes_are_the_signed_lines() -> None:
    silent = Critique(
        criterion_id="c1",
        criterion_name="C1",
        outcome="not_answered",
        internal_score=0,
        route="n/a",
        points=[],
    )
    absent = Critique(
        criterion_id="c1",
        criterion_name="C1",
        outcome="not_assessable",
        internal_score=0,
        route="n/a",
        points=[],
    )
    assert c1_candidate_lines(silent) == [C1_NOT_ANSWERED]
    assert c1_candidate_lines(absent) == [C1_INSUFFICIENT]


def test_board_end_leak_ban() -> None:
    assert board_end_leaks(["Delivery Clear"])
    assert board_end_leaks(["internal_score 4"])
    assert board_end_leaks(["Answer Construction"])
    assert board_end_leaks(["determination: he landed on the 3"])
    assert board_end_leaks([C1_LEAD, C1_HELD, C1_OUTSIDE_BODY]) == ()
    # AC19: bare candidate-facing 1–5 grades, not only Delivery labels.
    assert board_end_leaks(["You scored a 4"])
    assert board_end_leaks(["grade: 2"])
    assert board_end_leaks(["3 out of 5"])
    assert board_end_leaks(["rated 5"])
    assert board_end_leaks(["a 1"])
    assert board_end_leaks(["4"])
    assert board_end_leaks(["1-5 scale"])
    assert board_end_leaks([C1_LEAD, "You finished each answer."]) == ()


def test_draw_never_repeats_and_avoids_recent_families() -> None:
    seen = ["MOT-1.1", "TEA-1.1", "INT-1.1", "JOB-1.1", "OPN-1.1"]
    recent = ["MOT-1", "TEA-1", "INT-1", "JOB-1", "OPN-1"]
    board = draw_board(seen, recent_families=recent)
    assert isinstance(board, DrawnBoard)
    ids = {slot.scenario_id for slot in board.slots}
    assert ids.isdisjoint(seen)
    families = {slot.family for slot in board.slots}
    assert families.isdisjoint(recent)


def test_draw_relaxes_family_window_rather_than_going_c2_only() -> None:
    items = published_items()
    by_letter: dict[str, list[BankItem]] = {name: [] for name, _ in DRAW_SLOTS}
    from app.recruit.families import letter_for_family

    for item in items:
        letter = letter_for_family(item.family)
        for name, letters in DRAW_SLOTS:
            if letter in letters:
                by_letter[name].append(item)
    # Leave one unseen item in each slot, all from the same recent families.
    remaining = [pool[0] for pool in by_letter.values()]
    seen = [item.scenario_id for item in items if item not in remaining]
    recent = [item.family for item in remaining]
    board = draw_board(seen, recent_families=recent, bank=items)
    assert isinstance(board, DrawnBoard)
    assert {slot.scenario_id for slot in board.slots} == {
        item.scenario_id for item in remaining
    }


def test_draw_exhausts_when_a_slot_is_empty() -> None:
    items = tuple(
        item for item in published_items() if item.family.split("-", 1)[0] != "OPN"
    )
    decision = draw_board([], bank=items)
    assert isinstance(decision, ExhaustedIssue)
    assert decision.bank_size == len(items)


def test_notes_cannot_finish_when_a_slot_has_no_transcript() -> None:
    from app.storage.boards import notes_cannot_finish

    rows = [
        {"status": "completed", "transcript": f"answer {index}", "slot_index": index}
        for index in range(4)
    ] + [{"status": "critique_failed", "transcript": "", "slot_index": 4}]
    assert notes_cannot_finish("scoring", rows) is True
    assert notes_cannot_finish("in_progress", rows) is True
    assert notes_cannot_finish("completed", rows) is False
    rows[-1]["transcript"] = "enough spoken material to hear"
    rows[-1]["status"] = "completed"
    assert notes_cannot_finish("scoring", rows) is False


def test_scoring_board_without_transcript_signals_notes_blocked(monkeypatch) -> None:
    board = _board(status="scoring", current_index=4, current_question_text=Q5)
    response = _client(
        monkeypatch, get_board_record=board, notes_blocked=True
    ).get(f"/recruit/boards/{BOARD}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "scoring"
    assert body["notes_blocked"] is True
    assert body["notes_blocked_detail"] == NOTES_BLOCKED
    assert body["answers"] == []
    assert body["c1_lines"] == []
    assert body["framing"] is None


def test_c1_is_blocked_until_five_transcripts_exist(monkeypatch) -> None:
    """BD-R-003 §6 / §8.4: no fake C1 when a slot has no spoken material."""
    from app.worker.pipeline import _maybe_enqueue_c1

    queued: list[str] = []
    rows = [
        {"status": "completed", "transcript": f"answer {index}", "slot_index": index}
        for index in range(4)
    ] + [{"status": "critique_failed", "transcript": "", "slot_index": 4}]

    class _Jobs:
        def select(self, *_a):
            return self

        def eq(self, *_a):
            return self

        def limit(self, *_a):
            return self

        def execute(self):
            return SimpleNamespace(data=[])

    class _Db:
        def table(self, name: str) -> _Jobs:
            assert name == "jobs"
            return _Jobs()

    monkeypatch.setattr("app.storage.boards.worker_board_attempts", lambda db, _id: rows)
    monkeypatch.setattr("app.storage.boards.enqueue_c1", lambda db, _id: queued.append(_id))
    _maybe_enqueue_c1(_Db(), BOARD)
    assert queued == []
    rows[-1]["transcript"] = "enough spoken material to hear"
    _maybe_enqueue_c1(_Db(), BOARD)
    assert queued == [BOARD]


def test_c1_worker_skips_an_abandoned_board(monkeypatch) -> None:
    from app.worker.jobs import Job
    from app.worker.pipeline import run_recruit_c1

    called: list[str] = []
    monkeypatch.setattr(
        "app.storage.boards.get_board_for_worker",
        lambda db, _id: _board(status="abandoned"),
    )
    monkeypatch.setattr(
        "app.critique.critiquer.critique_answer",
        lambda **k: called.append("critique") or SimpleNamespace(critique=None),
    )
    job = Job(
        id="job-c1",
        kind="recruit_c1",
        board_id=BOARD,
        status="running",
        attempts=1,
        max_attempts=3,
    )
    run_recruit_c1(object(), _settings(), job)
    assert called == []


def test_pricing_ids_stay_blank() -> None:
    settings = Settings()
    assert settings.stripe_price_id_recruit_monthly == ""
    assert settings.play_product_id_recruit_monthly == ""
    assert settings.appstore_product_id_recruit_monthly == ""


def test_migration_0014_is_board_units_not_checkout() -> None:
    sql = (
        Path(__file__).resolve().parents[1]
        / "supabase"
        / "migrations"
        / "0014_recruit_boards.sql"
    ).read_text()
    assert "create table public.recruit_boards" in sql
    assert "held_candidate_lines" in sql
    assert "complete_recruit_board" in sql
    assert "abandon_recruit_board" in sql
    assert "recruit_c1" in sql
    assert "price_id" not in sql.lower()
    assert "checkout" in sql.lower()
    assert "does not" in sql.lower() and "enable checkout" in sql.lower()


def test_migration_0015_is_store_purchases_module_not_boards() -> None:
    """0014 is recruit_boards. The store_purchases.module filter is 0015."""
    migrations = Path(__file__).resolve().parents[1] / "supabase" / "migrations"
    assert not (migrations / "0014_store_purchases_module.sql").exists()
    sql = (migrations / "0015_store_purchases_module.sql").read_text()
    assert "add column module" in sql
    assert "sp.module = 'promote'" in sql
    assert "0014 is recruit_boards" in sql
