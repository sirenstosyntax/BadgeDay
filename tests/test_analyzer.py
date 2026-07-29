"""The analyzer seam: fixtures must load as a valid provider-neutral AnalyzedDocument."""

from pathlib import Path

import pytest

from app.config import Settings
from app.ingest.analyzer import (
    AzureDocumentAnalyzer,
    FixtureDocumentAnalyzer,
    figure_paragraph_indices,
    get_analyzer,
)
from app.ingest.models import AnalyzedDocument


def test_fixture_loads_as_analyzed_document(synthetic_sog: AnalyzedDocument) -> None:
    assert synthetic_sog.source_name == "synthetic_sog.pdf"
    assert synthetic_sog.page_count == 2
    assert len(synthetic_sog.blocks) > 0


def test_fixture_preserves_page_numbers(synthetic_sog: AnalyzedDocument) -> None:
    """A citation is only as good as its page number."""
    pages = {line.page for line in synthetic_sog.blocks}
    assert pages == {1, 2}


def test_fixture_preserves_reading_order(synthetic_sog: AnalyzedDocument) -> None:
    """Outline chunking depends on lines arriving in document order."""
    texts = [line.text for line in synthetic_sog.blocks]
    assert texts.index("304.1 Purpose") < texts.index("304.2 Scope")
    assert texts.index("304.2 Scope") < texts.index("304.2.1 Interior Operations")
    assert texts.index("304.2.1 Interior Operations") < texts.index("304.3 Responsibilities")


def test_missing_fixture_names_the_expected_path(fixture_dir: Path) -> None:
    analyzer = FixtureDocumentAnalyzer(fixture_dir)
    with pytest.raises(FileNotFoundError, match="nonexistent"):
        analyzer.analyze(Path("nonexistent.pdf"))


def test_get_analyzer_falls_back_to_fixtures_without_azure(fixture_dir: Path) -> None:
    settings = Settings(azure_docintel_endpoint="", azure_docintel_key="")
    assert isinstance(get_analyzer(settings, fixture_dir), FixtureDocumentAnalyzer)


def test_get_analyzer_uses_azure_when_configured(fixture_dir: Path) -> None:
    settings = Settings(
        azure_docintel_endpoint="https://sts-docintel.cognitiveservices.azure.com/",
        azure_docintel_key="fake-key-for-selection-test",
    )
    assert isinstance(get_analyzer(settings, fixture_dir), AzureDocumentAnalyzer)


# --- Figure resolution -------------------------------------------------------
#
# Extraction reports figures separately from the paragraphs that make up their text, so
# diagram content arrives untagged and reads as body prose. These cover the resolution
# that puts the two back together, using stand-ins shaped like the service response.


class _Elements:
    def __init__(self, elements: list[str] | None) -> None:
        self.elements = elements


class _Figure:
    def __init__(
        self,
        elements: list[str] | None = None,
        caption: _Elements | None = None,
        footnotes: list[_Elements] | None = None,
    ) -> None:
        self.elements = elements
        self.caption = caption
        self.footnotes = footnotes


class _Result:
    def __init__(self, figures: list[_Figure] | None) -> None:
        self.figures = figures


def test_figure_paragraphs_are_resolved_from_pointers() -> None:
    result = _Result([_Figure(elements=["/paragraphs/4", "/paragraphs/5"])])
    assert figure_paragraph_indices(result) == {4, 5}


def test_figure_captions_and_footnotes_are_included() -> None:
    """They describe the diagram, not the guideline."""
    result = _Result(
        [
            _Figure(
                elements=["/paragraphs/9"],
                caption=_Elements(["/paragraphs/8"]),
                footnotes=[_Elements(["/paragraphs/10"])],
            )
        ]
    )
    assert figure_paragraph_indices(result) == {8, 9, 10}


def test_non_paragraph_pointers_are_ignored() -> None:
    """A figure may also point at lines and words, which the analyzer never reads."""
    result = _Result([_Figure(elements=["/paragraphs/2", "/pages/0/lines/7", "/tables/1"])])
    assert figure_paragraph_indices(result) == {2}


def test_a_result_without_figures_recognizes_none() -> None:
    """Older service versions omit the field; behaviour falls back to the previous one."""
    assert figure_paragraph_indices(_Result(None)) == set()
    assert figure_paragraph_indices(object()) == set()


def test_a_figure_without_elements_is_survivable() -> None:
    result = _Result([_Figure(elements=None, caption=_Elements(None))])
    assert figure_paragraph_indices(result) == set()
