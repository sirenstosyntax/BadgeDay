"""Verification tests for the critique gate.

`recruit_scope.md` names the critique pipeline as the component where silent failure
destroys the product, for a specific reason: a critique that has quietly stopped
referencing criteria still *looks* like good feedback. Nothing about it appears wrong. So
these tests are organised around the ways a critique point can be wrong while reading
perfectly well — anchored to nothing, anchored to a clause that does not exist, quoting
words the candidate never said, handing him a script, or telling him what he is.
"""

import pytest

from app.critique.models import DraftCritique, DraftPoint, Metric
from app.critique.rubric import Clause, Rubric
from app.critique.verify import (
    MAX_FOREIGN_QUOTE_WORDS,
    Rejection,
    verify_critique,
    verify_point,
)

TRANSCRIPT = """
Yeah, so at my last job I had a guy on my crew who just wasn't keeping up. I took his
section on top of mine for about six weeks and I absorbed it. Came in early, stayed late.
I'm a team player, I don't complain.
"""


@pytest.fixture
def rubric() -> Rubric:
    return Rubric(
        criterion_id="c3",
        name="Criterion 3 — Teamwork & Interpersonal",
        text="(rubric body)",
        clauses=(
            Clause("c3.note.1", "note", "Score the cast of the story, not its adjectives"),
            Clause("c3.anchor.2", "anchor", "Qualified, and the crew is missing"),
        ),
    )


@pytest.fixture
def metrics() -> dict[str, Metric]:
    return {
        "filler_rate_per_100": Metric(
            name="filler_rate_per_100", value=7.4, display="7.4 per 100 words", band="2–6 typical"
        )
    }


def point(**overrides) -> DraftPoint:
    base = {
        "kind": "rubric",
        "source_id": "c3.anchor.2",
        "answer_quote": "I took his section on top of mine",
        "improvement": "answer",
        "observation": "The teammate never acts in this account; only you do.",
        "ask": "What did he say when you asked him about it?",
    }
    return DraftPoint(**{**base, **overrides})


# --- 1. Anchoring: the check the whole product rests on ----------------------


def test_point_citing_a_clause_the_rubric_does_not_have_is_rejected(rubric, metrics):
    result = verify_point(point(source_id="c3.anchor.9"), rubric, TRANSCRIPT, metrics)
    assert isinstance(result, Rejection)
    assert result.code == "clause_not_in_rubric"


def test_point_citing_another_criterions_clause_is_rejected(rubric, metrics):
    """Cross-criterion anchoring is the plausible failure: a real clause ID, wrong rubric."""
    result = verify_point(point(source_id="c2.anchor.3"), rubric, TRANSCRIPT, metrics)
    assert isinstance(result, Rejection)
    assert result.code == "clause_not_in_rubric"


def test_anchored_point_survives(rubric, metrics):
    result = verify_point(point(), rubric, TRANSCRIPT, metrics)
    assert not isinstance(result, Rejection)
    assert result.clause is not None
    assert result.clause.clause_id == "c3.anchor.2"


def test_measurement_point_must_cite_a_metric_that_was_measured(rubric, metrics):
    result = verify_point(
        point(kind="measurement", source_id="words_per_minute", answer_quote=None),
        rubric,
        TRANSCRIPT,
        metrics,
    )
    assert isinstance(result, Rejection)
    assert result.code == "metric_not_supplied"


def test_measurement_point_citing_a_supplied_metric_survives(rubric, metrics):
    result = verify_point(
        point(
            kind="measurement",
            source_id="filler_rate_per_100",
            answer_quote=None,
            observation="Filler runs 7.4 per 100 words, above the typical range.",
            ask=None,
        ),
        rubric,
        TRANSCRIPT,
        metrics,
    )
    assert not isinstance(result, Rejection)
    assert result.metric is not None


def test_no_metrics_supplied_means_no_measurement_points(rubric):
    result = verify_point(
        point(kind="measurement", source_id="filler_rate_per_100", answer_quote=None),
        rubric,
        TRANSCRIPT,
        {},
    )
    assert isinstance(result, Rejection)
    assert result.code == "metric_not_supplied"


# --- 2. Supplied language: the prohibition the product is built around --------


@pytest.mark.parametrize(
    "observation",
    [
        "Try saying something about what he told you.",
        "A stronger answer would be one that names what the other person did.",
        "You could say that you asked him directly.",
        "Instead, say what he contributed.",
        "Here's how to handle that: name the other person.",
    ],
)
def test_supplied_language_is_rejected(rubric, metrics, observation):
    result = verify_point(point(observation=observation), rubric, TRANSCRIPT, metrics)
    assert isinstance(result, Rejection)
    assert result.code == "supplies_language"


def test_scripted_sentence_in_quotes_is_rejected_even_without_a_giveaway_phrase(rubric, metrics):
    """The subtle form: no telltale phrase, just a sentence in quotes he never said."""
    result = verify_point(
        point(
            observation=(
                'The answer needs something like "I asked him what was going on and he told '
                'me his father was ill" to show the other person acting.'
            )
        ),
        rubric,
        TRANSCRIPT,
        metrics,
    )
    assert isinstance(result, Rejection)
    assert result.code == "supplies_language"


def test_quoting_the_candidates_own_words_is_allowed(rubric, metrics):
    result = verify_point(
        point(
            observation=(
                "You say \"I'm a team player, I don't complain\" and then describe only "
                "your own work."
            )
        ),
        rubric,
        TRANSCRIPT,
        metrics,
    )
    assert not isinstance(result, Rejection)


def test_short_quoted_rubric_terms_are_not_treated_as_supplied_language(rubric, metrics):
    result = verify_point(
        point(observation='This is what the rubric calls "a crew of one".'),
        rubric,
        TRANSCRIPT,
        metrics,
    )
    assert not isinstance(result, Rejection)
    assert len("a crew of one".split()) <= MAX_FOREIGN_QUOTE_WORDS


def test_contractions_are_not_read_as_quote_delimiters(rubric, metrics):
    """Regression: the first live run rejected sound points because of apostrophes.

    The observation below contains no quotation at all — only contractions. An earlier
    version of the gate paired the apostrophe in "he'd" with the one in "you've" and
    rejected everything between them as a scripted phrase. This domain's prose is
    conversational, so that misfire would have been constant, and each one either loses a
    good point or spends a retry.
    """
    observation = (
        "The response is built around a policy change he'd make if he had authority, not a "
        "step he has taken. Setting aside what you've learned about the department, nothing "
        "here connects to what you've actually done."
    )
    result = verify_point(point(observation=observation), rubric, TRANSCRIPT, metrics)
    assert not isinstance(result, Rejection), getattr(result, "detail", "")


def test_a_genuinely_scripted_single_quoted_sentence_is_still_caught(rubric, metrics):
    """The contraction fix must not open a hole: real single-quoted scripts still fail."""
    result = verify_point(
        point(
            observation=(
                "The answer needs 'I sat down with him and asked what was going on at home' "
                "to show the other person acting."
            )
        ),
        rubric,
        TRANSCRIPT,
        metrics,
    )
    assert isinstance(result, Rejection)
    assert result.code == "supplies_language"


# --- 3. Grounding: the point must be about something he said -----------------


def test_fabricated_quote_is_rejected(rubric, metrics):
    result = verify_point(
        point(answer_quote="I asked him what was wrong and he opened up"),
        rubric,
        TRANSCRIPT,
        metrics,
    )
    assert isinstance(result, Rejection)
    assert result.code == "quote_not_in_answer"


def test_quote_matching_survives_speech_punctuation_and_line_breaks(rubric, metrics):
    """Transcripts wrap and carry smart punctuation; a quote must not fail on typography."""
    result = verify_point(
        point(answer_quote="I took his section on top of mine\n   for about six weeks"),
        rubric,
        TRANSCRIPT,
        metrics,
    )
    assert not isinstance(result, Rejection)


def test_a_point_about_an_absence_may_omit_the_quote(rubric, metrics):
    """Most critique is about what is missing, and you cannot quote what was never said."""
    result = verify_point(
        point(
            answer_quote=None, observation="No one else takes an action anywhere in this account."
        ),
        rubric,
        TRANSCRIPT,
        metrics,
    )
    assert not isinstance(result, Rejection)


def test_blank_quote_is_rejected(rubric, metrics):
    result = verify_point(point(answer_quote="   "), rubric, TRANSCRIPT, metrics)
    assert isinstance(result, Rejection)
    assert result.code == "empty_quote"


# --- 4. Internal state: claims about the man, not the answer ------------------


@pytest.mark.parametrize(
    "observation",
    [
        "You came across as someone who does not listen.",
        "You seem uninterested in the people around you.",
        "You don't care about your crew.",
        "Your attitude towards the teammate is the problem.",
    ],
)
def test_internal_state_attribution_is_rejected(rubric, metrics, observation):
    result = verify_point(point(observation=observation), rubric, TRANSCRIPT, metrics)
    assert isinstance(result, Rejection)
    assert result.code == "attributes_internal_state"


def test_how_the_answer_reads_is_permitted(rubric, metrics):
    """The permitted form from the design decisions: about the answer, tied to a behaviour."""
    result = verify_point(
        point(
            observation=(
                "Six weeks of covering another man's section with no account of why he was "
                "struggling — that reads as a crew of one."
            )
        ),
        rubric,
        TRANSCRIPT,
        metrics,
    )
    assert not isinstance(result, Rejection)


# --- 5. Score disclosure: the number is internal -----------------------------


@pytest.mark.parametrize(
    "observation",
    [
        "You scored a 2 on this criterion.",
        "This is a level 2 answer.",
        "That puts your score at the lower end.",
        "Rated 2 out of 5 for teamwork.",
    ],
)
def test_score_disclosure_is_rejected(rubric, metrics, observation):
    result = verify_point(point(observation=observation), rubric, TRANSCRIPT, metrics)
    assert isinstance(result, Rejection)
    assert result.code == "discloses_score"


# --- Whole-critique behaviour ------------------------------------------------


def test_one_bad_point_does_not_discard_its_siblings(rubric, metrics):
    draft = DraftCritique(
        assessable=True,
        internal_score=2,
        route="n/a",
        points=[
            point(),
            point(source_id="c3.anchor.9"),
            point(observation="Try saying what he told you."),
        ],
    )
    critique, rejections = verify_critique(draft, rubric, TRANSCRIPT, metrics)
    assert len(critique.points) == 1
    assert {r.code for r in rejections} == {"clause_not_in_rubric", "supplies_language"}


def test_not_assessable_forces_the_internal_score_to_zero(rubric, metrics):
    """A not-assessable outcome must never carry a score that could be averaged in."""
    draft = DraftCritique(assessable=False, internal_score=2, route="n/a", points=[point()])
    critique, _ = verify_critique(draft, rubric, TRANSCRIPT, metrics)
    assert critique.internal_score == 0
    assert critique.assessable is False


def test_rejections_carry_enough_detail_to_regenerate_from(rubric, metrics):
    """The retry loop feeds `detail` back to the model, so it has to name the actual problem."""
    draft = DraftCritique(
        assessable=True, internal_score=2, route="n/a", points=[point(source_id="c3.anchor.9")]
    )
    _, rejections = verify_critique(draft, rubric, TRANSCRIPT, metrics)
    assert "c3.anchor.9" in rejections[0].detail


def test_spliced_quote_rejection_points_at_the_divergence(rubric, metrics):
    """The rejection text feeds the retry loop, so it must name the part that failed.

    A quote stitched from two things the candidate said separately matches perfectly for
    its opening words. An earlier message showed only those opening words, telling the
    model a passage does not appear while quoting back a passage that does.
    """
    spliced = "I took his section on top of mine and he thanked me for it afterwards"
    result = verify_point(point(answer_quote=spliced), rubric, TRANSCRIPT, metrics)
    assert isinstance(result, Rejection)
    assert result.code == "quote_not_in_answer"
    assert "i took his section on top of mine" in result.detail
    assert "thanked me" in result.detail


def test_wholly_invented_quote_says_so_plainly(rubric, metrics):
    result = verify_point(
        point(answer_quote="Nothing about this sentence was ever spoken"),
        rubric,
        TRANSCRIPT,
        metrics,
    )
    assert isinstance(result, Rejection)
    assert "does not appear in the transcript at all" in result.detail


# --- 6. Two kinds of improvement, and the guard on the expensive one ---------


def test_development_point_may_name_what_is_absent(rubric, metrics):
    """The permitted form: says what his experience lacks, leaves the route to it open."""
    result = verify_point(
        point(
            improvement="candidate",
            answer_quote=None,
            observation=(
                "Nothing in your account shows you asking someone why they were "
                "struggling. That is not something you can add to this story later."
            ),
            ask="When have you had to find out what was behind somebody's drop-off?",
        ),
        rubric,
        TRANSCRIPT,
        metrics,
    )
    assert not isinstance(result, Rejection), getattr(result, "detail", "")
    assert result.improvement == "candidate"


@pytest.mark.parametrize(
    "ask",
    [
        "Get your EMT-B and volunteer somewhere for six months.",
        "Enroll in a fire academy programme this year.",
        "You should join a volunteer department.",
        "Take a course in conflict resolution.",
        "I recommend you find a crew environment before testing again.",
    ],
)
def test_development_point_prescribing_a_remedy_is_rejected(rubric, metrics, ask):
    """Naming a gap is cheap to be wrong about; naming the cure costs him a year and a fee."""
    result = verify_point(
        point(improvement="candidate", answer_quote=None, ask=ask), rubric, TRANSCRIPT, metrics
    )
    assert isinstance(result, Rejection)
    assert result.code == "prescribes_remedy"


def test_the_prescription_guard_does_not_apply_to_answer_points(rubric, metrics):
    """An answer point telling him to name what a teammate did is not career advice."""
    result = verify_point(
        point(improvement="answer", ask="Take the story back to what he actually said."),
        rubric,
        TRANSCRIPT,
        metrics,
    )
    assert not isinstance(result, Rejection), getattr(result, "detail", "")


def test_a_critique_separates_the_two_kinds(rubric, metrics):
    draft = DraftCritique(
        assessable=True,
        internal_score=2,
        route="n/a",
        points=[
            point(improvement="none", observation="You gave a specific, dated incident."),
            point(improvement="answer", observation="The outcome never lands."),
            point(
                improvement="candidate",
                answer_quote=None,
                observation="You have never asked why somebody was falling behind.",
                ask="When have you had that conversation?",
            ),
        ],
    )
    critique, rejections = verify_critique(draft, rubric, TRANSCRIPT, metrics)
    assert not rejections
    assert len(critique.worked) == 1
    assert len(critique.answer_gaps) == 1
    assert len(critique.development_gaps) == 1
    assert critique.development_gaps[0].ask == "When have you had that conversation?"
