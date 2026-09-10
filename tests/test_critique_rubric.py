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

    # C2 still splits level 4 into route tags. C3 dropped them (Grant 2026-09-10):
    # clean 1–5; two-axes diagnosis is critique prose only.
    if criterion_id == "c2":
        assert {f"{criterion_id}.anchor.4A", f"{criterion_id}.anchor.4B"} <= ids
    else:
        assert f"{criterion_id}.anchor.4A" not in ids
        assert f"{criterion_id}.anchor.4B" not in ids

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
    assert "does not move the band by itself" in text  # 2026-09-10 — note 5 critique-only
    assert "change the situation" in text  # 2026-09-10 — 4 vs 3 named other
    assert "there are no route tags" in text  # 2026-09-10 — clean 1–5
    assert "Being changed by a named colleague clears this clause on its own" in text


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


# --- The review exercise's two score records -------------------------------


def test_the_blind_scores_and_the_revisions_stay_separate():
    """A revised ruling must never overwrite the blind one.

    The blind block is evidence *because* it was given with no rubric in view. This test is
    the guard against the tempting shortcut — editing `F = 5` to `F = 4` so the comparison
    reads cleanly — which spends the exercise's only real property to save a line of parsing.
    """
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "review_compare", root / "scripts" / "recruit_review_compare.py"
    )
    compare = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compare)

    text = (root / "reviews" / "c3-scoring-exercise.md").read_text()
    blind = compare.parse_scores(text)
    revised = compare.parse_revisions(text)

    # F was scored 5 blind on 2026-07-29 and re-read as a strong 4 on 2026-08-10. Both
    # records survive; the comparison uses the second.
    assert blind["F"][0] == "5", "the blind score was edited — that record is not editable"
    assert revised["F"][0] == "4"
    assert {**blind, **revised}["F"][0] == "4"

    # Every revision names a ref that was actually scored blind, or it is a typo that would
    # silently add a twelfth answer to the set.
    assert set(revised) <= set(blind)


def test_a_revised_4_agrees_with_either_route_and_diverges_from_5():
    """The rerun's whole question, pinned: does F come back inside band 4 or still at 5?

    `pipeline_verdict` reports a routed 4 as the lowercase tag, so a bare revised `4` has to
    agree with `4a` and `4b` and disagree with `5`. Getting this wrong makes the intended
    result print as a divergence, which is what the revisions block exists to prevent.
    """
    import importlib.util

    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location(
        "review_compare", root / "scripts" / "recruit_review_compare.py"
    )
    compare = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(compare)

    assert compare.agrees("4", "4a")
    assert compare.agrees("4", "4b")
    assert compare.agrees("4", "4")
    assert not compare.agrees("4", "5")
    assert not compare.agrees("4", "3")


def test_the_breadth_clause_does_not_close_the_being_changed_route():
    """The defect the first set re-run found, pinned so the clause cannot re-close it.

    The breadth clause claims precedence over everything below it in anchor 5. "Being changed
    by a named colleague" is named four paragraphs down and not in the clause's list, so the
    first version of the clause silently demoted a pre-existing route to 5 into nothing — and
    answer I, the fixture written to test that exact route, came back 4B against an SME 5.

    Both halves are asserted because either alone is insufficient: the clause has to say the
    route clears it, and the route has to say the clause does not close it. A reader arriving
    at one without the other gets the wrong answer.
    """
    root = Path(__file__).resolve().parents[1]
    text = rubric_module.load("c3", root=root).text
    assert "Being changed by a named colleague clears this clause on its own" in text
    assert "the breadth clause above does not close it" in text


def test_the_untied_routes_to_the_second_behaviour_survive():
    """Found by the n=20 run on answer E, where the clause split its own readers.

    The breadth clause offers three ways to supply the second behaviour; two of them are not
    tied to a named occasion. The neighbouring sentence — "one exchange does not supply two
    behaviours" — was being generalised into "only incidents count", which reads routes 2 and
    3 straight out of the clause. One run rejected *"that's how it works"* on exactly those
    grounds while others counted it, and both readings were available in the text.
    """
    root = Path(__file__).resolve().parents[1]
    text = rubric_module.load("c3", root=root).text
    assert "Routes 2 and 3 are not tied to a named occasion" in text
    assert "only incidents count" in text  # the misreading, named so it stays named


def test_a_disposition_that_restates_the_incident_is_not_a_second_behaviour():
    """SME ruling 2026-08-10, narrowing route 2 — and the guard against it eating route 2.

    The ruling and the fix directly above it pull in opposite directions and both have to
    survive, which is the trap this anchor fell into four times in a day. The untied rule
    says a disposition counts with no occasion attached; the restatement rule says it counts
    only when it names conduct the incident did not. Lose the first and route 2 closes,
    demoting answers on grounds the ruling explicitly did not endorse. Lose the second and E
    returns to 95% at the top band against a revised 4.

    The reconciling sentence is pinned too, because a reader who meets either rule without it
    reaches for the wrong axis: the test is what the disposition is *about*, never whether it
    is tied to a date.
    """
    root = Path(__file__).resolve().parents[1]
    text = rubric_module.load("c3", root=root).text
    assert "A disposition that only restates the incident is not a second behaviour" in text
    # The operational test, not just the principle — the clause has to be applicable.
    assert "remove the incident from the answer" in text.lower()
    # Matched on the unwrapped fragment: the sentence wraps as "for being\nuntied", and a
    # test that pins prose has to pin it as the file actually stores it.
    assert "Do not demote an untied disposition for being" in text
