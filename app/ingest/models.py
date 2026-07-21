"""Domain models for the ingestion pipeline.

The pipeline has two stages with a deliberate seam between them:

    file -> DocumentAnalyzer -> AnalyzedDocument -> chunker -> list[Chunk]

`AnalyzedDocument` is provider-neutral. Azure Document Intelligence is one producer of
it; the JSON fixtures in tests/fixtures are another. The chunker never sees an Azure
type, which is what makes it testable without an Azure account.
"""

from typing import Literal

from pydantic import BaseModel, Field

ChunkKind = Literal["outline", "semantic"]


class AnalyzedLine(BaseModel):
    """One line of extracted text, with the page it appeared on.

    Page numbers are 1-indexed to match what a candidate sees when they open the PDF —
    a citation that says "page 12" must mean the page labelled 12 by their reader.
    """

    text: str
    page: int = Field(ge=1)


class AnalyzedDocument(BaseModel):
    """Provider-neutral result of running a document through text extraction."""

    source_name: str
    page_count: int = Field(ge=1)
    lines: list[AnalyzedLine]


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

    # Present for outline chunks (e.g. "304.2.1"), absent for semantic fallback chunks.
    section_number: str | None = None
    section_title: str | None = None

    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)

    text: str

    def location(self) -> str:
        """Human-readable source location, as shown to the candidate on review."""
        pages = (
            f"p. {self.page_start}"
            if self.page_start == self.page_end
            else f"pp. {self.page_start}–{self.page_end}"
        )
        if self.section_number:
            return f"§ {self.section_number}, {pages}"
        return pages
