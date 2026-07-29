"""Marker recognition.

An unrecognized marker does not fail loudly — the item folds into its predecessor and
every citation beneath it coarsens without anything looking wrong. A *falsely* recognized
one is worse: it manufactures a section out of prose and puts a citable location where no
location exists. These tests hold both edges, with most of the weight on the second.
"""

from app.ingest.outline import MarkerStyle, parse_marker

# --- Ordinary markers --------------------------------------------------------


def test_each_ordinal_family_is_recognized() -> None:
    cases = [
        ("A. All Fireground Operations use NIMS.", MarkerStyle.UPPER_ALPHA, "A"),
        ("6. Lobby Control Unit shall be established.", MarkerStyle.ARABIC, "6"),
        ("d. Determining readiness of the fire pump:", MarkerStyle.LOWER_ALPHA, "d"),
        ("vii. Establish communication with building personnel.", MarkerStyle.LOWER_ROMAN, "vii"),
    ]
    for text, style, label in cases:
        marker = parse_marker(text)
        assert marker is not None, text
        assert (marker.style, marker.label) == (style, label)


def test_decimal_is_recognized() -> None:
    marker = parse_marker("304.2.1 Interior Operations")
    assert marker is not None
    assert (marker.style, marker.label) == (MarkerStyle.DECIMAL, "304.2.1")


def test_a_named_heading_needs_its_layout_role() -> None:
    """Shape alone cannot tell a heading from a diagram label."""
    assert parse_marker("PURPOSE") is None
    assert parse_marker("PURPOSE", role="sectionHeading") is not None


# --- A marker that lost its space --------------------------------------------


def test_a_marker_without_its_space_is_still_a_marker() -> None:
    """Verbatim from the reference SOG, where the source document has the typo."""
    marker = parse_marker(
        "ii.Fire personnel should be aware that carbon monoxide may build up in "
        "apparently clear basements"
    )
    assert marker is not None
    assert (marker.style, marker.label) == (MarkerStyle.LOWER_ROMAN, "ii")
    assert marker.text.startswith("Fire personnel")


def test_the_missing_space_is_tolerated_across_the_ordinal_families() -> None:
    for text, label in [("A.Command", "A"), ("6.Lobby Control", "6"), ("d.Determining", "d")]:
        marker = parse_marker(text)
        assert marker is not None, text
        assert marker.label == label


# --- What tolerating it must not let through ---------------------------------


def test_common_abbreviations_do_not_become_sections() -> None:
    """The reason the rule requires a capital: what follows these is lowercase."""
    for text in ["a.m. the crew returned to quarters", "e.g. a standpipe connection", "i.e. the"]:
        assert parse_marker(text) is None, text


def test_a_lowercase_continuation_is_not_a_marker() -> None:
    assert parse_marker("a.and then the crew advanced") is None


def test_a_measurement_does_not_become_a_decimal_section() -> None:
    """Decimal keeps requiring real whitespace — a fire document is full of these."""
    for text in ["2.5GPM at the nozzle", "1.5NST threaded couplings", "4.5PSI residual"]:
        assert parse_marker(text) is None, text


def test_a_bare_marker_with_no_text_is_not_a_marker() -> None:
    assert parse_marker("A.") is None
    assert parse_marker("ii.") is None
