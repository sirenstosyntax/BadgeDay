# BadgeDay — Project Brief

## What this is

BadgeDay is a B2C subscription product under Sirens to Syntax LLC serving firefighters at
two different career moments. Consumer brand — completely separate from DrillGround
(B2G). Domains: badgeday.com / badgeday.app. Social: @badgedayapp.

## Product family

BadgeDay has two parts. **They are architecturally different products sharing a brand, an
account layer, and a billing layer.** Do not assume a pattern from one transfers to the
other — in particular, the citation-grounding discipline that defines Command has no
equivalent in Recruit, and the "we ship zero content" rule is Command-only.

### BadgeDay Command — promotional exam prep (V1, building now)

For serving firefighters testing for Lieutenant / Captain / Battalion Chief. The
candidate uploads their department's announced promotional reading list (their own public
documents: SOGs listed on the exam announcement, standard published texts) and BadgeDay
generates cited practice questions from those exact documents, with a quiz interface that
tracks coverage until nothing on the list can surprise them.

**Pitch:** "Upload your reading list. Drill cited questions until badge day."

**Shape:** RAG over user-uploaded documents. BadgeDay ships zero content. Every question
carries a citation resolvable to a stored chunk.

### BadgeDay Recruit — pre-hire preparation (later; do not build during V1)

For candidates who have not been hired yet and are working to become competitive: no
department, no reading list. Formerly referred to as "BadgeDay Entry."

Recruit helps candidates develop the attributes departments hire for — through practice
tests, mock interviews, teaching of foundational principles common to all departments,
and the common traps that keep candidates from getting hired.

**Shape:** coaching and feedback against expert-authored rubrics — not a question bank.
There is no user upload, no retrieval, and no citation chain.

**Anchor the product on the oral board and on candidate-readiness gap analysis.** That is
where candidates are actually eliminated: most who reach the oral board have already
passed the written, and the next largest group is eliminated for being uncompetitive on
paper (no EMT, no coursework, no volunteer time) in ways that are fixable 6–18 months out.
Foundational principles and common traps are supporting content. Written-exam practice
comes last if at all — it is the most commoditized piece of the market and carries the
worst risk-to-differentiation ratio, since that is where the copyrighted commercial
batteries live.

This shape is deliberate for cost reasons as well. A question bank means an ever-growing
library of items, each needing review and each decaying as hiring practices shift.
Rubric-based critique means the reviewable asset is a bounded, stable set of rubrics and
frameworks, and the candidate's own answer supplies the variable content.

**Explicitly not the Command model:** Recruit must NOT be built to depend on the
candidate uploading department hiring materials. A pre-hire candidate has no such
documents, and requiring them would gate the product on something its users do not have.

## V1 scope — Command only (MVP — build only this)

- **Auth + billing:** email auth, Stripe subscription (monthly ~$29 and a 90-day
  intensive ~$129 — exact pricing configurable, not hardcoded).
- **Document upload:** PDF/DOCX, per-user private storage. The candidate uploads their
  own documents; we ship zero content.
- **Ingestion pipeline:** Azure Document Intelligence → hybrid chunking. Chunking must
  respect document outline numbering (SOGs are numbered hierarchically, e.g. 304.2.1 —
  chunk boundaries follow the outline structure, falling back to semantic chunks for
  unnumbered text). Store chunks with full location metadata (doc, section number, page).
- **Question generation:** Anthropic API, RAG-grounded. Question types: multiple choice,
  true/false, short-answer with model answer. EVERY question stores a citation (document
  + section/page) resolvable back to the stored chunk. Generation prompt uses strict
  guardrails: questions derive ONLY from retrieved chunks, never from model
  world-knowledge about fire service topics. Structured JSON output, schema-validated;
  reject and regenerate on validation failure.
- **Quiz UI:** practice sessions by document or full-list mix; grade answers; show
  citation + source section reference on review; flag/save questions; coverage tracker
  (% of each document's sections exercised).
- **Account basics:** delete documents, delete account (hard-delete user content).

## Explicitly OUT of scope for V1

- Voice / oral-board simulation (that's the V2 engine — do not scaffold it). Note this
  also defers Recruit's voice-based mock interviews; text-based interview practice is
  available sooner.
- BadgeDay Recruit in any form (see Product family above — comes after Command V1)
- Department/team accounts of ANY kind (see firewall below)
- Native mobile apps (responsive web only)
- Community features, leaderboards, content marketplace

## Hard constraints — never violate, never "helpfully" work around

### Product-wide

- **Buyer firewall:** individuals only. No feature that lets a department create, export,
  or administer examinations. No org accounts, no "share with my department," no
  exam-builder mode. (Company policy: exam prep is sold only to individuals; exam
  creation is sold to no one.)
- **Copyright:** questions and answers are written in original words. Never store or
  display long verbatim extracts in question content.
- **No licensed standards as a grounding source:** BadgeDay does not derive content from
  licensed or copyrighted standards and texts (NFPA, IFSTA and equivalents), and does not
  derive Recruit content from commercial hiring-test batteries (National Testing Network
  / FireTEAM, IPMA-HR, CPS HR and equivalents). Testing the same underlying *abilities*
  with original items is fine; tracking a specific published battery's structure or
  content is not.
- **Privacy:** user documents are private per user, never shared across users, never used
  to improve prompts/models, hard-deletable.

### Command only

- **Citation grounding:** no question ships without a traceable source location. If
  retrieval confidence is low, generate fewer questions, not ungrounded ones. This
  discipline is the product. Cite locations rather than reproducing passages.
- **No department-specific content from us:** the system contains no preloaded department
  documents. Users upload their own. BadgeDay ships zero content.

### Recruit only

- **Ships authored content by design.** The Command rules above do not apply: there is no
  upload, no retrieval, and nothing to cite. This is a deliberate departure, not an
  oversight — Recruit's users have no department documents to supply.
- **Expert review replaces citation grounding as the quality gate.** No Recruit item
  publishes without SME review. Since a candidate cannot check a Recruit question against
  a source the way they can a Command question, review is the only thing standing behind
  its accuracy.
- **Never depends on user-uploaded department materials.** See Product family above.

## Tech stack (use this; ask before deviating)

- **Backend:** Python 3.12+ / FastAPI
- **DB/Auth/Storage:** Supabase (Postgres, auth, file storage)
- **Doc processing:** Azure Document Intelligence (existing resource: `sts-docintel` in
  resource group `sts-examgen-rg`)
- **LLM:** Anthropic API (see Architecture decisions below for the model)
- **Payments:** Stripe (subscriptions + one-time 90-day pass)
- **Frontend:** React + Vite, Tailwind. Keep it simple; no SSR framework unless justified.
- **Hosting target:** Azure (align with existing sts infrastructure)

## Architecture decisions

Decisions made during scaffolding, with rationale. Change these deliberately, not
incidentally.

| Decision | Choice | Rationale |
|---|---|---|
| Generation model | `claude-sonnet-5` | Near-Opus quality on structured extraction at Sonnet cost. Supersedes `claude-sonnet-4-6` named in the original brief. Set via `GENERATION_MODEL`; never hardcode a model ID at a call site. |
| Data / auth / storage | Supabase Cloud | Row-level security enforces the per-user privacy constraint at the database, not in application code. |
| App hosting | Azure Container Apps | Matches the Azure target. Note: user documents live in Supabase Storage, not Azure Blob. |
| Background jobs | Postgres table + `SELECT … FOR UPDATE SKIP LOCKED` | Ingestion and generation are minutes-to-hours of work, not request/response. No Redis to operate; job state lives in the same database as everything else. |
| Auth flow | Magic link | No stored passwords, no reset flow, no password-reset support burden. |
| Document Intelligence | Behind a `DocumentAnalyzer` protocol | The chunker and citation resolver are testable against synthetic fixtures with no Azure account. Azure is an implementation detail behind the seam, not a test dependency. |

## Repo conventions

- Private repo. Secrets via `.env` + `pydantic-settings`, never committed. Maintain
  `.env.example` with variable names only.
- `.gitignore` includes: `.env`, `__pycache__/`, `.venv/`, `uploads/`, `*.pdf`, `*.docx`
  (no user/test documents in git history — test fixtures use small synthetic files in
  `tests/fixtures/` only, explicitly allowed via `!tests/fixtures/*`).
- Branch workflow: feature branches → PR → merge to main. No direct commits to main.
- Tests: pytest. The ingestion chunker and the citation resolver get real test coverage
  first — they are the two components where silent failure destroys the product.

## Build order

1. Scaffold: repo hygiene, FastAPI skeleton, health endpoint, config loading
2. Ingestion as a CLI-first pipeline: file → Document Intelligence → outline-aware chunks
   → stored with metadata (testable before any UI)
3. Generation: prompt + JSON schema + validation + citation resolution; golden-file tests
   with a synthetic SOG fixture
4. Supabase schema: users, documents, chunks, questions, sessions, responses
5. API endpoints wiring pipeline to storage
6. Minimal frontend: upload → generate → quiz → review loop
7. Stripe integration + gated access
8. Deploy pipeline to Azure

## Working style

- Propose ONE change at a time. For every code change, state the exact file, the exact
  location (function/line context), what it replaces, and what comes immediately before
  and after it.
- When a design decision has meaningful alternatives, present the options and a
  recommendation before implementing.
- Flag anything that drifts toward the out-of-scope list or the hard constraints instead
  of building it.
