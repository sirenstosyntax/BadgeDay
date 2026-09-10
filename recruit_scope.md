# BadgeDay Recruit — Scope

*Working scope for the pre-hire module. Read `CLAUDE.md` first for the product family, the
hard constraints, and the stack. Drafted 2026-07-26; the open questions at the bottom are
unanswered and some of them block build order.*

> **Revised 2026-07-27.** A working session settled the practice loop, the input medium,
> and the critique constraints, and reversed three things this document originally
> specified: text input became audio, the retry-the-same-question loop became a novel
> question every session, and critique lost the ability to describe a stronger answer.
> Those sections below are updated. **`recruit_design_decisions.md` is authoritative
> where it and this file disagree** — it carries the rationale and the record of what was
> rejected, so read it before reopening any of them.

## What Recruit is

Preparation for candidates who have **not been hired yet** and are working to become
competitive. No department, no reading list, no documents of their own.

Recruit is anchored on **the oral board** and on **candidate-readiness gap analysis**,
because that is where candidates are actually eliminated: most who reach the oral board
have already passed the written, and the next largest group is eliminated for being
uncompetitive on paper — no EMT, no coursework, no volunteer time — in ways that are
fixable 6–18 months out. Foundational principles and common traps are supporting content.

## The one thing to get right

Promote's discipline is citation grounding: no question ships without a source location a
candidate can open their own document to. That discipline is what makes it trustworthy,
and Recruit **has no equivalent** — there is no upload, no retrieval, and nothing to cite.

So Recruit needs its own answer to the same question, because the failure mode here is
worse. A bad Promote question is checkable: the candidate opens the SOG and sees we were
wrong. Bad Recruit feedback is **confident career advice to someone who cannot check it**,
delivered at the exact moment they are most anxious and most inclined to believe it.

The answer is the rubric:

> **Every piece of feedback traces to a named criterion in an SME-reviewed rubric.** The
> model's job is to apply a rubric, not to have opinions about fire service hiring. A
> critique that cannot point at the criterion it came from is a defect, exactly as an
> uncited question is in Promote.

This is the architectural spine of the module. It is what makes the reviewable asset
**bounded and stable** — a fixed set of rubrics — rather than an ever-growing library of
items that each need review and each decay as hiring practice shifts. It is also what
keeps the model on a leash: rubric in, criterion-referenced critique out, no free-roaming
advice about somebody's career.

## V1 scope

Three pillars, in the order they matter.

### 1. Oral board practice (spoken, recorded)

The core loop, and the reason someone subscribes.

- The candidate is given a scenario or question drawn from an SME-authored set. **It is a
  question he has not seen. No preview, no browsing the bank.**
- He answers **aloud**, on a clock. The browser captures audio; batch ASR returns a
  transcript with word-level timestamps; delivery metrics are computed from those
  timestamps in our own code. **No re-record.**
- He gets a structured critique **against the rubric for that question type**: what the
  panel is listening for, which criteria the answer hit, which it missed, and what is
  absent that the candidate would need to supply. Each point names its criterion or the
  metric it came from.
- Progress is shown across **different** questions over time — behaviors that held up and
  behaviors that drop out under pressure — not two attempts at one question side by side.

Not a score out of 100, and not a score shown at all. A 1–5 score exists to structure the
critique and stays internal; the candidate sees criterion-referenced feedback and
behaviors acquired. A surfaced number invites him to optimize the number and tells him
nothing about what to say differently.

**Why not text, and why not a retry** — this reverses the original scoping and the
reasoning is in `recruit_design_decisions.md` §4–5. In short: the skill a board tests is
constructing an answer to something you have not seen, right now. Repeating a question
trains a candidate to be excellent at that one question and leaves him back at square one
on the next; allowing a re-record converts construction into rehearsal, so the skill never
gets exercised. And text cannot see pace, fluency, hesitation, or length — a real part of
what a panel is reacting to.

**What the critique may not do:** supply content. It names what is missing and asks for
the candidate's own material; it never provides a model answer, sample language, or an
example response. The level 3 anchor is the clone answer — correct, generic,
indistinguishable — and a coaching tool that hands out language manufactures clone answers
at scale. This is the most-requested feature that must not be built.

### 2. Readiness gap analysis

A structured self-assessment producing a **prioritized, time-phased plan**: what this
candidate should fix in the next 6, 12, and 18 months to stop being screened out on
paper, hardest-hitting gap first.

This is the module's on-ramp — it is fast, it delivers something concrete on day one, and
it tells a candidate why they need the rest. It also **personalizes the oral board
coaching**: a candidate with no EMT and no fire academy gets different advice about how to
handle "why should we hire you" than one who has both.

Scored against an SME-authored rubric like everything else here, not against the model's
impressions of what departments want.

### 3. Foundational principles and common traps

Supporting content: the principles common to all departments, and the mistakes that keep
otherwise-good candidates from getting hired. SME-reviewed, and deliberately smaller than
the two pillars above — this is what a candidate reads between practice attempts, not the
product itself.

### Explicitly out of scope for Recruit V1

- **Real-time or conversational voice.** Streaming ASR, a panelist that talks back,
  avatars, follow-up questioning. V2. Recording a spoken answer and transcribing it in
  batch is **in** scope as of 2026-07-27; holding a conversation is not.
- **Voice-based confidence or emotion scoring.** Permanently out, not deferred —
  unreliable and biased by accent, gender, and first language.
- **Retrying a question the candidate has already answered.** See §1 and
  `recruit_design_decisions.md` §4. Rehearsal is the failure mode, not the feature.
- **Any critique that supplies language for the candidate to use.** Model answers, sample
  phrasing, example responses.
- **Written-exam practice.** Most commoditized part of the market, worst
  risk-to-differentiation ratio, and where the copyrighted commercial batteries live.
  Last, if at all.
- **Any dependence on user-uploaded documents.** A pre-hire candidate has none. This is
  the single most likely way for Promote's shape to leak across, and it would gate the
  product on something its users do not have.
- **Department-specific content.** We do not model any particular department's hiring
  process. Principles that generalize, or nothing.

## Hard constraints that bite hardest here

From `CLAUDE.md`, restated because Recruit is where the temptation is greatest:

- **No commercial hiring-test batteries as a source.** Nothing derived from National
  Testing Network / FireTEAM, IPMA-HR, CPS HR or equivalents. Testing the same underlying
  *abilities* with original material is fine; tracking a specific published battery's
  structure, sections, or content is not. If a rubric starts to look like a reproduction
  of somebody's product, it is one.
- **No licensed standards** (NFPA, IFSTA and equivalents) as a grounding source.
- **SME review is the quality gate.** No rubric, scenario, or principle publishes without
  it. A candidate cannot check Recruit content against a source the way they can check a
  Promote question, so review is the only thing standing behind its accuracy.
- **Individuals only.** The buyer firewall applies unchanged. No department-facing
  feature, no candidate-screening tool sold to the hiring side. Recruit helps the person
  applying, never the panel.
- **Original words.** Feedback and content are written originally, never long verbatim
  extracts.

## Architecture

Decisions I am making by default. Change them deliberately.

| Decision | Choice | Rationale |
|---|---|---|
| Where it lives | Same repo, same FastAPI app, same Supabase project, same React app | Shared auth and billing is the entire reason these are one brand. Two deployments would double the operations for no user-visible gain. Module selection is a UI concern. |
| Data model | New tables — rubrics, scenarios, attempts, critiques, assessments | Do **not** reuse `documents` / `chunks` / `questions`. Different shape, different lifecycle, different quality gate. Reuse there would couple two products that only share a login. |
| Content storage | Version-controlled files in the repo, published into the database | SME review needs diffs, history, and a record of who approved what. A rubric typed straight into a table has no reviewable form. Mirrors how DrillGround handles its library. |
| Critique execution | The existing Postgres job queue, with the client polling | A critique is 10–30 seconds of model time — longer now that transcription precedes it — which risks an ingress timeout on a plain request but is short enough that the candidate waits on the screen. The queue is built, tested, and already handles retry and failure; adding a second async mechanism would be the mistake. |
| Audio path | Browser capture → batch ASR with word-level timestamps → deterministic metrics computed in our own code → transcript **and** metrics into the critique step | No streaming, no real-time; a mock board does not need sub-second latency. Most of the delivery signal is arithmetic on timestamps — words per minute, time-to-first-word, pause count and position, filler rate, longest unbroken stretch — not audio ML. Deterministic, zero run-to-run variance, comparable across sessions. See `recruit_design_decisions.md` §5–6. |
| Audio retention | Transcribe, compute, discard. Retained only on explicit opt-in for self-review. | Voice is sensitive in a way typed answers are not and several states regulate it specifically. Playback of a candidate's own answer is likely a strong feature, but it is opt-in, not a reason to keep everything. |
| Scoring shape | Answers are **not** scored independently and summed | Real panels build a picture: a flag raised early shapes how later answers are read. A pipeline that scores each answer in isolation and adds them up will not reproduce board behavior. |
| Model role | Applies a rubric to an answer. Never authors a rubric that reaches a candidate unreviewed. | The bounded-reviewable-asset argument only holds if the asset stays bounded. A model may *draft* rubric candidates for SME review — that is generation into the review chain, not publication. |
| Entitlement | **Per-module.** `entitlements` keyed on (user, module) — migration 0012, ship gate #4. Recruit reads this table via `has_recruit_access`. Promote's live path still uses profiles + store_purchases / `has_access`. | Recruit is a separate plan (decided 2026-07-26), so one entitlement per account no longer expresses what a candidate has bought. A table beats adding `promote_*` / `recruit_*` column pairs: a third module would need another migration and every gate would need editing, where a row does not. Keep the service-role-only write rule from migration 0005 — a candidate must not be able to grant themselves either module. Pricing is held; checkout is not open. |
| Stripe mapping | Price ID → module, resolved server-side from config (`app/billing/module.py`) | Recruit has its own held price IDs alongside `STRIPE_PRICE_ID_MONTHLY` / `STRIPE_PRICE_ID_INTENSIVE_90DAY`. The webhook must decide *which module* a completed checkout grants. Mapping is in place; checkout is not open until Grant says go live. |
| Testing | The critique pipeline gets real coverage first, against fixture rubrics and fixture answers | Same reasoning as Promote's chunker and citation resolver: it is the component where silent failure destroys the product. A critique that quietly stops referencing criteria still *looks* like good feedback. |

### On reusing DrillGround's review chain

DrillGround already runs generate → ingest → sme-review → revise → publish over a content
library, and Recruit needs something with the same shape. Worth an hour of evaluation
before building anything new — but probably not worth lifting wholesale. Recruit's
reviewable surface is a bounded set of rubrics and scenarios, not an 87-item and growing
drill library, and DrillGround's machinery is sized for the latter. Expect to want a
lighter review record in this repo rather than a port.

## Build order

The riskiest assumption in this module is **whether a model applying an SME-authored
rubric produces feedback a fire captain would put his name to**. Everything else is
plumbing we have already proven once. So test that first, before any UI, exactly the way
Promote's pipeline was CLI-testable before it had a frontend.

1. ~~**One rubric, authored and SME-approved.**~~ **Done 2026-07-27** — Criterion 2,
   Motivation & Preparation, in `recruit_rubric_c2_motivation.md`. Hand-authored anchors,
   1–5, with a 4A/4B route split, and a 3/4B boundary tightened after the noise-floor run.
   - **Criterion 3 (Teamwork) Grant-approved / publishable 2026-09-10** in
     `recruit_rubric_c3_teamwork.md` after Grant’s captain text pass (adjacent bands kept
     as drafted; clean 1–5, no route tags). It exists to close the gap Criterion 2
     recorded: its level 2 anchor catches the qualified self-focused candidate. That gap
     is closed. Criteria 1–5 are all Grant-approved / publishable for scoring docs (C2
     already SME-approved). Bank growth, five-question board *build*, and live scorer
     wire remain held until Grant opens them — do not invent a start order.
2. ~~**The critique pipeline, CLI-first.**~~ **Built 2026-07-28** — `app/critique/`,
   exercisable now with `badgeday-critique --rubric c3 --all-fixtures`. Rubric clauses are
   parsed out of the markdown rather than kept beside it, so a point cites `c3.anchor.2`
   the way a Promote question cites a section number, and the gate checks that clause
   actually exists. Six checks: anchoring, supplied language, grounding in the transcript,
   internal-state attribution, score disclosure, and — added from the 2026-08-06 calibration
   review — rubric vocabulary, which stops the instrument talking about itself to a candidate
   who has never seen it. The measurement seam exists but nothing computes metrics yet —
   that is step 5.
   - **First live run: 8/8 fixtures across both rubrics produced verified critiques**, one
     attempt each, no rejections. It also found a false positive in the gate — apostrophes
     in contractions were being read as quote delimiters, so *"a policy change he'd make …
     what you've learned"* was rejected as a scripted phrase. Fixed, with the failing string
     pinned as a regression test. Worth noting the shape: the gate's *false* rejections cost
     as much as its misses, because each one either loses a sound point or spends a retry.
   - **Two runs disagreed about an off-topic answer** — not assessable once, 1 the other
     time. Logged as an open item; see below. The original spec text follows.

   *(original)* Transcript + metrics + rubric in,
   criterion-referenced critique out. Structured JSON, schema-validated, with a
   verification gate that **rejects any critique point not tied to a criterion or to a
   computed metric** — the direct analog of Promote's citation verification. Two classes
   of point flow through it: rubric-anchored and measurement-anchored, the second being
   trivially verifiable and worth preferring where it applies. The gate must also reject
   points that supply language to the candidate. Golden-file tests against fixture
   answers: a strong one, a weak one, an off-topic one, an empty one.
   - ~~**Before this step: measure the scorer's noise floor.**~~ **Run 2026-07-27**
     (`scripts/recruit_noise_floor.py`). Perfectly stable on unambiguous answers — twenty
     runs, twenty identical scores. At the 3/4B boundary it moves by one anchor on a
     quarter of runs, and the disagreement is a specific ambiguity in the rubric's
     *"something to show for it"* clause rather than model noise. Full result in
     `recruit_design_decisions.md` §7. It does not block this step; it confirms that
     progress must be reported as behaviors rather than a score, and it handed Criterion 2
     one anchor to tighten. **Tightened and re-run 2026-07-28: 60 runs, zero variance, with
     the 4B band still reachable.** One case the tightening does not cover is logged there.
3. **SME judgment on the output.** Grant reads real critiques of real answers and says
   whether they are good enough to ship. *This is a decision gate, not a step.* If the
   answer is no, the rubric or the prompt changes and we repeat — no UI gets built on top
   of feedback the SME would not give.
   - The bar is now comparative, not absolute: **stationvisit.com** already ships
     AI-scored mock firefighter oral boards across five dimensions, free first interview
     and subscription thereafter. So the question is not "is Recruit worth building" but
     "do critiques from these anchors read as materially better than what exists" — a
     cheaper question, answerable before the pipeline is finished.
4. **Content set.** Enough scenarios and rubrics across question types to make a practice
   session worth having, each through review. The novel-question-every-session rule makes
   **bank depth a hard requirement**, not a nice-to-have: size and rotation policy are
   undetermined and need settling here.
5. **Audio capture and transcription.** Browser recording, batch ASR with word-level
   timestamps, the deterministic metrics computed in our code, opt-in retention. Verify
   disfluency preservation on our own audio first — most ASR strips "um" and "uh" by
   default, which is the most likely silent failure in the feature.
6. **Schema and API.** Tables, RLS on the same per-user pattern as Promote, endpoints for
   question issue → attempt → critique. No retry endpoint.
7. **Readiness gap analysis.** Intake, scoring against its rubric, the time-phased plan.
8. **Frontend.** Module selection, the practice loop, attempt history, the plan view,
   progress reported as behaviors acquired rather than a rising number.
9. ~~**Entitlement wiring**, per the packaging decision (separate plan — see Settled).~~
   **Table and Recruit gate landed 2026-09-09 (ship gate #4).** `entitlements(user,
   module)`, `has_recruit_access` reads that table, price/SKU placeholders are blank.
   Checkout is not open; Stripe stays in test mode until Grant says go live.

Steps 2–3 are small, cheap, and answer the question that decides whether the rest are
worth doing.

## Settled

**Packaging — Recruit is a separate plan** (2026-07-26). Not a bundle, not one BadgeDay
subscription covering both. The audiences barely overlap: a serving firefighter testing
for Lieutenant is not a pre-hire candidate, so a combined plan would sell each buyer half
a product they will never open. See the entitlement and Stripe rows above for what that
means structurally.

**The SME is Grant, working alone** (2026-07-26). There is no second reviewer on the
project and none expected in the near term. That is workable, but it has to shape how the
content is written rather than be quietly ignored:

- **Author only what generalizes.** Do not model any particular department's scoring
  sheet — that is the part that varies, that dates, and that a solo author cannot keep
  current. Write to what any panel is listening for: whether the candidate answers the
  question actually asked, whether they show they understand the job, whether the
  attributes come through, whether they walk into the common traps. Twenty years and a
  captain's rank is strong ground for exactly that, and weaker ground for "here is how
  Department X scored oral boards last cycle." Stay on the strong ground.
- **Calibrate against public material.** Many departments publish their oral board
  dimensions and candidate handbooks openly as part of a hiring announcement. Reading
  several and writing rubrics to what they have in common is legitimate grounding, costs
  nothing, and is a different act from tracking a commercial battery — which stays
  prohibited. Same discipline DrillGround uses: public sources, original words. A first
  pass over four departments is in **`recruit_oral_board_sources.md`**, along with the
  screening rule it turned up: much of what a city publishes about its oral board was
  written by a testing vendor and is off limits despite the `.gov` address.
- **Do not let this block step 1.** Author the first rubric yourself and run the pipeline.
  A second reviewer is far easier to recruit against a finished, bounded artifact than
  against a blank page, and the rubric architecture is what makes that ask small — a fixed
  set of rubrics is a weekend of someone's attention, where an ever-growing question bank
  would be a standing commitment nobody would accept. *Done — Criterion 2 exists, and it
  is the artifact to recruit a second reviewer against.* The remedy for single-panelist
  bias is **more panelists, not more web content**: two or three captains from departments
  with differing board formats, scoring against these anchors independently. Agreement
  indicates trade-wide judgment; disagreement gets documented as a split rather than
  averaged away. The 4A/4B route split in particular came out of a single pass and wants a
  second panelist before it is settled.
- **Claim exactly what is true.** Content authored by a fire captain with over twenty
  years in the service is real credibility and is worth saying plainly. It is not a
  department's scoring sheet and must never be presented as one.

Revisit if a second reviewer becomes available; the review gate stays in the architecture
either way.

## Open questions — these need Grant

1. ~~**How prescriptive is the gap analysis?**~~ **Settled 2026-07-28: offer possible ways the improvement could be met — plural, routes not providers, spanning the cost and access range.** See `recruit_design_decisions.md` §3. Original text follows.

   *(original)* **How prescriptive is the gap analysis?** Naming specific certifications and programs
   is far more useful to a candidate and carries more accuracy risk than general
   categories. Where is the line? **This now gates more than it did.** The critique step
   classifies every point as improving the answer or improving the candidate
   (`recruit_design_decisions.md` §3, 2026-07-28), so development advice is produced at
   step 2 rather than waiting for step 7. Until the line is set, the pipeline runs a
   conservative interim default — a development point names what is absent and may name
   the category, but the gate rejects a specific certification, programme or provider.
   Relaxing that is one regex and a prompt line; deciding how far to relax it is not.
2. ~~**Does Recruit launch with all three pillars or with the oral board alone?**~~
   **Settled 2026-07-29 by Grant: all three pillars at launch.** The recommendation below
   was to ship two and grow the third; it was overruled deliberately, on the grounds that
   the product must launch with real value rather than with a defensible minimum.

   What that costs, recorded so it is not a surprise: pillar 3 is the cheapest of the three
   and the least risky, so the schedule impact is smaller than it looks — but **the binding
   constraint is not pillar 3, it is rubric coverage.** C1–C5 are Grant-approved /
   publishable for scoring docs (C2 already SME-approved; C3 Grant-approved 2026-09-10
   after the captain text pass). Bank growth, five-question board *build*, and live scorer
   wire remain held until Grant opens them — implementation hold, not a rubric hold. Do
   not invent a start order.

   Pillar 2 additionally becomes the free tier — see `badgeday_pricing.md`. That raises its
   quality bar (it is now the first thing a stranger sees) without changing its scope.

   *(original recommendation)* Oral board plus a thin gap analysis, with principles and
   traps growing after launch — the first two are the product, the third is what makes it
   feel complete.
3. ~~**What does Criterion 1 get called?**~~ **Settled 2026-09-10: Answer Construction**
   (not Communication). Structure: clean 1–5 construction (no 4A/4B); Delivery three-band
   Clear/Costly/Blocking; owns-a-miss on the 5; practice sessions = full board of five;
   whole-board scoring. **Grant-approved / publishable 2026-09-10** (adjacent bands kept
   as drafted). C4 named **Integrity & Ethics** — **Grant-approved / publishable
   2026-09-10** (adjacent bands kept as drafted). C5 named **Judgment & Composure** —
   **Grant-approved / publishable 2026-09-10** (adjacent bands kept as drafted). See
   `recruit_design_decisions.md` §10 Settles 2026-09-10.
4. ~~**Question bank size and rotation policy.**~~ **Proposed 2026-07-29 in
   `recruit_question_bank.md`** — 36 evidenced question families, target ~290 prompts at
   launch (36 families × 8 variants) growing to ~500, with 12-month retirement for
   exhaustion, no prompt ever repeated, no family within a rolling 8 sessions, and 70/30
   weighted/random selection. Needs your sign-off, and the family list needs SME review
   before any of it publishes.

   The reason a large bank turns out to be affordable: **a Recruit question is an unkeyed
   prompt** — no answer, no distractors, no citation — so per-item review is seconds rather
   than minutes, and the judgment lives in the family rather than the variant. The
   reviewable asset stays bounded.

   *(original)* A hard requirement now rather than a detail, because a novel question every
   session means the bank has to outlast a subscription. Needed at step 4.

5. ~~**Does a practice session issue one question or a full board of five?**~~
   **Settled 2026-09-10: full board of five** (session shape). Whole-board scoring for C1.
   Five-question board *build* remains held until Grant opens it — implementation not
   started. Session shape is settled. See `recruit_design_decisions.md` §10 Settles
   2026-09-10.
