"""Family → criterion and full-board draw groups.

A · B/C · D/E/F · G/H · J. Commitment (CMT / letter I) stays in the published
bank so never-repeat is honest, but it is not a board slot. C1 is scored
across the whole board; OPN still carries criterion_id c1 so the J slot is
transcribed and noted, while the official C1 block is the whole-board pass.
"""

from __future__ import annotations

GROUP_CRITERION: dict[str, str] = {
    "MOT": "c2",
    "TEA": "c3",
    "CON": "c3",
    "INT": "c4",
    "STR": "c5",
    "JUD": "c5",
    "SLF": "c5",
    "JOB": "c2",
    "CMT": "c2",
    "OPN": "c1",
}

# Letter used in recruit_question_bank.md (A–J).
GROUP_LETTER: dict[str, str] = {
    "MOT": "A",
    "TEA": "B",
    "CON": "C",
    "INT": "D",
    "STR": "E",
    "JUD": "F",
    "SLF": "G",
    "JOB": "H",
    "CMT": "I",
    "OPN": "J",
}

# One item from each of these five pools. Order is the board order.
DRAW_SLOTS: tuple[tuple[str, frozenset[str]], ...] = (
    ("A", frozenset({"A"})),
    ("BC", frozenset({"B", "C"})),
    ("DEF", frozenset({"D", "E", "F"})),
    ("GH", frozenset({"G", "H"})),
    ("J", frozenset({"J"})),
)

ALL_GROUPS = frozenset(GROUP_CRITERION)
C2_GROUPS = frozenset({"MOT", "JOB", "CMT"})


def criterion_for_family(family: str) -> str:
    group = family.split("-", 1)[0]
    try:
        return GROUP_CRITERION[group]
    except KeyError as exc:
        raise KeyError(f"unknown family group {group!r}") from exc


def letter_for_family(family: str) -> str:
    group = family.split("-", 1)[0]
    try:
        return GROUP_LETTER[group]
    except KeyError as exc:
        raise KeyError(f"unknown family group {group!r}") from exc
