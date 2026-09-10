"""The published Recruit bank, and whether a candidate still has a novel item.

The live set is the C2-only issuable subset: non-STRIKE MOT / JOB / CMT
variants from the reviewed draft. C1 / C3 / C4 / C5 stay unpublished until
the scorer wire. Rotation, family-within-8, 70/30 weighting, and retirement
are later work; this module is the seam those land behind.

`issue` is pure: callers pass the scenario ids already on the candidate's
attempt rows. Empty bank and fully-seen bank are the same exhausted state.
`next_eligible_at` stays None until a retirement/rotation policy is live.

Legacy attempts stored ``scenario_id="c2"`` used the old combined prompt.
That id is frozen — it is not re-issued — and it aliases any published item
that carries the same words, so novelty stays honest.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.critique.cli import QUESTIONS
from app.recruit.bank_data import PUBLISHED_ITEMS

C2_SCENARIO_ID = "c2"
C2_CRITERION_ID = "c2"
LEGACY_C2_QUESTION = QUESTIONS[C2_SCENARIO_ID]


@dataclass(frozen=True)
class BankItem:
    scenario_id: str
    question_text: str
    family: str = ""
    criterion_id: str = C2_CRITERION_ID


@dataclass(frozen=True)
class AvailableIssue:
    scenario_id: str
    question_text: str
    criterion_id: str = C2_CRITERION_ID
    family: str = ""


@dataclass(frozen=True)
class ExhaustedIssue:
    answered_count: int
    bank_size: int
    next_eligible_at: datetime | None = None


Issue = AvailableIssue | ExhaustedIssue


def published_items() -> tuple[BankItem, ...]:
    """Currently issuable prompts. Tests replace this to force an empty bank."""
    return tuple(
        BankItem(
            scenario_id=raw["scenario_id"],
            question_text=raw["question_text"],
            family=raw["family"],
            criterion_id=raw["criterion_id"],
        )
        for raw in PUBLISHED_ITEMS
        if raw["criterion_id"] == C2_CRITERION_ID
    )


def item_by_id(
    scenario_id: str, bank: Sequence[BankItem] | None = None
) -> BankItem | None:
    items = tuple(bank) if bank is not None else published_items()
    for item in items:
        if item.scenario_id == scenario_id:
            return item
    return None


def criterion_id_for(scenario_id: str, bank: Sequence[BankItem] | None = None) -> str:
    """Rubric id for an issued (or legacy) prompt. Never the item id itself."""
    item = item_by_id(scenario_id, bank)
    if item is not None:
        return item.criterion_id
    if scenario_id == C2_SCENARIO_ID:
        return C2_CRITERION_ID
    return C2_CRITERION_ID


def question_for(scenario_id: str, bank: Sequence[BankItem] | None = None) -> str:
    item = item_by_id(scenario_id, bank)
    if item is not None:
        return item.question_text
    if scenario_id == C2_SCENARIO_ID:
        return LEGACY_C2_QUESTION
    raise KeyError(f"unknown bank item {scenario_id!r}")


def expand_seen_ids(
    seen_scenario_ids: Sequence[str],
    bank: Sequence[BankItem],
) -> set[str]:
    """Treat legacy ``c2`` as the same prompt as any item with those words."""
    expanded = {sid for sid in seen_scenario_ids if sid}
    if C2_SCENARIO_ID in expanded:
        for item in bank:
            if item.question_text == LEGACY_C2_QUESTION:
                expanded.add(item.scenario_id)
    for item in bank:
        if item.question_text == LEGACY_C2_QUESTION and item.scenario_id in expanded:
            expanded.add(C2_SCENARIO_ID)
    return expanded


def issue(
    seen_scenario_ids: Sequence[str],
    bank: Sequence[BankItem] | None = None,
    *,
    completed_scenario_ids: Sequence[str] = (),
) -> Issue:
    """Pick the first unseen bank item, or the exhausted milestone payload.

    Novelty uses every issued id. `answered_count` is distinct *completed*
    bank ids only — not queued, running, failed, or abandoned. It is not a
    hardcoded 290, and it is not an "about" figure. Selection is first
    unseen (never-repeat). 70/30 weighting is not live.
    """
    items = tuple(bank) if bank is not None else published_items()
    seen = expand_seen_ids(seen_scenario_ids, items)
    completed = expand_seen_ids(completed_scenario_ids, items)
    bank_ids = {item.scenario_id for item in items}
    remaining = [item for item in items if item.scenario_id not in seen]
    if not remaining:
        return ExhaustedIssue(
            answered_count=len(completed & bank_ids) if bank_ids else 0,
            bank_size=len(items),
            next_eligible_at=None,
        )
    chosen = remaining[0]
    return AvailableIssue(
        scenario_id=chosen.scenario_id,
        question_text=chosen.question_text,
        criterion_id=chosen.criterion_id,
        family=chosen.family,
    )
