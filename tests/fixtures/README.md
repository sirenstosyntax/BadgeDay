# Test fixtures

Everything here is **synthetic**. No real department document, and no user-uploaded
document, may ever be committed to this repository — see the `.gitignore` rules for
`*.pdf` and `*.docx`.

`synthetic_sog.json` is a hand-written `AnalyzedDocument` (see `app/ingest/models.py`)
standing in for what Azure Document Intelligence would return for a two-page SOG. It
exists to exercise the parts of the pipeline where silent failure destroys the product:

- **Hierarchical outline numbering** — `304.1`, `304.2`, `304.2.1`, `304.3.2`. Chunk
  boundaries must follow this structure, and the depth must survive into the citation.
- **A section spanning a page break** — `304.2.1` begins on page 1 and continues onto
  page 2, so `page_start` and `page_end` cannot be assumed equal. A citation that reports
  only the heading's page sends the candidate to the wrong place.
- **Unnumbered preamble** — the department name, guideline number, and subject line
  precede the first numbered heading and belong to no section. They fall back to semantic
  chunking rather than being attached to `304.1`.
- **A false-positive heading** — `2.5 gallons of foam concentrate…` starts with what looks
  like a section number. Treating it as a heading would fragment `304.2.2` and attach a
  bogus section number to a citation.

Note that body text following a heading belongs to that heading until the next heading —
including the closing paragraph after `304.3.2`. Semantic fallback is for preamble and for
documents with no outline numbering at all, not for trailing prose inside a numbered
section.

"Example Fire Department" is not a real department. The section numbers are illustrative
and match no published guideline.
