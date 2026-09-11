"""Two views of a critique: the one the SME inspects, and the one the candidate reads.

They must not be two renderers. `render_critique` used to carry a note saying a second
renderer beside it would drift, and that was right — the 2026-08-06 review's finding was a
*rendering* finding, and the order and headings are doing work no field can do. Two
independent implementations of that would agree on the day they were written and not for
long.

So the structure is shared and only the point formatting differs. `sections()` decides
which sections exist, in what order, with what headings and which points in each; both
views walk the same list. A change to the order changes both, which is the only way the
inspection view can go on being evidence about what the candidate will see.

**Why the split exists at all.** `render_critique` prints each point's clause id and the
rubric's own heading as its label — right for an SME reading a determination, and exactly
what requirement 6 exists to keep from the candidate. It also prints the internal score.
The inspection view reads like a finished artifact, so the risk was never that somebody
would deliberately show it to a candidate; it was that step 4 would build a UI on top of
the thing that was already there.
"""

import re
from collections.abc import Iterable, Sequence

from app.critique.models import Critique, Point
from app.recruit.copy import (
    C1_COSTS,
    C1_HELD,
    C1_INSUFFICIENT,
    C1_LEAD,
    C1_NOT_ANSWERED,
    C1_OUTSIDE,
    C1_OUTSIDE_BODY,
    PER_ANSWER_NOT_ANSWERED,
    PER_ANSWER_NOT_ASSESSABLE,
)

# The three sections, in reading order, with the note under each. Read down: what he did,
# then what to work on, then what to watch if he tells this story again.
#
# The middle section's sub-notes carry the distinction the `improvement` field exists to
# make. SME review 2026-08-06: a broad evidence-inventory gap was read as the primary
# weakness of a strong answer, which it was not — it would have been just as true of a
# better one. Whatever comes first is taken as the verdict, so the wording is what stops it
# being read that way.
WORKED = "WHAT YOU DID WELL"
WORK_ON = "WHAT YOU COULD WORK ON"
REUSE = "IF YOU USE THIS STORY AGAIN"

_IN_THIS_ANSWER = "in this answer — it is here and handled badly"
_BEYOND_INVENTORY = (
    "beyond this answer — your stock of examples, not what you just said. "
    "is there a better story? if not, that is the thing to go and get"
)
_BEYOND_ABSENT = "beyond this answer — you said you have not done this"

# The candidate view's wording of the same two notes. Deliberately not the strings above.
#
# "that is the thing to go and get" is phrasing `_PRESCRIBES_REMEDY` rejects when a model
# writes it, and it would be strange to forbid it in a generated ask and then print it as a
# heading over that ask. It survives in the inspection view because those strings are pinned
# by tests as the record of a review finding; the candidate is the one who should not be
# read the directive form.
_CANDIDATE_IN_THIS_ANSWER = "in this answer — the material is here and did not land"
_CANDIDATE_BEYOND_INVENTORY = (
    "beyond this answer — about your stock of examples rather than what you just said. "
    "is there a better one? if there is not, that is worth knowing"
)
_CANDIDATE_BEYOND_ABSENT = "beyond this answer — from what you said, this has not come up yet"


def sections(
    critique: Critique, *, candidate_facing: bool = False
) -> list[tuple[str, str | None, list[Point]]]:
    """(heading, sub-note, points) in reading order, omitting anything empty.

    The single source of the shape both views render. A risk gets its own section and comes
    last: it is a caution attached to material that worked, and printed among the gaps it
    reads as a fault, which is the one thing scoring note 10 says it is not.
    """
    in_this = _CANDIDATE_IN_THIS_ANSWER if candidate_facing else _IN_THIS_ANSWER
    inventory = _CANDIDATE_BEYOND_INVENTORY if candidate_facing else _BEYOND_INVENTORY
    absent = _CANDIDATE_BEYOND_ABSENT if candidate_facing else _BEYOND_ABSENT

    out: list[tuple[str, str | None, list[Point]]] = []
    if critique.worked:
        out.append((WORKED, None, critique.worked))
    for note, points in (
        (in_this, critique.answer_gaps),
        (inventory, critique.inventory_gaps),
        (absent, critique.development_gaps),
    ):
        if points:
            out.append((WORK_ON, note, points))
    if critique.risks:
        out.append((REUSE, None, critique.risks))
    return out


def _print_grouped(
    grouped: Iterable[tuple[str, str | None, list[Point]]],
    show: object,
    *,
    reuse_preamble: str,
) -> None:
    """Walk the sections, printing each heading once even when it has several sub-notes."""
    last_heading: str | None = None
    for heading, note, points in grouped:
        if heading != last_heading:
            print(f"\n  {heading}")
            if heading == REUSE:
                print(reuse_preamble)
            last_heading = heading
        if note:
            print(f"\n    — {note}")
        for point in points:
            show(point)


# --- The SME's view ----------------------------------------------------------


def render_critique(critique: Critique, draft: bool) -> None:
    """Print a critique for inspection. Public because the run harnesses reuse it.

    Shows the clause ids, the internal score and the determination — everything step 3 is a
    judgment about. None of it may reach a candidate; that is `render_for_candidate`.
    """
    print(f"\n=== {critique.criterion_name} ===")
    if draft:
        print("    (DRAFT RUBRIC — anchors are unreviewed; critique shown for inspection only)")

    if critique.outcome == "not_assessable":
        print("\n  NOT ASSESSABLE — this answer establishes the material is not in his history.")
        print("  Not a low score. A finding, and one the points below have to support by")
        print("  quoting him.")
    elif critique.outcome == "not_answered":
        print("\n  NOT ANSWERED — nothing here to judge either way.")
        print("  Not a low score and not a finding about his life. He was silent on it,")
        print("  which is not the same as never having done it. The points below ask.")
    else:
        # The score is internal and deliberately not rendered to a candidate. It is printed
        # here behind a label that says so, because this is an inspection tool for the SME
        # and step 3 is a judgment about whether the score and the critique agree.
        route = f" ({critique.route})" if critique.route != "n/a" else ""
        print(f"\n  [internal, never shown to a candidate: {critique.internal_score}{route}]")
        # The determination is the part worth reading at step 3. The number says the anchors
        # and the SME disagree; this says which clause did it and on what reading, which is
        # the difference between a divergence you can act on and one you can only count.
        if critique.deciding_clause:
            print(f"  [decided by {critique.deciding_clause.clause_id}: {critique.determination}]")

    def show(point: Point) -> None:
        anchor = point.clause.clause_id if point.clause else f"metric:{point.metric.name}"
        print(f"\n  • [{anchor}] {point.anchor_label()}")
        if point.answer_quote:
            print(f'      you said: "{point.answer_quote}"')
        print(f"      {point.observation}")
        if point.ask:
            print(f"      → {point.ask}")

    _print_grouped(
        sections(critique),
        show,
        reuse_preamble=(
            "    Nothing below is wrong with the answer you gave. It is what would cost\n"
            "    you the next time you tell it."
        ),
    )


# --- The candidate's view ------------------------------------------------------


def candidate_lines(critique: Critique) -> list[str]:
    """The critique as the candidate should receive it, as lines.

    Returns lines rather than printing, because the surface that will use this is a web app
    and not a terminal — step 5's API renders from the same function the CLI preview does,
    so what a reviewer previews is what a candidate gets.

    **What is excluded, and why each one.** Clause ids and anchor labels: requirement 6, the
    instrument does not talk about itself to the man reading it. The internal score: §1, and
    surfaced scores get optimised where surfaced gaps get worked on. The determination:
    internal reasoning about which anchor applied, which is a sentence about the rubric
    rather than about him.
    """
    lines: list[str] = []

    if critique.outcome == "not_assessable":
        lines.append(
            "From what you said, this has not come up in your working life yet — so there is "
            "nothing here to judge you on, and this is not a mark against you."
        )
    elif critique.outcome == "not_answered":
        lines.append(
            "There was not enough in that answer to say anything useful about it yet."
        )

    for heading, note, points in sections(critique, candidate_facing=True):
        if not lines or lines[-1] != "":
            lines.append("")
        lines.append(heading)
        if heading == REUSE:
            lines.append(
                "Nothing below is wrong with the answer you gave. It is what would cost you "
                "the next time you tell it."
            )
        if note:
            lines.append(f"— {note}")
        for point in points:
            lines.append("")
            if point.answer_quote:
                lines.append(f'You said: "{point.answer_quote}"')
            lines.append(point.observation)
            if point.ask:
                lines.append(f"→ {point.ask}")

    return lines


def render_for_candidate(critique: Critique) -> None:
    """Print the candidate's view. A preview of a surface that does not exist yet."""
    for line in candidate_lines(critique):
        print(line)


def board_answer_lines(critique: Critique) -> list[str]:
    """Per-answer notes at board end. Same shape as `candidate_lines`, signed AC7/AC8."""
    lines = candidate_lines(critique)
    if critique.outcome == "not_assessable":
        return [PER_ANSWER_NOT_ASSESSABLE, *lines[1:]]
    if critique.outcome == "not_answered":
        return [PER_ANSWER_NOT_ANSWERED, *lines[1:]]
    return lines


_PRESENCE_RE = re.compile(
    r"\b(presence|eye contact|how you sit|sit in the room|sitting in the room)\b",
    re.I,
)


def routes_presence(critique: Critique) -> bool:
    """True when the critique sends presence / eye contact off the tool."""
    for point in critique.points:
        blob = f"{point.observation} {point.ask or ''}"
        if _PRESENCE_RE.search(blob):
            return True
    return False


def c1_candidate_lines(critique: Critique) -> list[str]:
    """Whole-board C1 block. Headings and lead are Red-signed."""
    if critique.outcome == "not_answered":
        return [C1_NOT_ANSWERED]
    if critique.outcome == "not_assessable":
        return [C1_INSUFFICIENT]

    lines: list[str] = [C1_LEAD]
    held = critique.worked
    costs = (
        critique.answer_gaps
        + critique.inventory_gaps
        + critique.development_gaps
        + critique.risks
    )
    if held:
        if lines[-1] != "":
            lines.append("")
        lines.append(C1_HELD)
        _append_point_lines(lines, held)
    if costs:
        if not lines or lines[-1] != "":
            lines.append("")
        lines.append(C1_COSTS)
        _append_point_lines(lines, costs)
    if routes_presence(critique):
        if not lines or lines[-1] != "":
            lines.append("")
        lines.append(C1_OUTSIDE)
        lines.append(C1_OUTSIDE_BODY)
    return lines


def _append_point_lines(lines: list[str], points: list[Point]) -> None:
    for point in points:
        lines.append("")
        if point.answer_quote:
            lines.append(f'You said: "{point.answer_quote}"')
        lines.append(point.observation)
        if point.ask:
            lines.append(f"→ {point.ask}")


# Board-end must never leak the instrument. Checked on the assembled payload.
_BOARD_END_BANNED = re.compile(
    r"(?ix)"
    r"\b(?:internal[_\s-]?score|criterion\s*[1-5]|anchor\s*[1-5]"
    r"|c[1-5]\.(?:anchor|note)\.\S+"
    r"|delivery\s+(?:clear|costly|blocking)"
    r"|4[ab]\b|determination|deciding clause"
    r"|answer construction|motivation & preparation"
    r"|teamwork & interpersonal|integrity & ethics"
    r"|judgment & composure)\b"
)


def board_end_leaks(lines: Sequence[str] | list[str]) -> tuple[str, ...]:
    """Return banned fragments found in board-end lines."""
    found: list[str] = []
    for line in lines:
        match = _BOARD_END_BANNED.search(line)
        if match:
            found.append(match.group(0))
    return tuple(found)
