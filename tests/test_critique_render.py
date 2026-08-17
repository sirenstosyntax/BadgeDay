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
from app.critique.render import REUSE, WORK_ON, WORKED, render_for_candidate, sections
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
                # Phrased as a fork rather than an instruction. The obvious wording — "that
                # is the thing to go and get" — is what `_PRESCRIBES_REMEDY` rejects, so a
                # fixture using it is not a critique that could ship, and a rendering test
                # should render something the gate would actually pass.
                ask="Has that happened? If it has not, that is a real gap and a fixable one.",
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


# --- The candidate's view ----------------------------------------------------
#
# The inspection view above prints clause ids, the internal score and the determination.
# All three are things requirement 6 and §1 exist to keep from the candidate, and the
# inspection view reads like a finished artifact — so the risk was never that somebody
# would deliberately show it to him, it was that a UI would get built on top of the thing
# that was already there.


def test_the_candidate_is_never_shown_a_clause_id(critique, capsys):
    render_for_candidate(critique)
    out = capsys.readouterr().out
    assert "c3.anchor.5" not in out
    assert "c3.note.10" not in out
    assert "c3.note.2" not in out


def test_the_candidate_is_never_shown_the_anchor_label(critique, capsys):
    """The rubric's own headings are the instrument talking about itself."""
    render_for_candidate(critique)
    out = capsys.readouterr().out
    assert "He demonstrably behaves well on a crew" not in out
    assert "Score the cast of the story" not in out


def test_the_candidate_is_never_shown_the_score_or_the_determination(critique, capsys):
    """Surfaced scores get optimised; surfaced gaps get worked on. §1."""
    render_for_candidate(critique)
    out = capsys.readouterr().out
    assert "internal" not in out.lower()
    assert "decided by" not in out
    assert critique.determination not in out


def test_the_candidate_still_gets_the_substance(critique, capsys):
    """Stripping the instrument must not strip the feedback."""
    render_for_candidate(critique)
    out = capsys.readouterr().out
    assert "Ryan went to the supervisor himself and you said so." in out
    assert "Nothing across your answers shows you telling somebody something unwelcome." in out
    assert "Has that happened?" in out


def test_both_views_render_the_same_sections_in_the_same_order(critique):
    """The anti-drift property, asserted rather than hoped for.

    Two independent renderers would agree on the day they were written and not for long,
    and the order carries a review finding — whatever comes first is taken as the verdict.
    """
    inspection = [heading for heading, _, _ in sections(critique)]
    candidate = [heading for heading, _, _ in sections(critique, candidate_facing=True)]
    assert inspection == candidate
    assert inspection == [WORKED, WORK_ON, REUSE]


def test_the_candidate_view_does_not_use_the_phrasing_the_gate_forbids(critique, capsys):
    """It would be strange to reject "go and get" from the model and print it as a heading."""
    render_for_candidate(critique)
    out = capsys.readouterr().out
    assert "the thing to go and get" not in out


def test_a_not_assessable_critique_says_it_is_not_a_mark_against_him(capsys):
    """The whole point of the third outcome: it is a finding, not a low score."""
    critique = Critique(
        criterion_id="c3",
        criterion_name="Criterion 3 — Teamwork & Interpersonal",
        outcome="not_assessable",
        deciding_clause=NOTE_2,
        determination="He has worked alone since he was twenty-one.",
        internal_score=0,
        route="n/a",
        points=[
            _point(
                "inventory",
                NOTE_2,
                "You describe a working life with nobody else in it.",
                ask="Military service, sport, a kitchen, a church group — any of those count.",
            )
        ],
    )
    render_for_candidate(critique)
    out = capsys.readouterr().out
    assert "not a mark against you" in out
    assert "0" not in out.split("not a mark against you")[0]
