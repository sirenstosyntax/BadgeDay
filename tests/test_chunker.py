"""Chunker tests.

The brief names the chunker as one of two components where silent failure destroys the
product, so these tests target the specific ways it can fail quietly: a section number
attached to the wrong text, a page number that sends the candidate to the wrong page, a
false-positive heading that fragments a section, and IDs that shift under re-ingestion
and orphan existing citations.
"""

from app.ingest.chunker import (
    _is_plausible_successor,
    chunk_document,
    chunk_id_for,
)
from app.ingest.models import AnalyzedBlock, AnalyzedDocument

DOC_ID = "doc-1"


def _doc(*blocks: tuple[str, int] | tuple[str, int, str]) -> AnalyzedDocument:
    """Build a document from (text, page) or (text, page, role) tuples."""
    return AnalyzedDocument(
        source_name="t.pdf",
        page_count=max(b[1] for b in blocks),
        blocks=[
            AnalyzedBlock(text=b[0], page=b[1], role=b[2] if len(b) > 2 else None) for b in blocks
        ],
    )


def _by_section(chunks: list) -> dict[str | None, object]:
    return {chunk.section_number: chunk for chunk in chunks}


# --- Outline structure -------------------------------------------------------


def test_every_numbered_heading_becomes_its_own_chunk(synthetic_sog) -> None:
    sections = {c.section_number for c in chunk_document(synthetic_sog, DOC_ID)}
    assert {"304.1", "304.2", "304.2.1", "304.2.2", "304.3", "304.3.1", "304.3.2"} <= sections


def test_child_section_is_not_swallowed_by_its_parent(synthetic_sog) -> None:
    """304.2.1 must be citable on its own, not folded into 304.2."""
    chunks = _by_section(chunk_document(synthetic_sog, DOC_ID))
    assert "two members shall enter the hazard area" in chunks["304.2.1"].text
    assert "two members shall enter the hazard area" not in chunks["304.2"].text


def test_section_title_is_captured(synthetic_sog) -> None:
    chunks = _by_section(chunk_document(synthetic_sog, DOC_ID))
    assert chunks["304.2.1"].section_title == "Interior Operations"
    assert chunks["304.3.1"].section_title == "Company Officer"


def test_body_text_stays_with_its_heading(synthetic_sog) -> None:
    """Trailing prose after the last heading belongs to that heading, not to a new chunk."""
    chunks = _by_section(chunk_document(synthetic_sog, DOC_ID))
    assert "unsafe condition" in chunks["304.3.2"].text


def test_chunks_are_in_reading_order(synthetic_sog) -> None:
    chunks = chunk_document(synthetic_sog, DOC_ID)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


# --- Page location -----------------------------------------------------------


def test_section_spanning_a_page_break_reports_both_pages(synthetic_sog) -> None:
    """Reporting only the heading's page would send the candidate to the wrong page."""
    chunk = _by_section(chunk_document(synthetic_sog, DOC_ID))["304.2.1"]
    assert (chunk.page_start, chunk.page_end) == (1, 2)


def test_single_page_section_reports_one_page(synthetic_sog) -> None:
    chunk = _by_section(chunk_document(synthetic_sog, DOC_ID))["304.1"]
    assert (chunk.page_start, chunk.page_end) == (1, 1)


# --- False-positive headings -------------------------------------------------


def test_measurement_is_not_treated_as_a_heading(synthetic_sog) -> None:
    """`2.5 gallons of foam…` looks like a section number and is not one."""
    chunks = chunk_document(synthetic_sog, DOC_ID)
    assert "2.5" not in {c.section_number for c in chunks}
    assert "foam concentrate" in _by_section(chunks)["304.2.2"].text


def test_capitalized_measurement_is_rejected_by_succession() -> None:
    """Shape and capitalization both pass here; only the outline rule catches it."""
    doc = _doc(
        ("304.2 Scope", 1),
        ("3.5 Inch Supply Line shall be used for all master stream operations.", 1),
    )
    chunks = chunk_document(doc, DOC_ID)
    assert len(chunks) == 1
    assert chunks[0].section_number == "304.2"


def test_long_sentence_shaped_like_a_heading_is_rejected() -> None:
    doc = _doc(
        ("304.2 Scope", 1),
        (
            "304.9 Members shall ensure that every appliance carried on the apparatus is "
            "inspected and returned to service before the end of the shift.",
            1,
        ),
    )
    assert len(chunk_document(doc, DOC_ID)) == 1


def test_bare_integer_is_not_a_heading() -> None:
    doc = _doc(("304 Structural Fire Attack", 1), ("Body text.", 1))
    chunks = chunk_document(doc, DOC_ID)
    assert chunks[0].kind == "semantic"
    assert chunks[0].section_number is None


# --- Page furniture ----------------------------------------------------------


def test_page_footer_is_dropped(synthetic_sog) -> None:
    """A running footer must not reach the generator.

    It is well-cited, factually present in the document, and worthless as a question —
    exactly the kind of content the citation rule cannot protect against.
    """
    combined = "\n".join(c.text for c in chunk_document(synthetic_sog, DOC_ID))
    assert "Page 1 of 2" not in combined
    assert "Page 2 of 2" not in combined


def test_footer_does_not_interrupt_a_section_spanning_pages(synthetic_sog) -> None:
    """The footer sat between two sentences of 304.2.1. Both must survive, adjacent."""
    chunk = _by_section(chunk_document(synthetic_sog, DOC_ID))["304.2.1"]
    assert "voice or visual contact" in chunk.text
    assert "charged hoseline" in chunk.text
    assert "SOG 304" not in chunk.text


def test_page_header_and_number_roles_are_dropped() -> None:
    doc = _doc(
        ("EXAMPLE FIRE DEPARTMENT SOG 304", 1, "pageHeader"),
        ("304.2 Scope", 1),
        ("This applies to all personnel.", 1),
        ("14", 1, "pageNumber"),
    )
    chunks = chunk_document(doc, DOC_ID)
    assert len(chunks) == 1
    assert chunks[0].section_number == "304.2"
    assert chunks[0].text == "304.2 Scope\nThis applies to all personnel."


def test_unroled_blocks_are_always_kept() -> None:
    """Only explicit furniture roles are dropped — never text merely resembling it."""
    doc = _doc(("304.2 Scope", 1), ("Page 1 of the pre-incident plan shall be posted.", 1))
    assert "Page 1 of the pre-incident plan" in chunk_document(doc, DOC_ID)[0].text


# --- Succession rule ---------------------------------------------------------


def test_succession_accepts_descendants_and_siblings() -> None:
    assert _is_plausible_successor((304, 2, 1), (304, 2))
    assert _is_plausible_successor((304, 3), (304, 2, 2))
    assert _is_plausible_successor((305,), (304, 9))
    assert _is_plausible_successor((1,), None)


def test_succession_rejects_repeats_and_backward_moves() -> None:
    assert not _is_plausible_successor((304, 2), (304, 2))
    assert not _is_plausible_successor((304, 1), (304, 2))
    assert not _is_plausible_successor((2, 5), (304, 2, 2))
    assert not _is_plausible_successor((304, 2), (304, 2, 1))


# --- Semantic fallback -------------------------------------------------------


def test_preamble_becomes_a_semantic_chunk(synthetic_sog) -> None:
    first = chunk_document(synthetic_sog, DOC_ID)[0]
    assert first.kind == "semantic"
    assert first.section_number is None
    assert "EXAMPLE FIRE DEPARTMENT" in first.text


def test_document_without_numbering_is_entirely_semantic() -> None:
    doc = _doc(
        ("Recruit orientation handout", 1),
        ("Report to the training division at 0700.", 1),
    )
    chunks = chunk_document(doc, DOC_ID)
    assert all(c.kind == "semantic" for c in chunks)
    assert all(c.section_number is None for c in chunks)


# --- Size splitting ----------------------------------------------------------


def test_oversized_section_splits_but_keeps_its_section_number() -> None:
    """A long section must still cite as that section, in every piece."""
    body = [(f"Sentence number {i} of the requirement.", 1) for i in range(40)]
    doc = _doc(("304.2 Scope", 1), *body)
    chunks = chunk_document(doc, DOC_ID, max_chars=200)
    assert len(chunks) > 1
    assert all(c.section_number == "304.2" for c in chunks)
    assert all(c.kind == "outline" for c in chunks)


def test_split_preserves_every_block() -> None:
    body = [(f"Line {i}.", 1) for i in range(30)]
    doc = _doc(("304.2 Scope", 1), *body)
    chunks = chunk_document(doc, DOC_ID, max_chars=100)
    combined = "\n".join(c.text for c in chunks)
    for i in range(30):
        assert f"Line {i}." in combined


def test_single_long_block_is_never_split() -> None:
    doc = _doc(("304.2 Scope", 1), ("x" * 5000, 1))
    chunks = chunk_document(doc, DOC_ID, max_chars=200)
    assert any("x" * 5000 in c.text for c in chunks)


# --- Identity ----------------------------------------------------------------


def test_chunk_ids_are_stable_across_runs(synthetic_sog) -> None:
    """Citations store chunk_id. Re-ingestion must not orphan them."""
    first = [c.chunk_id for c in chunk_document(synthetic_sog, DOC_ID)]
    second = [c.chunk_id for c in chunk_document(synthetic_sog, DOC_ID)]
    assert first == second


def test_chunk_ids_differ_between_documents() -> None:
    assert chunk_id_for("doc-a", 0) != chunk_id_for("doc-b", 0)


def test_empty_document_yields_no_chunks() -> None:
    doc = AnalyzedDocument(source_name="empty.pdf", page_count=1, blocks=[])
    assert chunk_document(doc, DOC_ID) == []
