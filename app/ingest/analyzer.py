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
from app.ingest.models import AnalyzedBlock, AnalyzedDocument


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

    Uses the prebuilt-layout model, reading `result.paragraphs` rather than
    `result.pages[].lines`. The distinction matters. Lines are *visual*: a sentence
    wrapping across three rendered lines comes back as three entries, so chunk text ends
    up with newlines mid-sentence, and a page footer sitting between them is interleaved
    into the middle of a section. Paragraphs are logical, and they carry a layout `role`
    that identifies page numbers, headers, and footers.

    Roles are recorded, not acted on. Deciding that a page footer is not worth asking a
    question about is an editorial judgement, and it belongs in the chunker where it can
    be tested against a fixture.
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

        blocks: list[AnalyzedBlock] = []
        for paragraph in result.paragraphs or []:
            text = (paragraph.content or "").strip()
            if not text:
                continue
            regions = paragraph.bounding_regions or []
            page = regions[0].page_number if regions else 1
            role = paragraph.role
            blocks.append(
                AnalyzedBlock(
                    text=text,
                    page=page,
                    role=getattr(role, "value", role),
                )
            )

        return AnalyzedDocument(
            source_name=path.name,
            page_count=max(len(result.pages or []), 1),
            blocks=blocks,
        )


def get_analyzer(settings: Settings, fixture_dir: Path | None = None) -> DocumentAnalyzer:
    """Return the real analyzer when Azure is configured, the fixture one otherwise."""
    if settings.azure_docintel_configured:
        return AzureDocumentAnalyzer(
            endpoint=settings.azure_docintel_endpoint,
            key=settings.azure_docintel_key,
        )
    return FixtureDocumentAnalyzer(fixture_dir or Path("tests/fixtures"))
