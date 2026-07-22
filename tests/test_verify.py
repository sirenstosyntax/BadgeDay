"""Verification tests.

The citation resolver is the second component the brief names as fatal on silent
failure. These tests are organised around the ways a question can be wrong while looking
right: ungrounded but confidently cited, correctly cited but copied verbatim, or
structurally broken in a way a candidate only discovers mid-quiz.
"""

import pytest

from app.generate.models import (
    Citation,
    DraftMultipleChoice,
    DraftShortAnswer,
    DraftTrueFalse,
)
from app.generate.verify import (
    MAX_QUOTE_CHARS,
    Rejection,
    is_generatable,
    longest_shared_run,
    verify_batch,
    verify_draft,
)
from app.ingest.models import Chunk

SOURCE = (
    "304.2.1 Interior Operations\n"
    "A minimum of two members shall enter the hazard area together and shall remain in "
    "voice or visual contact at all times.\n"
    "A charged hoseline shall be in place before the interior attack team advances past "
    "the entry point."
)


@pytest.fixture
def chunk() -> Chunk:
    return Chunk(
        chunk_id="chunk-1",
        document_id="doc-1",
        ordinal=3,
        kind="outline",
        section_number="304.2.1",
        section_title="Interior Operations",
        page_start=1,
        page_end=2,
        text=SOURCE,
    )


def _mc(**overrides) -> DraftMultipleChoice:
    defaults = {
        "type": "multiple_choice",
        "stem": "How many members must enter a hazard area together?",
        "options": ["One", "Two", "Three", "Four"],
        "correct_index": 1,
        "source_quote": "a minimum of two members shall enter the hazard area together",
        "explanation": "The guideline sets a two-member minimum for entry.",
    }
    return DraftMultipleChoice.model_validate({**defaults, **overrides})


def _verified(draft, chunk):
    result = verify_draft(draft, chunk)
    assert not isinstance(result, Rejection), getattr(result, "detail", result)
    return result


# --- Grounding ---------------------------------------------------------------


def test_quote_present_in_source_is_accepted(chunk) -> None:
    assert _verified(_mc(), chunk).type == "multiple_choice"


def test_invented_quote_is_rejected(chunk) -> None:
    """A model that fabricates its supporting passage must not get a citation."""
    draft = _mc(source_quote="a minimum of three members shall enter the hazard area")
    result = verify_draft(draft, chunk)
    assert isinstance(result, Rejection)
    assert result.code == "quote_not_in_source"


def test_paraphrased_quote_is_rejected(chunk) -> None:
    """Close is not the same as present. Paraphrase defeats the grounding proof."""
    draft = _mc(source_quote="at least two firefighters must enter the hazard zone as a pair")
    assert isinstance(verify_draft(draft, chunk), Rejection)


def test_quote_matching_survives_line_breaks_and_case(chunk) -> None:
    """The quote spans a newline in the source; normalization must see through it."""
    draft = _mc(
        stem="What must be in place before the attack team moves inside?",
        source_quote="ALL TIMES. A charged hoseline shall be in place",
        options=["A charged hoseline", "A ladder", "A fan", "A saw"],
        correct_index=0,
    )
    assert _verified(draft, chunk).citation.section_number == "304.2.1"


# --- Copyright ---------------------------------------------------------------


def test_overlong_quote_is_rejected(chunk) -> None:
    draft = _mc(source_quote=SOURCE.replace("\n", " ")[: MAX_QUOTE_CHARS + 20])
    result = verify_draft(draft, chunk)
    assert isinstance(result, Rejection)
    assert result.code == "quote_too_long"


def test_stem_copied_verbatim_is_rejected(chunk) -> None:
    """A true/false stem lifted from the source reproduces the text it should cite."""
    draft = DraftTrueFalse.model_validate(
        {
            "type": "true_false",
            "stem": (
                "A charged hoseline shall be in place before the interior attack team "
                "advances past the entry point."
            ),
            "correct_answer": True,
            "source_quote": "A charged hoseline shall be in place",
            "explanation": "The guideline requires it.",
        }
    )
    result = verify_draft(draft, chunk)
    assert isinstance(result, Rejection)
    assert result.code == "stem_reproduces_source"


def test_reworded_true_false_stem_is_accepted(chunk) -> None:
    draft = DraftTrueFalse.model_validate(
        {
            "type": "true_false",
            "stem": "Crews may advance inside before their hoseline is charged.",
            "correct_answer": False,
            "source_quote": "A charged hoseline shall be in place",
            "explanation": "The hoseline must be charged first.",
        }
    )
    assert _verified(draft, chunk).correct_answer is False


def test_shared_run_measures_consecutive_words_only() -> None:
    assert longest_shared_run("two members shall enter", "two members shall enter") == 4
    assert longest_shared_run("two members shall enter", "members two enter shall") == 1
    assert longest_shared_run("nothing alike", "completely different") == 0


# --- Structural validity -----------------------------------------------------


def test_correct_index_out_of_range_is_rejected(chunk) -> None:
    result = verify_draft(_mc(correct_index=9), chunk)
    assert isinstance(result, Rejection)
    assert result.code == "correct_index_out_of_range"


def test_duplicate_options_are_rejected(chunk) -> None:
    """Two identical options mean two correct answers, or none."""
    result = verify_draft(_mc(options=["Two", "Two", "Three", "Four"]), chunk)
    assert isinstance(result, Rejection)
    assert result.code == "duplicate_options"


def test_blank_option_is_rejected(chunk) -> None:
    result = verify_draft(_mc(options=["Two", "   ", "Three", "Four"]), chunk)
    assert isinstance(result, Rejection)
    assert result.code == "empty_option"


def test_short_answer_needs_a_usable_model_answer(chunk) -> None:
    draft = DraftShortAnswer.model_validate(
        {
            "type": "short_answer",
            "stem": "What is the minimum crew size for entering a hazard area?",
            "model_answer": "Two.",
            "source_quote": "a minimum of two members shall enter the hazard area",
            "explanation": "Two members minimum.",
        }
    )
    result = verify_draft(draft, chunk)
    assert isinstance(result, Rejection)
    assert result.code == "model_answer_too_short"


def test_trivial_stem_is_rejected(chunk) -> None:
    result = verify_draft(_mc(stem="How many?"), chunk)
    assert isinstance(result, Rejection)
    assert result.code == "stem_too_short"


# --- Citation construction ---------------------------------------------------


def test_citation_is_built_from_the_chunk_not_the_model(chunk) -> None:
    """The model never authors a citation, so it cannot point one somewhere wrong."""
    citation = _verified(_mc(), chunk).citation
    assert citation.chunk_id == "chunk-1"
    assert citation.document_id == "doc-1"
    assert citation.section_number == "304.2.1"
    assert (citation.page_start, citation.page_end) == (1, 2)


def test_citation_display_includes_section_and_page_range(chunk) -> None:
    assert _verified(_mc(), chunk).citation.display() == "§ 304.2.1 Interior Operations, pp. 1–2"


def test_citation_display_for_unnumbered_source() -> None:
    citation = Citation(
        document_id="d",
        chunk_id="c",
        section_number=None,
        section_title=None,
        page_start=4,
        page_end=4,
    )
    assert citation.display() == "p. 4"


def test_source_quote_is_not_carried_into_the_stored_question(chunk) -> None:
    """The quote proves grounding, then must disappear — storing it stores source text."""
    question = _verified(_mc(), chunk)
    assert "source_quote" not in question.model_dump()
    assert "a minimum of two members" not in question.model_dump_json()


# --- Batch behaviour ---------------------------------------------------------


def test_batch_keeps_good_drafts_and_reports_bad_ones(chunk) -> None:
    """Fewer questions is the prescribed response to failure — not zero, and not bad ones."""
    drafts = [_mc(), _mc(source_quote="invented text not in the section"), _mc(correct_index=7)]
    questions, rejections = verify_batch(drafts, chunk)
    assert len(questions) == 1
    assert {r.code for r in rejections} == {"quote_not_in_source", "correct_index_out_of_range"}


def test_empty_batch_is_not_an_error(chunk) -> None:
    assert verify_batch([], chunk) == ([], [])


# --- Chunk eligibility -------------------------------------------------------


def test_container_heading_chunk_is_not_generatable() -> None:
    """`304.3 Responsibilities` has no substance of its own — its children hold it all."""
    chunk = Chunk(
        chunk_id="c",
        document_id="d",
        ordinal=5,
        kind="outline",
        section_number="304.3",
        section_title="Responsibilities",
        page_start=2,
        page_end=2,
        text="304.3 Responsibilities",
    )
    assert not is_generatable(chunk)


def test_substantive_chunk_is_generatable(chunk) -> None:
    assert is_generatable(chunk)


def test_very_short_chunk_is_not_generatable() -> None:
    chunk = Chunk(
        chunk_id="c",
        document_id="d",
        ordinal=9,
        kind="semantic",
        page_start=2,
        page_end=2,
        text="Revised: January 2026",
    )
    assert not is_generatable(chunk)
