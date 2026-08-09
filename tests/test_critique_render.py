"""What a critique looks like on the page.

Ordinarily rendering is not worth pinning. It is here because the 2026-08-06 calibration
review's finding was a *rendering* finding as much as a content one: a broad
evidence-inventory gap read as the primary weakness of a strong answer, and a caution about
reusing the story would have read as a fault if it had been printed among the gaps.

Whatever comes first is taken as the verdict, so the order and the headings carry the
distinction the `improvement` field exists to make. A test that only asserts the field is
set would pass while the man reading it drew the opposite conclusion.
"""

import pytest

from app.critique.cli import render_critique
from app.critique.models import Critique, Point
from app.critique.rubric import Clause

ANCHOR_5 = Clause("c3.anchor.5", "anchor", "He demonstrably behaves well on a crew")
NOTE_10 = Clause("c3.note.10", "note", "A reuse or delivery risk is reported")
NOTE_2 = Clause("c3.note.2", "note", "Score the cast of the story, not its adjectives")


def _point(improvement: str, clause: Clause, observation: str, ask: str | None = None) -> Point:
    return Point(
        kind="rubric",
        improvement=improvement,
        clause=clause,
        observation=observation,
        ask=ask,
    )


@pytest.fixture
def critique() -> Critique:
    """A strong answer: one thing that worked, one broad inventory gap, one reuse risk."""
    return Critique(
        criterion_id="c3",
        criterion_name="Criterion 3 — Teamwork & Interpersonal",
        outcome="scored",
        deciding_clause=ANCHOR_5,
        determination="He stayed in it until Ryan said what was actually going on.",
        internal_score=5,
        route="n/a",
        points=[
            _point("none", ANCHOR_5, "Ryan went to the supervisor himself and you said so."),
            _point(
                "inventory",
                NOTE_2,
                "Nothing across your answers shows you telling somebody something unwelcome.",
                ask="Has that happened? If it has not, that is the thing to go and get.",
            ),
            _point(
                "risk",
                NOTE_10,
                "Opening with a claim about yourself puts the claim ahead of the story.",
            ),
        ],
    )


def test_what_worked_is_read_first(critique, capsys):
    """He is about to read what to work on. The order is what stops that being a verdict."""
    render_critique(critique, draft=True)
    out = capsys.readouterr().out
    assert out.index("WHAT YOU DID WELL") < out.index("WHAT YOU COULD WORK ON")


def test_a_broad_inventory_gap_is_labelled_as_beyond_this_answer(critique, capsys):
    """The finding of 2026-08-06: it is not what was wrong with the answer he just gave.

    It would be equally true of a better one, and printed without the qualifier it reads as
    the verdict on this answer.
    """
    render_critique(critique, draft=True)
    out = capsys.readouterr().out
    heading = next(line for line in out.splitlines() if "better story" in line)
    assert "beyond this answer" in heading


def test_a_reuse_risk_is_its_own_section_and_comes_last(critique, capsys):
    """Scoring note 10: it is a caution attached to material that worked, not a fault."""
    render_critique(critique, draft=True)
    out = capsys.readouterr().out
    assert "IF YOU USE THIS STORY AGAIN" in out
    assert out.index("WHAT YOU COULD WORK ON") < out.index("IF YOU USE THIS STORY AGAIN")
    assert "Nothing below is wrong with the answer you gave" in out


def test_a_risk_does_not_appear_among_the_gaps(critique, capsys):
    """Rendered as a gap it would tell him he did badly at something he did not do."""
    render_critique(critique, draft=True)
    out = capsys.readouterr().out
    gaps, _, risks = out.partition("IF YOU USE THIS STORY AGAIN")
    assert "c3.note.10" in risks
    assert "c3.note.10" not in gaps


def test_the_score_is_not_rendered_as_a_score(critique, capsys):
    """It is printed for the SME behind a label saying it is internal, and nowhere else."""
    render_critique(critique, draft=True)
    out = capsys.readouterr().out
    assert "[internal, never shown to a candidate: 5]" in out
