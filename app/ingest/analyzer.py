"""Document text extraction, behind a provider-neutral seam.

`DocumentAnalyzer` is the only thing the rest of the pipeline knows about. Azure
Document Intelligence sits behind it in production; `FixtureDocumentAnalyzer` sits
behind it in tests. Nothing downstream can tell the difference, which is the point:
the chunker and the citation resolver get real test coverage without an Azure account,
a network call, or a real user document.
"""

import re
from pathlib import Path
from typing import Any, Protocol

from app.config import Settings
from app.ingest.models import ROLE_FIGURE, AnalyzedBlock, AnalyzedDocument

# Document Intelligence cross-references its own result with JSON pointers: a figure
# lists `/paragraphs/7` to mean `result.paragraphs[7]`. Only paragraph pointers matter
# here; a figure may also point at lines or words, which the analyzer never reads.
_PARAGRAPH_POINTER = re.compile(r"^/paragraphs/(\d+)$")


def figure_paragraph_indices(result: Any) -> set[int]:
    """Indices of paragraphs that belong to a figure rather than to the guideline text.

    Figures come back in `result.figures`, separately from `result.paragraphs` — but the
    text *inside* a figure is still emitted as ordinary paragraphs with no role. An ICS
    org chart therefore arrives as forty untagged fragments (`COMMAND`, `SAFETY`,
    `LOGISTICS`, `BACKUP`) that look exactly like body prose, and lands in whichever
    section happened to precede the diagram.

    That is the worst shape of failure this pipeline has: a question generated from those
    fragments cites the section they were absorbed into, the citation *resolves* because
    the chunk really does contain that text, and verification passes. The candidate opens
    the SOG at the cited item and finds something else entirely.

    Each figure states its own contents as JSON pointers, so membership is exact and needs
    no geometry. Captions and footnotes are pulled in too — they describe the diagram
    rather than the guideline.

    Written defensively: `figures`, `caption`, `footnotes`, and `elements` are all
    optional in the response, and an older service version may omit them entirely. A
    missing field means no figures are recognized, which is the pre-existing behaviour.
    """
    indices: set[int] = set()
    for figure in getattr(result, "figures", None) or []:
        sources = [figure, *(getattr(figure, "footnotes", None) or [])]
        caption = getattr(figure, "caption", None)
        if caption is not None:
            sources.append(caption)
        for source in sources:
            for pointer in getattr(source, "elements", None) or []:
                match = _PARAGRAPH_POINTER.match(str(pointer))
                if match:
                    indices.add(int(match.group(1)))
    return indices


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

    The one role this class *assigns* rather than copies is `ROLE_FIGURE`. That is still
    recording rather than judging: extraction already knows which paragraphs sit inside a
    diagram, but says so in `result.figures` instead of on the paragraph. Resolving the
    two back together is part of reading the response faithfully — see
    `figure_paragraph_indices`. Whether diagram text is worth a question remains the
    chunker's call.
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

        figure_paragraphs = figure_paragraph_indices(result)

        blocks: list[AnalyzedBlock] = []
        for index, paragraph in enumerate(result.paragraphs or []):
            text = (paragraph.content or "").strip()
            if not text:
                continue
            regions = paragraph.bounding_regions or []
            page = regions[0].page_number if regions else 1
            role = getattr(paragraph.role, "value", paragraph.role)
            if index in figure_paragraphs:
                # Figure membership overrides whatever role the paragraph carries. A box
                # in an org chart is often tagged `sectionHeading` on visual shape alone,
                # and that is precisely the false heading the chunker must never see.
                role = ROLE_FIGURE
            blocks.append(AnalyzedBlock(text=text, page=page, role=role))

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
