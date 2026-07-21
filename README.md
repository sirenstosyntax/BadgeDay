# BadgeDay

Upload your reading list. Drill cited questions until badge day.

A web app for firefighter promotional candidates. The candidate uploads their own
department's announced promotional reading list; BadgeDay generates practice questions
from those exact documents, every one carrying a citation back to the section and page it
came from.

See [`CLAUDE.md`](CLAUDE.md) for the full brief, scope boundaries, and hard constraints.

## Local setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env      # fill in what you have; blanks are tolerated
pytest
```

The test suite runs with no credentials at all. Document extraction sits behind a
provider seam (`app/ingest/analyzer.py`), so the chunker and citation resolver are tested
against synthetic fixtures rather than a live Azure resource.

## Run the API

```bash
uvicorn app.main:app --reload
```

- `GET /health` — liveness. Never touches a dependency.
- `GET /ready` — which external services are configured. Does not call them.

## Layout

```
app/
  config.py          Environment-driven settings. Nothing deployment-specific is hardcoded.
  main.py            FastAPI entry point.
  api/               HTTP routes.
  ingest/            file -> AnalyzedDocument -> Chunk[]
  generate/          chunks -> cited questions
tests/
  fixtures/          Synthetic documents only. Never a real or user document.
```

## Constraints that are not negotiable

Read them in `CLAUDE.md` before changing anything in `app/generate/`. In short: no
question ships without a resolvable citation; questions are written in original words and
never reproduce source passages; the product is sold to individuals and contains no
feature for administering or building exams; user documents are private per user and
hard-deletable.
