# BadgeDay — Project Brief

## What this is

BadgeDay is a B2C subscription product under Sirens to Syntax LLC serving firefighters at
two different career moments. Consumer brand — completely separate from DrillGround
(B2G). Domains: badgeday.com / badgeday.app. Social: @badgedayapp.

## Product family

BadgeDay has two parts. **They are architecturally different products sharing a brand, an
account layer, and a billing layer.** Do not assume a pattern from one transfers to the
other — in particular, the citation-grounding discipline that defines Promote has no
equivalent in Recruit, and the "we ship zero content" rule is Promote-only.

### BadgeDay Promote — promotional exam prep (built and deployed)

For serving firefighters testing for Lieutenant / Captain / Battalion Chief. The
candidate uploads their department's announced promotional reading list (their own public
documents: SOGs listed on the exam announcement, standard published texts) and BadgeDay
generates cited practice questions from those exact documents, with a quiz interface that
tracks coverage until nothing on the list can surprise them.

**Pitch:** "Upload your reading list. Drill cited questions until badge day."

**Shape:** RAG over user-uploaded documents. BadgeDay ships zero content. Every question
carries a citation resolvable to a stored chunk.

### BadgeDay Recruit — pre-hire preparation (building now)

For candidates who have not been hired yet and are working to become competitive: no
department, no reading list. Formerly referred to as "BadgeDay Entry."

Detailed scope and build order: **`recruit_scope.md`**. Settled design decisions and the
reasoning behind them: **`recruit_design_decisions.md`** — that file is authoritative
where the two disagree.

Recruit helps candidates develop the attributes departments hire for — through practice
tests, mock interviews, teaching of foundational principles common to all departments,
and the common traps that keep candidates from getting hired.

**Shape:** coaching and feedback against expert-authored rubrics — not a question bank.
The candidate answers a question aloud and the answer is transcribed. There is no user
upload, no retrieval, and no citation chain.

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

**Explicitly not the Promote model:** Recruit must NOT be built to depend on the
candidate uploading department hiring materials. A pre-hire candidate has no such
documents, and requiring them would gate the product on something its users do not have.

## What launch means — both modules

**Decided 2026-07-26: BadgeDay does not go live with real payments until Promote and
Recruit are both built.** The brand and the marketing site address both audiences, so
shipping one alone advertises the other to a waitlist that cannot buy it. Stripe stays in
**test mode** until both are ready.

This supersedes the original "Promote only, do not build Recruit" scoping. Promote is
built and deployed at app.badgeday.com; Recruit is the remaining work and is now on the
critical path to any revenue.

**Reaffirmed 2026-08-16, when the app-store decision was taken.** Going into the stores
does not open the gate early. The store work runs *alongside* Recruit rather than ahead of
it, because most of what it costs is waiting — developer-account enrolment, a D-U-N-S
number, closed testing — and waiting is the one thing that parallelises. Nothing in
`mobile_release_plan.md` should be read as a reason to take real money before Recruit
ships.

### Promote — built (what shipped)

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
- **Legal:** privacy policy and terms served at /privacy and /terms, linked from the
  footer, the sign-in screen and the paywall.

Still open on Promote, none of it blocking Recruit: **transactional email for magic
links** (Supabase's default sender is rate-limited and spam-prone — needs a provider
account, so it is blocked on a signup rather than on code), and **cost-per-document
measured against a real SOG** (blocked on a real document).

Closed 2026-07-28: **reporting a wrong question** (`POST /questions/{id}/report`,
migration 0006) and **noticing a dead job** (an ERROR log at the point a job spends its
last attempt, plus the `dead_jobs` view). Both existed because the product had no way to
tell anyone it was broken — verification proves a question is cited, never that it is
right, and a job that exhausted its retries stopped silently while a candidate waited.

### Recruit — to build

Anchored on the oral board and on candidate-readiness gap analysis, per Product family
above. Coaching against expert-authored rubrics, not a question bank. Scope and build
order live in **`recruit_scope.md`**; settled decisions live in
**`recruit_design_decisions.md`**. Read both before writing Recruit code, and do not infer
Recruit's shape from Promote's.

## Explicitly OUT of scope

- **Real-time or conversational voice** — streaming ASR, a simulated panelist that talks
  back, avatars, follow-up questioning. Still V2; do not scaffold it. Recruit V1 records a
  spoken answer and transcribes it in batch. Recording an answer is in scope; holding a
  conversation is not. (Reversal of the earlier "text-based only" line, 2026-07-27 —
  see `recruit_design_decisions.md` §5.)
- **Voice-based confidence or emotion scoring.** Not a schedule decision — a permanent
  one. Unreliable, and biased by accent, gender, and first language. See the binding
  constraints at the end of this file.
- Written-exam practice in Recruit (most commoditized, worst risk-to-differentiation —
  see Product family above). Last, if at all.
- Department/team accounts of ANY kind (see firewall below)
- ~~Native mobile apps (responsive web only)~~ — **reversed 2026-08-16.** BadgeDay is going
  into both stores, as wrappers around the same web app: a Trusted Web Activity for Play and
  Capacitor for iOS. There is no second product codebase and there must not be one — the
  wrappers add native capabilities (upload from Files and camera, offline practice, local
  notifications, store purchase) around the app that already exists. A React Native or Swift
  rewrite is still out of scope. Everything about the release lives in
  **`mobile_release_plan.md`**; read it before touching either wrapper or anything under
  `app/billing/store*`.
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
  to improve prompts/models, hard-deletable. The same applies to Recruit's voice
  recordings, which are additionally **transcribed, measured, and discarded** unless the
  candidate opts in to keeping them for self-review — voice is sensitive in a way typed
  answers are not, and several states regulate it specifically.

### Promote only

- **Citation grounding:** no question ships without a traceable source location. If
  retrieval confidence is low, generate fewer questions, not ungrounded ones. This
  discipline is the product. Cite locations rather than reproducing passages.
- **No department-specific content from us:** the system contains no preloaded department
  documents. Users upload their own. BadgeDay ships zero content.

### Recruit only

- **Ships authored content by design.** The Promote rules above do not apply: there is no
  upload, no retrieval, and nothing to cite. This is a deliberate departure, not an
  oversight — Recruit's users have no department documents to supply.
- **Expert review replaces citation grounding as the quality gate.** No Recruit item
  publishes without SME review. Since a candidate cannot check a Recruit question against
  a source the way they can a Promote question, review is the only thing standing behind
  its accuracy.
- **Never depends on user-uploaded department materials.** See Product family above.
- **Further binding constraints** on scoring, critique generation and the practice loop
  are listed at the end of this file, with rationale in `recruit_design_decisions.md`.

## Tech stack (use this; ask before deviating)

- **Backend:** Python 3.12+ / FastAPI
- **DB/Auth/Storage:** Supabase (Postgres, auth, file storage)
- **Doc processing:** Azure Document Intelligence (existing resource: `sts-docintel` in
  resource group `sts-examgen-rg`)
- **LLM:** Anthropic API (see Architecture decisions below for the model)
- **Speech-to-text (Recruit):** batch ASR with word-level timestamps and preserved
  disfluencies. Provider not yet chosen — read the implementation warnings in
  `recruit_design_decisions.md` §5 before selecting one; both requirements are commonly
  unmet by default.
- **Payments:** Stripe on the web (subscriptions + one-time 90-day pass). **Inside the
  phone apps, the store's own billing** — Play Billing and StoreKit — because both stores
  require it for a digital subscription sold in-app. Same two products, same entitlement,
  different till; the split is in `app/billing/store*` and the reasoning in
  `mobile_release_plan.md`.
- **Frontend:** React + Vite, Tailwind. Keep it simple; no SSR framework unless justified.
- **Mobile:** wrappers around that same frontend — Trusted Web Activity (Play), Capacitor
  (iOS). Product code is never forked per platform.
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

Promote — all eight complete, kept for the record of how it was built:

1. ~~Scaffold: repo hygiene, FastAPI skeleton, health endpoint, config loading~~
2. ~~Ingestion as a CLI-first pipeline: file → Document Intelligence → outline-aware chunks
   → stored with metadata (testable before any UI)~~
3. ~~Generation: prompt + JSON schema + validation + citation resolution; golden-file tests
   with a synthetic SOG fixture~~
4. ~~Supabase schema: users, documents, chunks, questions, sessions, responses~~
5. ~~API endpoints wiring pipeline to storage~~
6. ~~Minimal frontend: upload → generate → quiz → review loop~~
7. ~~Stripe integration + gated access~~
8. ~~Deploy pipeline to Azure~~

Recruit — see `recruit_scope.md`. It shares this repo, this stack, and Promote's auth and
billing layers, but nothing of its ingestion or retrieval architecture.

## Working style

- Propose ONE change at a time. For every code change, state the exact file, the exact
  location (function/line context), what it replaces, and what comes immediately before
  and after it.
- When a design decision has meaningful alternatives, present the options and a
  recommendation before implementing.
- Flag anything that drifts toward the out-of-scope list or the hard constraints instead
  of building it.

## Recruit — binding constraints

Read `recruit_design_decisions.md` before changing scoring, critique
generation, or the practice loop. Rationale and superseded decisions
are recorded there.

- Never generate model answers, sample language, or example responses.
  Critique names what is missing and asks for the candidate's own material.
- Every practice session uses a question the candidate has not seen.
  No preview, no re-record. The post-take Record again control was
  removed 2026-09-09 (Grant) so the UI matches this constraint.
- Do not score answers independently and sum them.
- Do not build voice-based confidence or emotion detection.
- Scores are internal. Report progress as behaviors acquired, not as a number.
- The rubric's vocabulary is internal too. A candidate never reads the name of
  a criterion, an anchor, a scoring note, a clause id or a route tag.
