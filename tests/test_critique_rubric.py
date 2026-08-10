"""Rubric parsing tests.

The clause catalogue is what the verification gate checks against, and it is derived from
the rubric markdown rather than maintained beside it. That choice removes one failure mode
— a hand-kept list drifting from the rubric while still passing — and introduces another:
a heading whose format changes silently stops being citable, and every point that would
have cited it gets rejected instead.

So these tests pin the heading formats the parser depends on, and assert against the real
rubric files rather than only against synthetic ones.
"""

from pathlib import Path

import pytest

from app.critique import rubric as rubric_module
from app.critique.rubric import parse_clauses, scorer_region

REGION = """
## Scoring notes

**1. Score the cast of the story, not its adjectives.**
Body text that is not itself citable.

**2. The behavioural frame: a specific incident, not a self-description.**
More body.

## Anchors

### 5 — Other people are real in his account

### 4 — Strong on one axis, short on the other

**4A — Wants the crew; rough edges.**

**4B — Handles people; appetite unproven.**

### 3 — Says the right things; the team stays generic

### 2 — Qualified, and the crew is missing from his own stories

### 1 — The problem is in the room
"""


def test_notes_and_anchors_are_both_citable():
    ids = {clause.clause_id for clause in parse_clauses("c3", REGION)}
    assert "c3.note.1" in ids
    assert "c3.anchor.5" in ids
    assert "c3.anchor.1" in ids


def test_lettered_routes_are_citable_separately_from_their_level():
    ids = {clause.clause_id for clause in parse_clauses("c3", REGION)}
    assert {"c3.anchor.4", "c3.anchor.4A", "c3.anchor.4B"} <= ids


def test_clauses_are_returned_in_document_order():
    """The catalogue is shown to the model; scrambled order makes it harder to read."""
    ids = [clause.clause_id for clause in parse_clauses("c3", REGION)]
    assert ids.index("c3.note.1") < ids.index("c3.anchor.5")
    assert ids.index("c3.anchor.4") < ids.index("c3.anchor.4A")


def test_clause_ids_are_unique():
    clauses = parse_clauses("c3", REGION)
    assert len({clause.clause_id for clause in clauses}) == len(clauses)


def test_body_prose_is_not_citable():
    """Only headings are clauses; a point cannot cite a sentence of body text."""
    labels = {clause.label for clause in parse_clauses("c3", REGION)}
    assert not any("Body text" in label for label in labels)


def test_scorer_region_excludes_material_outside_the_markers():
    text = (
        "# Title\n\n> DRAFT — NOT SME-APPROVED\n\n"
        "<!-- scorer:start — note -->\n\n## Scoring notes\n\nbody\n\n"
        "<!-- scorer:end -->\n\n## Provenance and limitations\n\nauthored by nobody\n"
    )
    region = scorer_region(text)
    assert "DRAFT" not in region
    assert "Provenance" not in region
    assert "## Scoring notes" in region


def test_missing_markers_are_an_error_rather_than_a_silent_full_read():
    with pytest.raises(ValueError, match="scorer:start"):
        scorer_region("# Title\n\n## Scoring notes\n")


# --- Against the real rubrics ------------------------------------------------


@pytest.mark.parametrize("criterion_id", sorted(rubric_module.RUBRIC_FILES))
def test_real_rubric_parses_and_yields_the_expected_clause_shape(criterion_id):
    root = Path(__file__).resolve().parents[1]
    rubric = rubric_module.load(criterion_id, root=root)

    ids = rubric.clause_ids
    # Every rubric carries a full 1-5 scale and at least one scoring note.
    for level in range(1, 6):
        assert f"{criterion_id}.anchor.{level}" in ids, f"missing anchor {level}"
    assert any(clause.kind == "note" for clause in rubric.clauses)

    # Both criteria currently split level 4 into routes.
    assert {f"{criterion_id}.anchor.4A", f"{criterion_id}.anchor.4B"} <= ids

    # No clause carries an empty label, which would render as a blank catalogue line.
    assert all(clause.label.strip() for clause in rubric.clauses)


def test_real_rubrics_do_not_leak_authorship_or_provenance_to_the_model():
    """A draft rubric must not be critiqued differently for announcing that it is a draft."""
    root = Path(__file__).resolve().parents[1]
    for criterion_id in rubric_module.RUBRIC_FILES:
        text = rubric_module.load(criterion_id, root=root).text
        for forbidden in ("DRAFT", "NOT SME-APPROVED", "drafted by Claude", "Provenance"):
            assert forbidden not in text, f"{criterion_id} leaks {forbidden!r}"


def test_criterion_ids_do_not_collide_across_rubrics():
    """Cross-criterion citation is a real failure mode; the IDs must make it detectable."""
    root = Path(__file__).resolve().parents[1]
    seen: set[str] = set()
    for criterion_id in rubric_module.RUBRIC_FILES:
        ids = rubric_module.load(criterion_id, root=root).clause_ids
        assert not (ids & seen), "clause IDs collide between rubrics"
        seen |= ids


def test_the_reuse_risk_note_is_citable_on_the_real_c3_rubric():
    """A risk point cites this note. If the heading stops parsing, every risk is unanchorable.

    Worth pinning separately from the shape test above: the failure is silent in exactly the
    way the parse-don't-maintain-a-list decision was meant to prevent. The clause would
    simply stop existing, and the gate would reject a class of point that the prompt still
    asks for — which reads as the model misbehaving rather than as a heading that lost its
    format.
    """
    root = Path(__file__).resolve().parents[1]
    rubric = rubric_module.load("c3", root=root)
    assert "c3.note.10" in rubric.clause_ids
    assert "reuse" in rubric.clause("c3.note.10").label.lower()


def test_the_c3_scorer_region_carries_the_sme_rulings():
    """Every dated ruling reaches the model, or the decisions doc is lying about the rubric.

    All of these live inside `scorer:start`/`scorer:end`. Putting one outside the markers
    would leave §9 and §10 saying a ruling was encoded while the scorer never saw it — the
    drift the region markers were introduced to catch.

    The last two pull against each other and both have to survive. 2026-08-06 settled that a
    colleague acting on his own is not held against the candidate; 2026-08-10 settled that it
    does not by itself reach the top band. Losing the first re-opens the F divergence at 4B;
    losing the second returns the anchor to scoring F at 5 twenty-five times out of twenty-five.
    """
    root = Path(__file__).resolve().parents[1]
    text = rubric_module.load("c3", root=root).text
    assert "past that first deflection" in text  # asking is the floor, finding out is not
    assert "not a cap on it" in text  # 2026-08-06 — the other man acting is not a demerit
    assert "One exchange does not supply two behaviours" in text  # 2026-08-10 — breadth
    assert "It does not by itself earn him the band" in text  # 2026-08-10 — and not the band


def test_the_c3_top_band_requires_more_than_one_behaviour():
    """The breadth clause is the load-bearing sentence of the 2026-08-10 correction.

    Pinned on its own because its absence is silent. Without it the anchor still reads well,
    still scores every answer, and quietly hands the top band to any single well-handled
    episode — which is exactly what it did for twenty-five consecutive runs with nothing
    looking wrong. A clause whose failure mode is a clean run needs a test.
    """
    root = Path(__file__).resolve().parents[1]
    text = rubric_module.load("c3", root=root).text
    assert "A 5 requires more than one of the behaviours listed above" in text
    # Matched on the unwrapped fragment: the sentence wraps as "this\nclause governs", and a
    # test that pins prose has to pin it as the file actually stores it.
    assert "clause governs" in text  # it outranks the anchor prose below it
