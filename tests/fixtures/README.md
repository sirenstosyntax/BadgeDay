# Test fixtures

Everything here is **synthetic**. No real department document, and no user-uploaded
document, may ever be committed to this repository — see the `.gitignore` rules for
`*.pdf` and `*.docx`.

`synthetic_sog.json` is an `AnalyzedDocument` (see `app/ingest/models.py`) **recorded from
a real Azure Document Intelligence run**, not hand-written. A synthetic two-page SOG was
rendered to PDF, analyzed, and the result serialized here — so the fixture reproduces
Document Intelligence's actual output shape, including paragraph roles, rather than an
assumption about it.

Regenerate it by rendering the same content to PDF and running it through
`AzureDocumentAnalyzer`. Do not hand-edit: the value of this file is that it is a
recording. An earlier hand-written version got the block granularity wrong (visual lines
rather than paragraphs) and missed page-furniture roles entirely, which hid two real
defects until a genuine document was run through.

`synthetic_outline_sog.json` covers the other numbering family: named headings
(`PURPOSE`, `PROCEDURE`) followed by `A.` / `1.` / `a.` / `i.` — the classic legal outline,
which is what regional and county guidelines actually use. Unlike the decimal fixture this
one is **hand-written**, because the `sectionHeading` role it depends on is assigned from
visual formatting that a uniform-font render cannot reproduce. It also carries an org
chart's worth of all-caps labels (`COMMAND`, `HYDRANT`), which look exactly like headings
and must not become sections.

It exercises the parts of the pipeline where silent failure destroys the product:

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
- **A running page footer** — `SOG 304 - Page 1 of 2`, carrying the `pageNumber` role,
  sits *between* the two sentences of `304.2.1`. It must be dropped: it would otherwise
  interrupt the section mid-thought and hand the generator a perfectly citable, perfectly
  worthless question. This is the case the citation rule cannot catch on its own.

Note that body text following a heading belongs to that heading until the next heading —
including the closing paragraph after `304.3.2`. Semantic fallback is for preamble and for
documents with no outline numbering at all, not for trailing prose inside a numbered
section.

"Example Fire Department" is not a real department. The section numbers are illustrative
and match no published guideline.
