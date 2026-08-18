"""Domain models for the ingestion pipeline.

The pipeline has two stages with a deliberate seam between them:

    file -> DocumentAnalyzer -> AnalyzedDocument -> chunker -> list[Chunk]

`AnalyzedDocument` is provider-neutral. Azure Document Intelligence is one producer of
it; the JSON fixtures in tests/fixtures are another. The chunker never sees an Azure
type, which is what makes it testable without an Azure account.

The division of labour across the seam: the analyzer *records* what extraction saw,
including layout roles, without editing. The chunker makes the editorial decisions —
which blocks are document furniture, where sections begin, how text is grouped.
"""

from typing import Literal

from pydantic import BaseModel, Field

ChunkKind = Literal["outline", "semantic"]

# Roles that Document Intelligence assigns to repeating page furniture. These are
# recorded by the analyzer and dropped by the chunker — see chunker.LAYOUT_FURNITURE.
ROLE_PAGE_HEADER = "pageHeader"
ROLE_PAGE_FOOTER = "pageFooter"
ROLE_PAGE_NUMBER = "pageNumber"

# Not a Document Intelligence role — one the analyzer assigns itself. Extraction reports
# figures separately from paragraphs, but the *text inside* a figure still comes back as
# ordinary paragraphs carrying no role, so a diagram is indistinguishable from body prose
# by role alone. The analyzer resolves the two back together and stamps this, which lets
# the chunker drop diagram text the same way it drops a running footer.
ROLE_FIGURE = "figure"


class AnalyzedBlock(BaseModel):
    """One contiguous block of extracted text — a paragraph, not a visual line.

    Document Intelligence returns both. Paragraphs are the right unit: a sentence that
    wraps across three visual lines is one paragraph, so chunk text does not end up with
    newlines mid-sentence.

    Page numbers are 1-indexed to match what a candidate sees when they open the PDF — a
    citation that says "page 12" must mean the page labelled 12 by their reader.

    `role` is the layout role extraction assigned, when it assigned one — `pageNumber`,
    `pageHeader`, `sectionHeading`, and so on. Recorded verbatim, including `None`.
    """

    text: str
    page: int = Field(ge=1)
    role: str | None = None


class AnalyzedDocument(BaseModel):
    """Provider-neutral result of running a document through text extraction."""

    source_name: str
    page_count: int = Field(ge=1)
    blocks: list[AnalyzedBlock]


def format_section_path(path: list[str]) -> str:
    """Render an outline path the way a reader would cite it.

    A decimal number already states its own position, so it stands alone: `304.2.1`.
    An ordinal path needs its ancestors to mean anything — item `d` is meaningless
    without knowing it sits under `PROCEDURE`, `C`, `4` — so the root is kept and the
    rest joined: `PROCEDURE C.4.d`.
    """
    if not path:
        return ""
    if len(path) == 1:
        return path[0]
    return f"{path[0]} {'.'.join(path[1:])}"


class Chunk(BaseModel):
    """A stored, citable unit of source text.

    Every question BadgeDay generates cites exactly one chunk. The location metadata
    here is what makes a citation resolvable back to something the candidate can open
    and read — if this is wrong, the citation is a lie and the product is broken.
    """

    chunk_id: str
    document_id: str
    ordinal: int = Field(ge=0, description="Position in the source document, 0-indexed.")
    kind: ChunkKind

    # The outline path to this chunk, outermost first: ["304.2.1"] for a decimal
    # guideline, ["PROCEDURE", "C", "4", "d"] for a lettered one. Empty for semantic
    # chunks, which have no position in an outline.
    section_path: list[str] = Field(default_factory=list)
    section_title: str | None = None

    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)

    text: str

    @property
    def section_label(self) -> str:
        """The outline reference, as cited. Empty when the chunk has no outline position."""
        return format_section_path(self.section_path)

    @property
    def depth(self) -> int:
        """How deep in the outline this chunk sits. 0 for semantic chunks."""
        return len(self.section_path)

    def location(self) -> str:
        """Human-readable source location, as shown to the candidate on review."""
        pages = (
            f"p. {self.page_start}"
            if self.page_start == self.page_end
            else f"pp. {self.page_start}–{self.page_end}"
        )
        label = self.section_label
        return f"{label}, {pages}" if label else pages
