"""Citation display formatting.

`Chunk.location()` is what a candidate reads on the review screen. It is the visible
end of the citation chain, so it gets a test even though it is three lines long.
"""

from app.ingest.models import Chunk


def _chunk(**overrides: object) -> Chunk:
    defaults: dict[str, object] = {
        "chunk_id": "c1",
        "document_id": "d1",
        "ordinal": 0,
        "kind": "outline",
        "section_path": ["304.2.1"],
        "section_title": "Interior Operations",
        "page_start": 1,
        "page_end": 1,
        "text": "…",
    }
    return Chunk.model_validate({**defaults, **overrides})


def test_location_single_page_with_section() -> None:
    assert _chunk().location() == "304.2.1, p. 1"


def test_location_spanning_pages() -> None:
    assert _chunk(page_start=1, page_end=2).location() == "304.2.1, pp. 1–2"


def test_location_without_section_number() -> None:
    """Semantic fallback chunks still cite a page — never nothing."""
    chunk = _chunk(kind="semantic", section_path=[], section_title=None)
    assert chunk.location() == "p. 1"
