"""The analyzer seam: fixtures must load as a valid provider-neutral AnalyzedDocument."""

from pathlib import Path

import pytest

from app.config import Settings
from app.ingest.analyzer import (
    AzureDocumentAnalyzer,
    FixtureDocumentAnalyzer,
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
