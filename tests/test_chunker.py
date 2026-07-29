"""Chunker tests.

The brief names the chunker as one of two components where silent failure destroys the
product. These tests target the ways it fails quietly: an outline path attached to the
wrong text, a page number that sends the candidate to the wrong page, a false heading
that fragments a section, a real heading missed so its content becomes uncitable, and
IDs that shift under re-ingestion and orphan existing citations.

Both numbering families are covered, because a chunker that only understands one leaves
whole documents citable by page number alone.
"""

from app.ingest.chunker import chunk_document, chunk_id_for
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


def _paths(chunks) -> list[list[str]]:
    return [c.section_path for c in chunks]


def _by_path(chunks) -> dict[str, object]:
    return {c.section_label: c for c in chunks}


# --- Decimal outlines --------------------------------------------------------


def test_decimal_headings_become_their_own_chunks(synthetic_sog) -> None:
    labels = {c.section_label for c in chunk_document(synthetic_sog, DOC_ID)}
    assert {"304.1", "304.2.1", "304.2.2", "304.3.1", "304.3.2"} <= labels


def test_decimal_child_is_not_swallowed_by_its_parent(synthetic_sog) -> None:
    chunks = _by_path(chunk_document(synthetic_sog, DOC_ID))
    assert "two members shall enter the hazard area" in chunks["304.2.1"].text


def test_decimal_path_has_a_single_element(synthetic_sog) -> None:
    """A decimal number states its own depth, so it needs no ancestors to be found."""
    chunk = _by_path(chunk_document(synthetic_sog, DOC_ID))["304.2.1"]
    assert chunk.section_path == ["304.2.1"]


def test_measurement_is_not_treated_as_a_decimal_heading(synthetic_sog) -> None:
    """`2.5 gallons of foam...` looks like a section number and is not one."""
    chunks = chunk_document(synthetic_sog, DOC_ID)
    assert "2.5" not in {c.section_label for c in chunks}
    assert "foam concentrate" in _by_path(chunks)["304.2.2"].text


# --- Lettered outlines -------------------------------------------------------


def test_named_headings_are_recognized_from_layout_role(synthetic_outline_sog) -> None:
    """PURPOSE and PROCEDURE carry no marker — only the sectionHeading role finds them."""
    labels = {c.section_label for c in chunk_document(synthetic_outline_sog, DOC_ID)}
    assert "PURPOSE" in labels
    assert any(label.startswith("PROCEDURE") for label in labels)


def test_ordinal_markers_nest_under_their_named_heading(synthetic_outline_sog) -> None:
    paths = _paths(chunk_document(synthetic_outline_sog, DOC_ID))
    assert ["PROCEDURE", "A"] in paths
    assert ["PROCEDURE", "C", "3"] in paths


BODY = " ".join(["Every company officer shall verify this assignment on arrival."] * 3)


def _deep_doc() -> AnalyzedDocument:
    """Four levels, each item substantial enough to be cited on its own.

    Lists open at A / 1 / a / i, which is what real outlines do — and what the sequence
    guard requires, since a list appearing to start at `C` is more often prose.
    """
    return _doc(
        ("PROCEDURE", 1, "sectionHeading"),
        (f"A. Supply responsibilities are assigned as follows. {BODY}", 1),
        (f"1. Relay Operations shall be established as follows. {BODY}", 1),
        (f"a. The Water Supply Officer shall confirm the following. {BODY}", 1),
        (f"i. The total length of hose and the elevation change. {BODY}", 1),
        (f"ii. The rated capacity of every pump in the relay. {BODY}", 1),
    )


def test_depth_is_inferred_from_the_order_styles_appear() -> None:
    """A. then 1. then a. then i. — the marker says position, the order says depth."""
    labels = {c.section_label for c in chunk_document(_deep_doc(), DOC_ID)}
    assert "PROCEDURE A.1.a" in labels


def test_full_path_is_kept_so_a_deep_item_can_be_found() -> None:
    """Item `c` alone is meaningless; PROCEDURE C.3.c can be looked up."""
    chunk = _by_path(chunk_document(_deep_doc(), DOC_ID))["PROCEDURE A.1.a"]
    assert chunk.section_path == ["PROCEDURE", "A", "1", "a"]


def test_roman_sub_items_nest_under_their_letter() -> None:
    """`i.` after `c.` opens a nested roman list rather than continuing the letters."""
    labels = {c.section_label for c in chunk_document(_deep_doc(), DOC_ID)}
    assert "PROCEDURE A.1.a.ii" in labels


def test_thin_sub_items_merge_into_the_section_a_reader_would_look_up(
    synthetic_outline_sog,
) -> None:
    """One-line list items are reachable through their parent, not stranded alone."""
    chunk = _by_path(chunk_document(synthetic_outline_sog, DOC_ID))["PROCEDURE C.3"]
    assert "rated capacity of every pump" in chunk.text
    assert "intake pressure" in chunk.text.lower()


def test_roman_after_h_continues_the_lettered_list() -> None:
    """`i.` is both a numeral and the ninth letter. After `h.` it is the letter."""
    letters = "abcdefghi"
    doc = _doc(
        ("PROCEDURE", 1, "sectionHeading"),
        *[
            (f"{ch}. Requirement number {n} of the sequence. {BODY}", 1)
            for n, ch in enumerate(letters, start=1)
        ],
    )
    paths = _paths(chunk_document(doc, DOC_ID))
    assert ["PROCEDURE", "i"] in paths
    assert ["PROCEDURE", "h", "i"] not in paths


# --- False headings ----------------------------------------------------------


def test_all_caps_diagram_labels_do_not_become_sections(synthetic_outline_sog) -> None:
    """An org chart's labels look exactly like headings. Only the role tagging knows."""
    labels = {c.section_label for c in chunk_document(synthetic_outline_sog, DOC_ID)}
    assert "COMMAND" not in labels
    assert "HYDRANT" not in labels


def test_a_number_mid_list_that_breaks_sequence_is_not_a_heading() -> None:
    """A marker must open a list or continue one; prose starting with a digit does neither."""
    doc = _doc(
        ("PROCEDURE", 1, "sectionHeading"),
        (f"1. First item of the list. {BODY}", 1),
        (f"7. This sentence merely begins with a number and continues no sequence. {BODY}", 1),
    )
    paths = _paths(chunk_document(doc, DOC_ID))
    assert ["PROCEDURE", "1"] in paths
    assert ["PROCEDURE", "7"] not in paths


def test_a_list_that_continues_in_sequence_is_kept() -> None:
    doc = _doc(
        ("PROCEDURE", 1, "sectionHeading"),
        (f"1. First item of the list. {BODY}", 1),
        (f"2. Second item of the list. {BODY}", 1),
        (f"3. Third item of the list. {BODY}", 1),
    )
    paths = _paths(chunk_document(doc, DOC_ID))
    assert ["PROCEDURE", "1"] in paths
    assert ["PROCEDURE", "3"] in paths


def test_unroled_capitals_before_any_heading_stay_in_the_preamble(
    synthetic_outline_sog,
) -> None:
    first = chunk_document(synthetic_outline_sog, DOC_ID)[0]
    assert first.kind == "semantic"
    assert first.section_path == []
    assert "EXAMPLE COUNTY FIRE CHIEFS ASSOCIATION" in first.text


# --- Subtree merging ---------------------------------------------------------


def test_short_subtree_is_emitted_whole_under_its_own_heading() -> None:
    """Sub-items too thin to question alone must not be stranded from their parent."""
    doc = _doc(
        ("PROCEDURE", 1, "sectionHeading"),
        ("1. Water Supply shall be established by the third arriving company.", 1),
        ("a. Supplementing the sprinkler system;", 1),
        ("b. Supplementing the standpipe system;", 1),
    )
    chunks = chunk_document(doc, DOC_ID, max_chars=1800)
    parent = _by_path(chunks)["PROCEDURE 1"]
    assert "sprinkler system" in parent.text
    assert "standpipe system" in parent.text
    assert "PROCEDURE 1.a" not in {c.section_label for c in chunks}


def test_oversized_subtree_splits_into_its_children() -> None:
    doc = _doc(
        ("PROCEDURE", 1, "sectionHeading"),
        ("1. Water Supply shall be established by the third arriving company.", 1),
        ("a. " + "x" * 900, 1),
        ("b. " + "y" * 900, 1),
    )
    labels = {c.section_label for c in chunk_document(doc, DOC_ID, max_chars=800)}
    assert "PROCEDURE 1.a" in labels
    assert "PROCEDURE 1.b" in labels


def test_no_content_is_lost_when_a_subtree_splits() -> None:
    doc = _doc(
        ("PROCEDURE", 1, "sectionHeading"),
        ("1. Water Supply shall be established by the third arriving company.", 1),
        ("a. " + "x" * 900, 1),
        ("b. " + "y" * 900, 1),
    )
    combined = "\n".join(c.text for c in chunk_document(doc, DOC_ID, max_chars=800))
    assert "x" * 900 in combined
    assert "y" * 900 in combined
    assert "Water Supply shall be established" in combined


# --- Page location -----------------------------------------------------------


def test_section_spanning_a_page_break_reports_both_pages(synthetic_sog) -> None:
    """Reporting only the heading's page would send the candidate to the wrong page."""
    chunk = _by_path(chunk_document(synthetic_sog, DOC_ID))["304.2.1"]
    assert (chunk.page_start, chunk.page_end) == (1, 2)


def test_location_renders_path_and_pages(synthetic_outline_sog) -> None:
    chunk = _by_path(chunk_document(synthetic_outline_sog, DOC_ID))["PROCEDURE C.3"]
    assert chunk.location() == "PROCEDURE C.3, p. 2"


def test_location_without_a_path_is_just_the_page(synthetic_outline_sog) -> None:
    assert chunk_document(synthetic_outline_sog, DOC_ID)[0].location() == "p. 1"


# --- Page furniture ----------------------------------------------------------


def test_page_furniture_is_dropped(synthetic_outline_sog) -> None:
    combined = "\n".join(c.text for c in chunk_document(synthetic_outline_sog, DOC_ID))
    assert "Page 2 of 2" not in combined
    assert "EXAMPLE COUNTY SOG - WATER SUPPLY" not in combined


def test_footer_does_not_interrupt_a_section_spanning_pages(synthetic_sog) -> None:
    chunk = _by_path(chunk_document(synthetic_sog, DOC_ID))["304.2.1"]
    assert "voice or visual contact" in chunk.text
    assert "charged hoseline" in chunk.text
    assert "SOG 304" not in chunk.text


def test_unroled_blocks_are_always_kept() -> None:
    """Only explicit furniture roles are dropped — never text merely resembling it."""
    doc = _doc(
        ("PROCEDURE", 1, "sectionHeading"),
        ("Page 1 of the pre-incident plan shall be posted at the entrance.", 1),
    )
    assert "pre-incident plan" in chunk_document(doc, DOC_ID)[0].text


# --- Ordering and identity ---------------------------------------------------


def test_chunks_are_in_reading_order(synthetic_outline_sog) -> None:
    chunks = chunk_document(synthetic_outline_sog, DOC_ID)
    assert [c.ordinal for c in chunks] == list(range(len(chunks)))


def test_chunk_ids_are_stable_across_runs(synthetic_outline_sog) -> None:
    """Citations store chunk_id. Re-ingestion must not orphan them."""
    first = [c.chunk_id for c in chunk_document(synthetic_outline_sog, DOC_ID)]
    second = [c.chunk_id for c in chunk_document(synthetic_outline_sog, DOC_ID)]
    assert first == second


def test_chunk_ids_differ_between_documents() -> None:
    assert chunk_id_for("doc-a", 0) != chunk_id_for("doc-b", 0)


def test_empty_document_yields_no_chunks() -> None:
    doc = AnalyzedDocument(source_name="empty.pdf", page_count=1, blocks=[])
    assert chunk_document(doc, DOC_ID) == []


def test_document_without_structure_is_entirely_semantic() -> None:
    doc = _doc(
        ("Recruit orientation handout for the spring hiring process.", 1),
        ("Report to the training division at 0700 in station uniform.", 1),
    )
    chunks = chunk_document(doc, DOC_ID)
    assert all(c.kind == "semantic" for c in chunks)
    assert all(c.section_path == [] for c in chunks)


# --- Figure text -------------------------------------------------------------


def test_figure_text_is_dropped() -> None:
    """An org chart's box labels are not guideline content."""
    doc = _doc(
        ("A. Command shall be established by the first arriving officer.", 1),
        ("Figure 1: High-Rise Alarm Assignments", 2, "figure"),
        ("COMMAND BATTALION CHIEF", 2, "figure"),
        ("WATER SUPPLY 3RD ENGINE", 2, "figure"),
    )
    text = " ".join(c.text for c in chunk_document(doc, DOC_ID))
    assert "Command shall be established" in text
    assert "BATTALION CHIEF" not in text
    assert "WATER SUPPLY" not in text


def test_figure_text_does_not_attach_to_the_preceding_section() -> None:
    """The real failure: diagram text absorbed into the last section before it.

    A question drawn from those fragments would cite that section, and the citation
    would resolve — the chunk really would contain the text — so verification passes
    while the candidate is sent to a section about something else.
    """
    doc = _doc(
        ("PROCEDURE", 1, "sectionHeading"),
        ("A. Companies shall carry standpipe equipment into the building.", 1),
        ("B. Air replenishment systems are found in stairwells.", 1),
        ("LOBBY CONTROL 4TH ENGINE", 2, "figure"),
        ("RECON GROUP 2ND AERIAL", 2, "figure"),
    )
    chunks = chunk_document(doc, DOC_ID)
    holding_the_prose = [c for c in chunks if "Air replenishment" in c.text]
    assert holding_the_prose, "the guideline text itself must survive"
    for chunk in holding_the_prose:
        assert "LOBBY CONTROL" not in chunk.text
        assert "RECON GROUP" not in chunk.text


def test_figure_label_shaped_like_a_heading_does_not_open_a_section() -> None:
    """`COMMAND` in a chart box must not become a citable location."""
    doc = _doc(
        ("A. Units arriving shall assume pre-assigned responsibilities.", 1),
        ("COMMAND", 2, "figure"),
        ("SAFETY", 2, "figure"),
        ("LOGISTICS", 2, "figure"),
    )
    labels = {c.section_label for c in chunk_document(doc, DOC_ID)}
    assert not {"COMMAND", "SAFETY", "LOGISTICS"} & labels
