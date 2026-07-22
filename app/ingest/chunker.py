"""Outline-aware chunking.

SOGs are numbered hierarchically — 304, 304.2, 304.2.1 — and that numbering is what a
candidate uses to find a passage when they check a citation. So chunk boundaries follow
the outline, and the section number travels with the chunk into the citation.

Two things fall back to size-bounded grouping ("semantic" chunks): preamble before the
first numbered heading, and documents with no outline numbering at all. Body text
*following* a heading belongs to that heading until the next one — that is how outlines
work, and a parser cannot reliably decide otherwise.

Note on the name: `semantic` here means size-bounded grouping at line boundaries, not
embedding-based similarity. Real semantic segmentation is a later improvement; the field
name is the brief's, and the honest description is this one.

## Detecting a heading

The hard problem is false positives. `2.5 gallons of foam concentrate…` opens with
something shaped exactly like a section number. Accepting it would fragment the real
section and stamp a bogus section number onto every citation derived from it — a citation
that points somewhere the text does not exist is worse than no citation at all.

Three independent signals must all agree before a line is treated as a heading:

1. **Shape** — `<digits>(.<digits>)+` followed by text. A bare `304` is not enough; real
   SOG headings in this scheme carry at least one dot.
2. **Title-like text** — begins with a capital and runs no longer than
   `MAX_HEADING_WORDS`. `2.5 gallons` fails on the lowercase `g`.
3. **Hierarchical succession** — the number must be a plausible successor to the previous
   heading: a descendant of it, or a sibling of it or of one of its ancestors. After
   `304.2.2`, the number `2.5` is neither, so it is rejected even if it had survived the
   first two checks.

The failure mode this trades toward is missing a real heading rather than inventing one.
A missed heading degrades a citation's precision — the candidate is sent to the parent
section instead of the child. An invented heading sends them to a section that does not
exist. The first is a worse answer; the second is a broken promise.

## Container sections (read this before building coverage tracking)

A heading whose content lives entirely in its children — `304.3 Responsibilities`, with
the substance in `304.3.1` and `304.3.2` — produces a chunk holding only the heading line.
That is structurally correct and the chunk is kept, because dropping it would erase the
section from the document's outline.

Two downstream consequences:

- **Generation must skip it.** There is nothing to ask a question about. Attempting one
  would produce an ungrounded question wearing a valid-looking citation.
- **Coverage tracking must exclude it from the denominator.** Coverage is "% of sections
  exercised"; a section that can never be exercised would hold coverage permanently below
  100% and make the tracker read as broken to a candidate who has in fact covered
  everything.

The signal is a chunk whose text is exactly its heading line.
"""

import re
import uuid
from dataclasses import dataclass

from app.ingest.models import AnalyzedDocument, AnalyzedLine, Chunk

# Fixed namespace so chunk IDs are reproducible across ingestion runs. Citations store a
# chunk_id; if re-ingesting a document minted new IDs, every existing citation would
# dangle.
CHUNK_ID_NAMESPACE = uuid.UUID("f1c0d9a2-6b7e-5d3a-9c14-2e8b7a4f0d63")

HEADING_PATTERN = re.compile(r"^(\d+(?:\.\d+)+)\s+(\S.*)$")

MAX_HEADING_WORDS = 12
DEFAULT_MAX_CHARS = 1800


@dataclass(frozen=True)
class _Heading:
    number: str
    title: str
    parts: tuple[int, ...]


def _parse_parts(number: str) -> tuple[int, ...]:
    return tuple(int(part) for part in number.split("."))


def _is_plausible_successor(candidate: tuple[int, ...], previous: tuple[int, ...] | None) -> bool:
    """Could `candidate` follow `previous` in a well-formed outline?

    Valid: a descendant (304.2 -> 304.2.1), or a sibling of the previous heading or of
    any of its ancestors (304.2.2 -> 304.3, or -> 305).

    Invalid: repeating a number, moving backwards, or an unrelated branch — which is what
    a measurement like 2.5 looks like after 304.2.2.
    """
    if previous is None:
        return True

    if len(candidate) > len(previous) and candidate[: len(previous)] == previous:
        return True

    for index in range(min(len(candidate), len(previous))):
        if candidate[index] != previous[index]:
            # Everything before `index` matched, so this is a sibling at that level.
            return candidate[index] > previous[index]

    return False


def _detect_heading(text: str, previous: tuple[int, ...] | None) -> _Heading | None:
    match = HEADING_PATTERN.match(text.strip())
    if match is None:
        return None

    number, title = match.group(1), match.group(2).strip()

    if not title or not title[0].isupper():
        return None
    if len(title.split()) > MAX_HEADING_WORDS:
        return None

    parts = _parse_parts(number)
    if not _is_plausible_successor(parts, previous):
        return None

    return _Heading(number=number, title=title, parts=parts)


def _split_into_sections(
    lines: list[AnalyzedLine],
) -> list[tuple[_Heading | None, list[AnalyzedLine]]]:
    """Group lines under the heading that governs them.

    The leading group has no heading when the document opens with preamble.
    """
    sections: list[tuple[_Heading | None, list[AnalyzedLine]]] = []
    current_heading: _Heading | None = None
    current_lines: list[AnalyzedLine] = []
    previous_parts: tuple[int, ...] | None = None

    for line in lines:
        heading = _detect_heading(line.text, previous_parts)
        if heading is not None:
            if current_lines:
                sections.append((current_heading, current_lines))
            current_heading = heading
            current_lines = [line]
            previous_parts = heading.parts
        else:
            current_lines.append(line)

    if current_lines:
        sections.append((current_heading, current_lines))

    return sections


def _split_by_size(lines: list[AnalyzedLine], max_chars: int) -> list[list[AnalyzedLine]]:
    """Break an oversized section at line boundaries.

    A single line is never split — better an over-long chunk than a citation pointing at
    half a sentence.
    """
    groups: list[list[AnalyzedLine]] = []
    current: list[AnalyzedLine] = []
    size = 0

    for line in lines:
        length = len(line.text) + 1
        if current and size + length > max_chars:
            groups.append(current)
            current, size = [], 0
        current.append(line)
        size += length

    if current:
        groups.append(current)

    return groups


def chunk_id_for(document_id: str, ordinal: int) -> str:
    """Deterministic chunk ID, stable across re-ingestion of the same document."""
    return str(uuid.uuid5(CHUNK_ID_NAMESPACE, f"{document_id}:{ordinal}"))


def chunk_document(
    document: AnalyzedDocument,
    document_id: str,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[Chunk]:
    """Split an analyzed document into citable chunks, in reading order."""
    chunks: list[Chunk] = []

    for heading, lines in _split_into_sections(document.lines):
        for group in _split_by_size(lines, max_chars):
            ordinal = len(chunks)
            chunks.append(
                Chunk(
                    chunk_id=chunk_id_for(document_id, ordinal),
                    document_id=document_id,
                    ordinal=ordinal,
                    kind="outline" if heading is not None else "semantic",
                    section_number=heading.number if heading is not None else None,
                    section_title=heading.title if heading is not None else None,
                    page_start=min(line.page for line in group),
                    page_end=max(line.page for line in group),
                    text="\n".join(line.text for line in group),
                )
            )

    return chunks
