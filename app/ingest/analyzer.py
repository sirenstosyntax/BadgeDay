"""Document text extraction, behind a provider-neutral seam.

`DocumentAnalyzer` is the only thing the rest of the pipeline knows about. Azure
Document Intelligence sits behind it in production; `FixtureDocumentAnalyzer` sits
behind it in tests. Nothing downstream can tell the difference, which is the point:
the chunker and the citation resolver get real test coverage without an Azure account,
a network call, or a real user document.
"""

from pathlib import Path
from typing import Protocol

from app.config import Settings
from app.ingest.models import AnalyzedDocument, AnalyzedLine


class DocumentAnalyzer(Protocol):
    """Extracts page-located text from a PDF or DOCX."""

    def analyze(self, path: Path) -> AnalyzedDocument: ...


class FixtureDocumentAnalyzer:
    """Reads a pre-extracted `AnalyzedDocument` from JSON.

    Used by tests and by local development without Azure credentials. The fixture
    format is exactly the `AnalyzedDocument` schema, so a fixture is a recording of
    what the real analyzer would have returned.
    """

    def __init__(self, fixture_dir: Path) -> None:
        self.fixture_dir = fixture_dir

    def analyze(self, path: Path) -> AnalyzedDocument:
        fixture = self.fixture_dir / f"{path.stem}.json"
        if not fixture.exists():
            raise FileNotFoundError(
                f"No fixture for {path.name}. Expected {fixture}. "
                "Set AZURE_DOCINTEL_ENDPOINT and AZURE_DOCINTEL_KEY to analyze real documents."
            )
        return AnalyzedDocument.model_validate_json(fixture.read_text())


class AzureDocumentAnalyzer:
    """Azure Document Intelligence, mapped onto `AnalyzedDocument`.

    Uses the prebuilt-layout model: it preserves reading order and hierarchical
    structure, which is what the outline-aware chunker depends on to find section
    numbering like 304.2.1.
    """

    def __init__(self, endpoint: str, key: str) -> None:
        self.endpoint = endpoint
        self.key = key

    def analyze(self, path: Path) -> AnalyzedDocument:
        # Imported lazily so the package is usable (and testable) without the Azure SDK
        # installed or credentials present.
        from azure.ai.documentintelligence import DocumentIntelligenceClient
        from azure.core.credentials import AzureKeyCredential

        client = DocumentIntelligenceClient(
            endpoint=self.endpoint, credential=AzureKeyCredential(self.key)
        )
        with path.open("rb") as fh:
            poller = client.begin_analyze_document("prebuilt-layout", body=fh)
        result = poller.result()

        lines: list[AnalyzedLine] = []
        for page_index, page in enumerate(result.pages or [], start=1):
            page_number = getattr(page, "page_number", page_index) or page_index
            for line in page.lines or []:
                text = line.content.strip()
                if text:
                    lines.append(AnalyzedLine(text=text, page=page_number))

        return AnalyzedDocument(
            source_name=path.name,
            page_count=max(len(result.pages or []), 1),
            lines=lines,
        )


def get_analyzer(settings: Settings, fixture_dir: Path | None = None) -> DocumentAnalyzer:
    """Return the real analyzer when Azure is configured, the fixture one otherwise."""
    if settings.azure_docintel_configured:
        return AzureDocumentAnalyzer(
            endpoint=settings.azure_docintel_endpoint,
            key=settings.azure_docintel_key,
        )
    return FixtureDocumentAnalyzer(fixture_dir or Path("tests/fixtures"))
