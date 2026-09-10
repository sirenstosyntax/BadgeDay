"""The published Recruit bank, and whether a candidate still has a novel item.

The live set is the C2 prompt only. C3 exists in the CLI fixture set but is
unreviewed, so it is not issuable. Rotation and the ~290-item launch bank are
later work; this module is the seam those land behind.

`issue` is pure: callers pass the scenario ids already on the candidate's
attempt rows. Empty bank and fully-seen bank are the same exhausted state.
`next_eligible_at` stays None until a retirement/rotation policy is live.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.critique.cli import QUESTIONS

C2_SCENARIO_ID = "c2"


@dataclass(frozen=True)
class BankItem:
    scenario_id: str
    question_text: str


@dataclass(frozen=True)
class AvailableIssue:
    scenario_id: str
    question_text: str


@dataclass(frozen=True)
class ExhaustedIssue:
    answered_count: int
    bank_size: int
    next_eligible_at: datetime | None = None


Issue = AvailableIssue | ExhaustedIssue


def published_items() -> tuple[BankItem, ...]:
    """Currently issuable prompts. Tests replace this to force an empty bank."""
    return (
        BankItem(scenario_id=C2_SCENARIO_ID, question_text=QUESTIONS[C2_SCENARIO_ID]),
    )


def issue(
    seen_scenario_ids: Sequence[str],
    bank: Sequence[BankItem] | None = None,
    *,
    completed_scenario_ids: Sequence[str] = (),
) -> Issue:
    """Pick a novel bank item, or the exhausted milestone payload.

    Novelty uses every issued id. `answered_count` is distinct *completed*
    bank ids only — not queued, running, failed, or abandoned. It is not a
    hardcoded 290, and it is not an "about" figure.
    """
    items = tuple(bank) if bank is not None else published_items()
    seen = {sid for sid in seen_scenario_ids if sid}
    completed = {sid for sid in completed_scenario_ids if sid}
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
    )
