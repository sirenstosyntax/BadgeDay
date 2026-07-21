# Test fixtures

Everything here is **synthetic**. No real department document, and no user-uploaded
document, may ever be committed to this repository — see the `.gitignore` rules for
`*.pdf` and `*.docx`.

`synthetic_sog.json` is a hand-written `AnalyzedDocument` (see `app/ingest/models.py`)
standing in for what Azure Document Intelligence would return for a two-page SOG. It
exists to exercise the parts of the pipeline where silent failure destroys the product:

- **Hierarchical outline numbering** — `304.1`, `304.2`, `304.2.1`, `304.3.2`. Chunk
  boundaries must follow this structure, and the depth must survive into the citation.
- **Sections that span a page break** — `304.2` starts on page 1 and its children
  continue onto page 2, so `page_start` and `page_end` cannot be assumed equal.
- **Unnumbered trailing text** — the closing paragraph and the revision date belong to no
  numbered section, and must fall back to semantic chunking rather than being silently
  attached to `304.3.2` or dropped.

"Example Fire Department" is not a real department. The section numbers are illustrative
and match no published guideline.
