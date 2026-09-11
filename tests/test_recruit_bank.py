"""C2-only bank publish: parse, count, novelty, legacy alias, FD-name lint."""

from pathlib import Path

from app.critique import rubric as rubric_module
from app.critique.cli import QUESTIONS
from app.recruit.bank import (
    C2_SCENARIO_ID,
    LEGACY_C2_QUESTION,
    AvailableIssue,
    BankItem,
    ExhaustedIssue,
    criterion_id_for,
    expand_seen_ids,
    issue,
    published_items,
)
from app.recruit.bank_data import PUBLISHED_ITEMS
from app.recruit.draft import (
    C2_GROUPS,
    DRAFT_PATH,
    fd_name_hits,
    issuable,
    parse_draft,
    parse_issuable,
    parse_issuable_c2,
)

SAMPLE = """
# MOT — Motivation

## MOT-1 — Why the fire service

**Listening for:** a decision with a traceable origin.
**Sources:** CJ, SLC, FH.

1. Why do you want to be a firefighter?
2. ~~Near-dupe of the first.~~ **`STRIKE`** (Grant, 2026-09-10, pass 2) — dupe.
3. What else did you seriously consider doing?

# TEA — Teamwork

## TEA-1 — Not in this slice

1. Tell us about a crew you were on.

# JOB — Understanding of the job

## JOB-1 — Least appealing

1. What's the least appealing part of this job to you?
2. ~~What part of this job are you least looking forward to?~~ **`STRIKE`** (Grant) — near-dupe.
"""


def _ids(items=None) -> list[str]:
    return [item.scenario_id for item in (items if items is not None else published_items())]


def test_parse_skips_strike_and_non_c2_families() -> None:
    rows = parse_draft(SAMPLE, groups=C2_GROUPS, criterion_id="c2")
    assert [item.scenario_id for item in rows] == [
        "MOT-1.1",
        "MOT-1.2",
        "MOT-1.3",
        "JOB-1.1",
        "JOB-1.2",
    ]
    struck = {item.scenario_id: item for item in rows if item.struck}
    assert set(struck) == {"MOT-1.2", "JOB-1.2"}
    assert struck["JOB-1.2"].question_text == (
        "What part of this job are you least looking forward to?"
    )
    kept = issuable(rows)
    assert _ids(kept) == ["MOT-1.1", "MOT-1.3", "JOB-1.1"]
    assert all(item.criterion_id == "c2" for item in kept)
    assert all(item.family.split("-", 1)[0] in C2_GROUPS for item in kept)
    assert "TEA-1.1" not in _ids(rows)


def test_draft_c2_surviving_count_is_81() -> None:
    rows = parse_draft(DRAFT_PATH.read_text(), groups=C2_GROUPS, criterion_id="c2")
    kept = issuable(rows)
    struck = [item for item in rows if item.struck]
    assert len(rows) == 88
    assert len(struck) == 7
    assert {item.scenario_id for item in struck} == {
        "JOB-1.2",
        "JOB-2.6",
        "JOB-3.1",
        "JOB-3.2",
        "JOB-3.8",
        "JOB-4.5",
        "CMT-2.6",
    }
    by_group = {}
    for item in kept:
        by_group[item.family.split("-", 1)[0]] = by_group.get(item.family.split("-", 1)[0], 0) + 1
    assert by_group == {"MOT": 40, "JOB": 26, "CMT": 15}
    assert len(kept) == 81


def test_published_items_are_the_reviewed_272() -> None:
    items = published_items()
    parsed = parse_issuable()
    assert len(items) == 272
    assert len(PUBLISHED_ITEMS) == 272
    assert _ids(items) == [item.scenario_id for item in parsed]
    assert items[0].scenario_id == "MOT-1.1"
    assert items[0].question_text == "Why do you want to be a firefighter?"
    assert C2_SCENARIO_ID not in _ids(items)
    assert {item.criterion_id for item in items} == {"c1", "c2", "c3", "c4", "c5"}
    assert all("." in item.scenario_id for item in items)
    c2_only = parse_issuable_c2()
    assert len(c2_only) == 81
    assert _ids(c2_only) == [
        item.scenario_id for item in items if item.family.split("-", 1)[0] in C2_GROUPS
    ]


def test_c2_issuable_subset_still_parses_to_81() -> None:
    parsed = parse_issuable_c2()
    assert len(parsed) == 81
    assert parsed[0].scenario_id == "MOT-1.1"
    assert parsed[-1].scenario_id == "CMT-2.8"
    assert all(item.criterion_id == "c2" for item in parsed)
    assert all(item.family.split("-", 1)[0] in C2_GROUPS for item in parsed)


def test_issue_first_unseen_never_repeats() -> None:
    items = published_items()
    first = issue([])
    assert isinstance(first, AvailableIssue)
    assert first.scenario_id == "MOT-1.1"
    assert first.criterion_id == "c2"
    second = issue(["MOT-1.1"])
    assert isinstance(second, AvailableIssue)
    assert second.scenario_id == "MOT-1.2"
    third = issue(["MOT-1.2", "MOT-1.1"])
    assert isinstance(third, AvailableIssue)
    assert third.scenario_id == items[2].scenario_id


def test_issue_exhausted_when_the_published_bank_was_seen() -> None:
    ids = _ids()
    decision = issue(ids, completed_scenario_ids=ids)
    assert isinstance(decision, ExhaustedIssue)
    assert decision.answered_count == 272
    assert decision.bank_size == 272
    assert decision.next_eligible_at is None


def test_legacy_c2_does_not_reissue_the_same_words() -> None:
    """Users who already have scenario_id=c2 keep novelty honest."""
    assert LEGACY_C2_QUESTION == QUESTIONS["c2"]
    live = issue(["c2"])
    assert isinstance(live, AvailableIssue)
    assert live.scenario_id != C2_SCENARIO_ID
    assert live.question_text != LEGACY_C2_QUESTION

    aliased = (
        BankItem(
            scenario_id="MOT-9.1",
            question_text=LEGACY_C2_QUESTION,
            family="MOT-9",
            criterion_id="c2",
        ),
        BankItem(
            scenario_id="MOT-9.2",
            question_text="A genuinely different prompt.",
            family="MOT-9",
            criterion_id="c2",
        ),
    )
    decision = issue(["c2"], bank=aliased)
    assert isinstance(decision, AvailableIssue)
    assert decision.scenario_id == "MOT-9.2"
    assert decision.question_text != LEGACY_C2_QUESTION
    assert "MOT-9.1" in expand_seen_ids(["c2"], aliased)


def test_criterion_id_for_decouples_item_from_rubric() -> None:
    assert criterion_id_for("MOT-1.3") == "c2"
    assert criterion_id_for("c2") == "c2"
    assert criterion_id_for("TEA-1.1") == "c3"
    assert criterion_id_for("INT-1.1") == "c4"
    assert criterion_id_for("OPN-1.1") == "c1"
    assert set(rubric_module.RUBRIC_FILES) == {"c1", "c2", "c3", "c4", "c5"}
    assert rubric_module.DRAFT_RUBRICS == frozenset()


def test_published_strings_name_no_real_department() -> None:
    for item in published_items():
        hits = fd_name_hits(item.question_text)
        assert hits == (), f"{item.scenario_id} names {hits}"
        assert "Listening for" not in item.question_text
        assert "Sources:" not in item.question_text
        text = item.question_text
        assert not text.startswith("~~")
        assert "`STRIKE`" not in text


def test_migration_persists_criterion_id_on_the_attempt() -> None:
    sql = (
        Path(__file__).resolve().parents[1]
        / "supabase"
        / "migrations"
        / "0013_recruit_attempt_criterion.sql"
    ).read_text()
    assert "add column criterion_id" in sql
    assert "p_criterion_id" in sql
    assert "drop function public.submit_queued_recruit_attempt" in sql
    storage = (Path(__file__).resolve().parents[1] / "app" / "storage" / "recruit.py").read_text()
    assert '"p_criterion_id": criterion_id' in storage
    assert "criterion_id: str | None" in storage
