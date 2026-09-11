"""Parse `recruit_question_bank_draft.md` into typed bank rows.

The live bank is a generated artifact (`bank_data.py`). This module is the
parser that artifact is built from, so tests can prove STRIKE skipping and
group counts without depending on a hand-edited list.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from app.recruit.families import ALL_GROUPS, C2_GROUPS, GROUP_CRITERION, criterion_for_family

C2_CRITERION_ID = "c2"

DRAFT_PATH = Path(__file__).resolve().parents[2] / "recruit_question_bank_draft.md"

_FAMILY_RE = re.compile(r"^## ([A-Z]{3}-\d+) —")
_VARIANT_RE = re.compile(r"^(\d+)\.\s+(.+)$")
_STRIKE_TEXT_RE = re.compile(r"~~(.+?)~~")

# Real department / vendor proper names. Candidate-facing text says
# "this department", never a named one.
_FD_NAME_RE = re.compile(
    r"\b(?:"
    r"Salt Lake City|SLC Fire|Unified Fire Authority|"
    r"Tulsa Fire|Seattle Fire|Columbus Fire|Duncanville|"
    r"Cal-JAC|LAFD|FDNY|Los Angeles Fire|Chicago Fire|"
    r"Phoenix Fire|Houston Fire|Boston Fire|Austin Fire|"
    r"Denver Fire|Miami-Dade|Fairfax County|Montgomery County|"
    r"National Testing Network|FireTEAM|IPMA-HR|CPS HR|"
    r"I/O Solutions|NTN FireTEAM"
    r")\b",
    re.I,
)
_PROPER_FIRE_DEPT_RE = re.compile(
    r"\b[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*\s+Fire (?:Department|Dept\.?)\b"
)


@dataclass(frozen=True)
class DraftItem:
    scenario_id: str
    question_text: str
    family: str
    criterion_id: str
    struck: bool = False


def parse_draft(
    text: str,
    *,
    groups: Iterable[str] | None = None,
    criterion_id: str | None = None,
) -> tuple[DraftItem, ...]:
    """Family variants in document order. Struck rows stay, marked ``struck``.

    When ``criterion_id`` is omitted, each family gets the criterion for its
    group (MOT→c2, TEA→c3, …). Passing one id forces every kept row to that
    id — used by the C2-only parser tests.
    """
    wanted = frozenset(groups) if groups is not None else ALL_GROUPS
    items: list[DraftItem] = []
    family: str | None = None
    group: str | None = None

    for line in text.splitlines():
        heading = _FAMILY_RE.match(line)
        if heading:
            family = heading.group(1)
            group = family.split("-", 1)[0]
            continue
        if line.startswith("# ") or (line.startswith("## ") and not line.startswith("### ")):
            family = None
            group = None
            continue
        if family is None or group not in wanted:
            continue
        variant = _VARIANT_RE.match(line)
        if variant is None:
            continue
        number, raw = variant.group(1), variant.group(2)
        question_text, struck = _variant_text(raw)
        if not question_text:
            continue
        assigned = criterion_id if criterion_id is not None else criterion_for_family(family)
        items.append(
            DraftItem(
                scenario_id=f"{family}.{number}",
                question_text=question_text,
                family=family,
                criterion_id=assigned,
                struck=struck,
            )
        )
    return tuple(items)


def issuable(items: Iterable[DraftItem]) -> tuple[DraftItem, ...]:
    """Non-STRIKE rows only."""
    return tuple(item for item in items if not item.struck)


def parse_issuable(
    text: str | None = None,
    *,
    groups: Iterable[str] | None = None,
) -> tuple[DraftItem, ...]:
    source = DRAFT_PATH.read_text() if text is None else text
    return issuable(parse_draft(source, groups=groups))


def parse_issuable_c2(text: str | None = None) -> tuple[DraftItem, ...]:
    source = DRAFT_PATH.read_text() if text is None else text
    return issuable(parse_draft(source, groups=C2_GROUPS, criterion_id=C2_CRITERION_ID))


def _variant_text(raw: str) -> tuple[str, bool]:
    struck = "~~" in raw or "`STRIKE`" in raw or "**STRIKE**" in raw
    if struck:
        inner = _STRIKE_TEXT_RE.search(raw)
        text = inner.group(1).strip() if inner else raw
        text = re.sub(r"\s*\*\*`?STRIKE`?\*\*.*$", "", text).strip()
        return text, True
    return raw.strip(), False


def fd_name_hits(text: str) -> tuple[str, ...]:
    """Proper department / vendor names that must not appear in issued text."""
    found = [match.group(0) for match in _FD_NAME_RE.finditer(text)]
    found.extend(match.group(0) for match in _PROPER_FIRE_DEPT_RE.finditer(text))
    return tuple(found)


# Re-export so existing imports keep working.
__all__ = [
    "ALL_GROUPS",
    "C2_CRITERION_ID",
    "C2_GROUPS",
    "DRAFT_PATH",
    "DraftItem",
    "GROUP_CRITERION",
    "fd_name_hits",
    "issuable",
    "parse_draft",
    "parse_issuable",
    "parse_issuable_c2",
]
