"""The published Recruit bank, and how a five-question board is drawn.

Never-repeat a prompt. No family inside a rolling 8 boards. 70/30 is a
seam: until behavior tracking exists the weighted half is uniform random
among remaining items in the slot, same as the random half.

`issue` stays for single-item callers (legacy wrap, tests). Boards use
`draw_board`. Empty bank and a slot that cannot be filled are exhausted.
`next_eligible_at` stays None until a retirement policy is live.

Legacy attempts stored ``scenario_id="c2"`` used the old combined prompt.
That id is frozen — it is not re-issued — and it aliases any published item
that carries the same words, so novelty stays honest.
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from app.critique.cli import QUESTIONS
from app.recruit.bank_data import PUBLISHED_ITEMS
from app.recruit.families import DRAW_SLOTS, letter_for_family

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


@dataclass(frozen=True)
class DrawnSlot:
    scenario_id: str
    question_text: str
    family: str
    criterion_id: str
    draw_group: str


@dataclass(frozen=True)
class DrawnBoard:
    slots: tuple[DrawnSlot, ...]


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
    bank ids only. Selection is first unseen (never-repeat). Board draws
    use `draw_board` instead.
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


def _items_in_letters(
    items: Sequence[BankItem],
    letters: frozenset[str],
) -> list[BankItem]:
    out: list[BankItem] = []
    for item in items:
        if not item.family:
            continue
        if letter_for_family(item.family) in letters:
            out.append(item)
    return out


def _pick(
    candidates: Sequence[BankItem],
    *,
    rng: random.Random,
    weights: Mapping[str, float] | None,
) -> BankItem:
    """70/30 seam. Without behavior weights both halves are uniform random."""
    if not candidates:
        raise ValueError("no candidates to pick")
    if rng.random() < 0.3 or not weights:
        return rng.choice(list(candidates))
    scored: list[tuple[float, BankItem]] = []
    for item in candidates:
        scored.append((float(weights.get(item.family, 1.0)), item))
    total = sum(weight for weight, _ in scored)
    if total <= 0:
        return rng.choice(list(candidates))
    cursor = rng.random() * total
    running = 0.0
    for weight, item in scored:
        running += weight
        if cursor <= running:
            return item
    return scored[-1][1]


def draw_board(
    seen_scenario_ids: Sequence[str],
    *,
    recent_families: Sequence[str] = (),
    completed_scenario_ids: Sequence[str] = (),
    bank: Sequence[BankItem] | None = None,
    rng: random.Random | None = None,
    weights: Mapping[str, float] | None = None,
) -> DrawnBoard | ExhaustedIssue:
    """One item from each of A, B/C, D/E/F, G/H, J.

    `recent_families` is families issued on the last eight boards (started,
    including abandoned). A family in that window is skipped unless the
    slot would otherwise be empty — then the window is relaxed for that
    slot only. Never-repeat is never relaxed.

    Five C2-only slots cannot come out of this function while the published
    bank still has non-C2 groups.
    """
    items = tuple(bank) if bank is not None else published_items()
    seen = expand_seen_ids(seen_scenario_ids, items)
    completed = expand_seen_ids(completed_scenario_ids, items)
    bank_ids = {item.scenario_id for item in items}
    blocked_families = {family for family in recent_families if family}
    picker = rng or random.Random()
    chosen_ids: set[str] = set()
    slots: list[DrawnSlot] = []

    for group_name, letters in DRAW_SLOTS:
        pool = [
            item
            for item in _items_in_letters(items, letters)
            if item.scenario_id not in seen and item.scenario_id not in chosen_ids
        ]
        if not pool:
            return ExhaustedIssue(
                answered_count=len(completed & bank_ids) if bank_ids else 0,
                bank_size=len(items),
                next_eligible_at=None,
            )
        preferred = [item for item in pool if item.family not in blocked_families]
        usable = preferred or pool
        picked = _pick(usable, rng=picker, weights=weights)
        chosen_ids.add(picked.scenario_id)
        blocked_families.add(picked.family)
        slots.append(
            DrawnSlot(
                scenario_id=picked.scenario_id,
                question_text=picked.question_text,
                family=picked.family,
                criterion_id=picked.criterion_id,
                draw_group=group_name,
            )
        )

    return DrawnBoard(slots=tuple(slots))


def draw_is_c2_only(board: DrawnBoard) -> bool:
    return all(slot.criterion_id == C2_CRITERION_ID for slot in board.slots)
