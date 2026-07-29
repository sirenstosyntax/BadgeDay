"""Recognizing outline structure across numbering conventions.

Departments do not agree on how to number a guideline. Two families cover what real
documents use:

**Decimal** — `304`, `304.2`, `304.2.1`. Self-describing: the number states its own depth.

**Ordinal markers** — `A.` `B.` then `1.` `2.` then `a.` `b.` then `i.` `ii.`, the classic
legal outline. A marker states its position among siblings but says nothing about depth;
`1.` might be a top-level item in one document and three levels down in another. Depth is
therefore inferred from the order styles first appear, which is how a human reads one too.

**Named headings** carry no marker at all — `PURPOSE`, `BACKGROUND`, `PROCEDURE`. These
are recognized from Document Intelligence's `sectionHeading` role rather than from text
shape, because shape does not distinguish them from anything else in capitals. On a real
guideline that role is precise; on a document rendered in a single uniform font it finds
almost nothing, since it depends on visual cues.

## Why not just match capitals

Matching ALL-CAPS lines would find `PURPOSE` — and would also manufacture thirty sections
out of an org chart, turning `COMMAND`, `SAFETY`, `LOGISTICS`, and `BACKUP` into citable
locations. Diagram labels look exactly like headings and are not headings. The role
tagging ignores them; a shape rule cannot.

## Guarding against false markers

A stray `1.` opening a sentence is the ordinal-marker equivalent of `2.5 gallons`. The
guard is sequence: a marker is accepted only if it opens a list (`A`, `1`, `a`, `i`) or
continues one (the successor of the previous sibling). Prose rarely satisfies that by
accident, and when it does it is genuinely a list.

## Markers that lose their space

Real documents contain typos, and `ii.Fire personnel` is one a fire captain will never
notice. The recognizer tolerates a missing space after an ordinal marker when a capital
follows — see `_MARKER_GAP` for why that condition, and why decimal is excluded.
"""

import re
from dataclasses import dataclass
from enum import StrEnum

# A heading short enough to be a title rather than a sentence of body text. Outline items
# are usually full sentences and get no title; named headings and short labels get one.
MAX_TITLE_WORDS = 12

ROLE_SECTION_HEADING = "sectionHeading"


class MarkerStyle(StrEnum):
    DECIMAL = "decimal"
    UPPER_ALPHA = "upper_alpha"
    ARABIC = "arabic"
    LOWER_ALPHA = "lower_alpha"
    LOWER_ROMAN = "lower_roman"
    NAMED = "named"


_LOWER_ROMAN = [
    "i",
    "ii",
    "iii",
    "iv",
    "v",
    "vi",
    "vii",
    "viii",
    "ix",
    "x",
    "xi",
    "xii",
    "xiii",
    "xiv",
    "xv",
    "xvi",
    "xvii",
    "xviii",
    "xix",
    "xx",
]

# A marker is normally followed by whitespace. Real documents lose it — the reference SOG
# this pipeline was validated against carries `ii.Fire personnel should be aware…` — and
# an unrecognized marker does not fail loudly: the item folds into its predecessor, and
# every citation beneath it silently coarsens. That is the failure class this module
# exists to prevent, so the missing space has to be tolerated.
#
# Tolerating it outright would trade the bug for a worse one. `a.m.` would open a lettered
# list and `e.g.` a roman one, manufacturing sections out of ordinary prose. Requiring the
# next character to be a capital rejects both — what follows those abbreviations is
# lowercase — and costs nothing real, because an outline item starts with a capital.
_MARKER_GAP = r"(?:\s+|(?=[A-Z]))"

# Decimal is deliberately left requiring real whitespace. It is the family that collides
# with measurements, and in a fire document the collisions are everywhere: `2.5GPM`,
# `1.5NST`, `4.5PSI` would each become a citable section, every one of them followed by a
# capital. `decimal_follows` guards the same risk from the other side; this keeps both
# lines of defense. A decimal outline that also loses its spaces is a problem worth
# seeing evidence of before widening the rule to meet it.
PATTERNS: list[tuple[MarkerStyle, re.Pattern[str]]] = [
    (MarkerStyle.DECIMAL, re.compile(r"^(\d+(?:\.\d+)+)[.)]?\s+(\S.*)$")),
    (MarkerStyle.UPPER_ALPHA, re.compile(rf"^([A-Z])[.)]{_MARKER_GAP}(\S.*)$")),
    (MarkerStyle.ARABIC, re.compile(rf"^(\d{{1,3}})[.)]{_MARKER_GAP}(\S.*)$")),
    (
        MarkerStyle.LOWER_ROMAN,
        re.compile(rf"^({'|'.join(_LOWER_ROMAN)})[.)]{_MARKER_GAP}(\S.*)$"),
    ),
    (MarkerStyle.LOWER_ALPHA, re.compile(rf"^([a-z])[.)]{_MARKER_GAP}(\S.*)$")),
]


@dataclass(frozen=True)
class Marker:
    """A recognized heading marker and the text that followed it."""

    style: MarkerStyle
    label: str
    text: str

    @property
    def title(self) -> str | None:
        """The heading's title, when it reads as one rather than as body text."""
        if len(self.text.split()) <= MAX_TITLE_WORDS:
            return self.text.strip()
        return None


def parse_marker(text: str, role: str | None = None) -> Marker | None:
    """Recognize a heading marker, or a named heading from its layout role."""
    stripped = text.strip()
    if not stripped:
        return None

    for style, pattern in PATTERNS:
        match = pattern.match(stripped)
        if match:
            return Marker(style=style, label=match.group(1), text=match.group(2).strip())

    if role == ROLE_SECTION_HEADING:
        return Marker(style=MarkerStyle.NAMED, label=stripped, text=stripped)

    return None


def decimal_depth(label: str) -> int:
    """How deep a decimal number sits: 304 is 1, 304.2 is 2, 304.2.1 is 3."""
    return len(label.split("."))


def _alpha_index(label: str) -> int:
    return ord(label.lower()) - ord("a")


def sequence_index(style: MarkerStyle, label: str) -> int | None:
    """Position of a marker within its sibling sequence, 0-based.

    `None` for styles with no inherent sequence (decimal carries its own structure,
    named headings have no ordering).
    """
    if style in (MarkerStyle.UPPER_ALPHA, MarkerStyle.LOWER_ALPHA):
        return _alpha_index(label)
    if style is MarkerStyle.ARABIC:
        return int(label) - 1
    if style is MarkerStyle.LOWER_ROMAN:
        return _LOWER_ROMAN.index(label.lower())
    return None


def opens_or_continues(style: MarkerStyle, label: str, previous_label: str | None) -> bool:
    """Does this marker start a list, or follow on from the previous sibling?

    The check that stops a sentence beginning `1.` from becoming a section. A marker
    either opens a sequence or succeeds its predecessor; a number that does neither is
    prose that happens to start with a digit.
    """
    index = sequence_index(style, label)
    if index is None:
        return True
    if previous_label is None:
        return index == 0
    previous_index = sequence_index(style, previous_label)
    if previous_index is None:
        return True
    return index == previous_index + 1


def decimal_follows(candidate: str, previous: str | None) -> bool:
    """Could this decimal number follow the previous one in a well-formed outline?

    Valid: a descendant (304.2 -> 304.2.1), or a sibling of it or of one of its
    ancestors (304.2.2 -> 304.3, or -> 305).

    Invalid: repeating, moving backwards, or an unrelated branch — which is what a
    measurement like `2.5 gallons` looks like arriving after 304.2.2. Shape alone cannot
    tell the two apart; position in the outline can.
    """
    if previous is None:
        return True

    parts = tuple(int(p) for p in candidate.split("."))
    prior = tuple(int(p) for p in previous.split("."))

    if len(parts) > len(prior) and parts[: len(prior)] == prior:
        return True

    for index in range(min(len(parts), len(prior))):
        if parts[index] != prior[index]:
            # Everything before `index` matched, so this is a sibling at that level.
            return parts[index] > prior[index]

    return False


def is_ambiguous_roman(label: str) -> bool:
    """`i`, `v`, and `x` are both roman numerals and letters of the alphabet.

    Which one is meant depends on what came before: an `i.` following `h.` continues a
    lettered list, while an `i.` following `d.` opens a nested roman one.
    """
    return label.lower() in ("i", "v", "x")
