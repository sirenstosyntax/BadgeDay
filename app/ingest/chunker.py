"""Outline-aware chunking.

A candidate checking a citation navigates by the document's own structure — "PROCEDURE,
item 4.d.ii" or "§ 304.2.1". So chunk boundaries follow the outline, and the path to a
chunk travels with it into the citation. A chunk that can only say "page 4" sends a
candidate hunting through a page; on a two-hundred-page reading list that is no citation
at all.

Numbering conventions vary by department and are recognized in `outline.py`. This module
turns recognized headings into a tree, then decides where chunk boundaries fall.

## Where boundaries go

Not simply at every heading. A deep outline produces items far too small to question —
`a. Supplementing the sprinkler system;` is five words. Chunking at every marker would
strand that content: too thin to generate from on its own, and absent from its parent.

So a node is emitted whole, with all its descendants, when the subtree fits within
`max_chars`. `5. Water Supply` arrives as one chunk carrying its sub-items, cited as the
section a reader would actually look up. Only when a subtree is too large does it split
into its children. This is the "hybrid" the brief asks for: outline structure decides
*where* boundaries can fall, size decides *which* of them are taken.

## Page furniture

Running headers and footers are dropped before anything else. A footer appears on every
page, so it lands inside every section spanning a page break — interrupting a sentence,
and offering the generator a perfectly citable, perfectly worthless question. That last
part is why it matters: nothing about it is false, so no grounding check catches it.

Figure text is dropped for the same reason, and it is the more dangerous case. A footer
is worthless but harmless; an org chart is forty fragments of real-looking content that
attach to whichever section preceded the diagram, so a question drawn from them cites a
section that says something else. The citation still resolves, so verification passes.

This does lose any content that only exists inside a diagram. That is the intended
trade: extraction of diagram text is unreliable in a way prose is not — superscript
ordinals in a real chart came back as `4""`, `15T`, and `21D` — so a question generated
from it would be wrong on the facts as well as wrong on the citation. Tables are a
separate structure in the response and are unaffected.

## Container sections (read before building coverage tracking)

A heading whose content lives entirely in its children can still emit a heading-only
chunk when its subtree is too large to merge. It is kept, because dropping it would erase
the section from the outline. Generation skips it (`is_generatable`), and coverage
tracking must exclude it from the denominator — a section that can never be exercised
would hold coverage below 100% forever and read as broken to a candidate who has in fact
covered everything.
"""

import uuid
from dataclasses import dataclass, field

from app.ingest.models import (
    ROLE_FIGURE,
    ROLE_PAGE_FOOTER,
    ROLE_PAGE_HEADER,
    ROLE_PAGE_NUMBER,
    AnalyzedBlock,
    AnalyzedDocument,
    Chunk,
)
from app.ingest.outline import (
    Marker,
    MarkerStyle,
    decimal_depth,
    decimal_follows,
    is_ambiguous_roman,
    opens_or_continues,
    parse_marker,
)

# Fixed namespace so chunk IDs are reproducible across ingestion runs. Citations store a
# chunk_id; if re-ingesting a document minted new IDs, every existing citation would
# dangle.
CHUNK_ID_NAMESPACE = uuid.UUID("f1c0d9a2-6b7e-5d3a-9c14-2e8b7a4f0d63")

DEFAULT_MAX_CHARS = 1800

# Below this, a sub-item is a fragment rather than a section: too little text to generate
# a question from, so splitting it out would strand its content rather than make it
# citable. Roughly eighteen words — above a list item like "a. Supplementing the
# sprinkler system;" and below the shortest numbered subsection that states a real
# requirement. Set it higher and genuine subsections get absorbed, silently coarsening
# their citations.
MIN_SPLIT_CHARS = 120

LAYOUT_FURNITURE = frozenset({ROLE_PAGE_HEADER, ROLE_PAGE_FOOTER, ROLE_PAGE_NUMBER, ROLE_FIGURE})


@dataclass
class _Node:
    """One outline section: its own text, and everything nested beneath it."""

    marker: Marker | None = None
    path: list[str] = field(default_factory=list)
    blocks: list[AnalyzedBlock] = field(default_factory=list)
    children: list["_Node"] = field(default_factory=list)
    last_child_label: dict[MarkerStyle, str] = field(default_factory=dict)

    @property
    def style(self) -> MarkerStyle | None:
        return self.marker.style if self.marker else None

    def subtree_blocks(self) -> list[AnalyzedBlock]:
        blocks = list(self.blocks)
        for child in self.children:
            blocks.extend(child.subtree_blocks())
        return blocks

    def subtree_chars(self) -> int:
        return sum(len(b.text) + 1 for b in self.subtree_blocks())


def _resolve_style(marker: Marker, stack: list[_Node]) -> MarkerStyle:
    """Disambiguate `i.`, `v.`, and `x.`, which are both numerals and letters.

    An `i.` following `h.` continues a lettered list. An `i.` anywhere else opens a
    nested roman one. Getting this wrong either fragments a list or buries a level.
    """
    if marker.style is not MarkerStyle.LOWER_ROMAN or not is_ambiguous_roman(marker.label):
        return marker.style

    for node in reversed(stack):
        previous = node.last_child_label.get(MarkerStyle.LOWER_ALPHA)
        if previous is not None:
            expected = chr(ord(previous) + 1)
            if expected == marker.label.lower():
                return MarkerStyle.LOWER_ALPHA
            break
    return MarkerStyle.LOWER_ROMAN


def _target_index(
    marker: Marker,
    style: MarkerStyle,
    stack: list[_Node],
    last_decimal: str | None,
) -> int | None:
    """Where in the open stack this heading belongs, or None if it is not a heading.

    Depth comes from the numbering family. A decimal number states its own depth. An
    ordinal marker's depth is wherever its style already sits in the stack — or one
    level deeper than the current node if the style is new, which is how a reader infers
    that `a.` nests under `1.` on first encountering it.
    """
    if style is MarkerStyle.NAMED:
        return 1

    if style is MarkerStyle.DECIMAL:
        if not decimal_follows(marker.label, last_decimal):
            return None
        depth = decimal_depth(marker.label)
        for index in range(1, len(stack)):
            node = stack[index]
            if node.style is MarkerStyle.DECIMAL and decimal_depth(node.path[-1]) >= depth:
                return index
        return len(stack)

    for index in range(1, len(stack)):
        node = stack[index]
        if node.style is style:
            parent = stack[index - 1]
            if not opens_or_continues(style, marker.label, parent.last_child_label.get(style)):
                return None
            return index

    if not opens_or_continues(style, marker.label, None):
        return None
    return len(stack)


def _parent_path(stack: list[_Node], style: MarkerStyle) -> list[str]:
    """The ancestor path a new node inherits.

    A decimal number already names its own ancestors — `304.2.1` states that it sits
    under `304.2` — so repeating them would produce `304.2 304.2.1`. Decimal ancestors
    are therefore dropped, while a named heading above them is kept, since a document
    can put `PROCEDURE` over a decimal series and the heading still carries meaning.
    """
    if style is not MarkerStyle.DECIMAL:
        return stack[-1].path
    return [
        node.marker.label
        for node in stack[1:]
        if node.marker is not None and node.style is not MarkerStyle.DECIMAL
    ]


def _build_tree(blocks: list[AnalyzedBlock]) -> _Node:
    root = _Node()
    stack: list[_Node] = [root]
    last_decimal: str | None = None

    for block in blocks:
        marker = parse_marker(block.text, block.role)
        target: int | None = None
        style: MarkerStyle | None = None

        if marker is not None:
            style = _resolve_style(marker, stack)
            marker = Marker(style=style, label=marker.label, text=marker.text)
            target = _target_index(marker, style, stack, last_decimal)

        if marker is None or target is None:
            stack[-1].blocks.append(block)
            continue

        del stack[target:]
        parent = stack[-1]
        node = _Node(
            marker=marker,
            path=[*_parent_path(stack, style), marker.label],
            blocks=[block],
        )
        parent.children.append(node)
        parent.last_child_label[style] = marker.label
        stack.append(node)
        if style is MarkerStyle.DECIMAL:
            last_decimal = marker.label

    return root


def _split_by_size(blocks: list[AnalyzedBlock], max_chars: int) -> list[list[AnalyzedBlock]]:
    """Break an oversized run at block boundaries.

    A single block is never split — better an over-long chunk than a citation pointing at
    half a sentence.
    """
    groups: list[list[AnalyzedBlock]] = []
    current: list[AnalyzedBlock] = []
    size = 0

    for block in blocks:
        length = len(block.text) + 1
        if current and size + length > max_chars:
            groups.append(current)
            current, size = [], 0
        current.append(block)
        size += length

    if current:
        groups.append(current)

    return groups


def chunk_id_for(document_id: str, ordinal: int) -> str:
    """Deterministic chunk ID, stable across re-ingestion of the same document."""
    return str(uuid.uuid5(CHUNK_ID_NAMESPACE, f"{document_id}:{ordinal}"))


def _emit_whole(node: _Node, max_chars: int) -> bool:
    """Should this node be emitted as one chunk carrying all its descendants?

    Two competing goods. Splitting at every marker gives the most precise citation — a
    candidate sent to `PROCEDURE C.4.d` rather than to `PROCEDURE`. Merging keeps thin
    sub-items reachable: `a. Supplementing the sprinkler system;` is five words, too
    little to question on its own and lost entirely if separated from its parent.

    So children are kept separate when each one carries enough text to stand as its own
    citation, and absorbed when they are fragments. Preferring the merge unconditionally
    silently coarsens every citation in a well-structured document; preferring the split
    unconditionally strands the content of every deep list.
    """
    if not node.children:
        return True
    if node.subtree_chars() > max_chars:
        return False
    return not all(child.subtree_chars() >= MIN_SPLIT_CHARS for child in node.children)


def _emit(
    node: _Node,
    document_id: str,
    max_chars: int,
    chunks: list[Chunk],
) -> None:
    def append(blocks: list[AnalyzedBlock], path: list[str], title: str | None) -> None:
        if not blocks:
            return
        ordinal = len(chunks)
        chunks.append(
            Chunk(
                chunk_id=chunk_id_for(document_id, ordinal),
                document_id=document_id,
                ordinal=ordinal,
                kind="outline" if path else "semantic",
                section_path=list(path),
                section_title=title,
                page_start=min(b.page for b in blocks),
                page_end=max(b.page for b in blocks),
                text="\n".join(b.text for b in blocks),
            )
        )

    title = node.marker.title if node.marker else None

    if node.marker is not None and _emit_whole(node, max_chars):
        append(node.subtree_blocks(), node.path, title)
        return

    for group in _split_by_size(node.blocks, max_chars):
        append(group, node.path, title)

    for child in node.children:
        _emit(child, document_id, max_chars, chunks)


def chunk_document(
    document: AnalyzedDocument,
    document_id: str,
    max_chars: int = DEFAULT_MAX_CHARS,
) -> list[Chunk]:
    """Split an analyzed document into citable chunks, in reading order."""
    body = [b for b in document.blocks if b.role not in LAYOUT_FURNITURE]
    root = _build_tree(body)
    chunks: list[Chunk] = []
    _emit(root, document_id, max_chars, chunks)
    return chunks
