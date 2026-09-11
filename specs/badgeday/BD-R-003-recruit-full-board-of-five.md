# BD-R-003 — Recruit: full board of five

Status: signed by Red 2026-09-11 (board-end/C1 display) — ready for Gyro
Red review: signed 2026-09-11 — board-end/C1 strings in AC17–AC19 (full review held in agent drafts)
§8: soft timer 2 min + daily=boards-started confirmed by Zazu 2026-09-11
Zazu handed Gyro 2026-09-11
Product: BadgeDay Recruit (not Promote, not DrillGround)
Repo: https://github.com/sirenstosyntax/BadgeDay
Authoritative: Grant START ORDER 2026-09-11 (via Zazu); supersedes 2026-09-10 hold on full-board *build* and non-C2 bank issue; session shape settled 2026-09-10; BD-R-001 / BD-R-002 remain for history and empty-bank UX
Author: Geppetto
Date: 2026-09-11
Audience: Red (board-end candidate-facing notes + C1 presentation), then Gyro (build), then Baymax (verify)

This spec defines behavior only. Table names, endpoints, libraries, and function names are Gyro's call except where an existing public contract must stay aligned.

Soft constraint: no real FD logos, insignia, apparatus, or facilities; no employer naming; no department-specific content.

---

## 1. User story

A signed-in pre-hire Recruit candidate can run one practice session as a **full oral board of five novel questions**, answer each out loud without seeing upcoming prompts, and only after the fifth answer receive the held per-answer critique notes plus a Criterion 1 (Answer Construction) whole-board pass — so practice matches a real board shape, free entitlement is one complete board (not one question), and they never optimize a single rehearsed item.

---

## 2. Scope

### In

- Session unit = **one board of five questions** (Grant lock).
- Free entitlement = **one complete five-question board** (not one delivered question-critique) (Grant lock).
- Critique cadence = **hold all candidate-facing notes until the board ends**; then show **per-answer notes + C1 whole-board pass together** (Grant lock). Internal scores / routes / determinations stay server-side (existing Recruit rule).
- **Phase 0:** wire live scorers for **C1–C5** and **publish the non-C2 bank** so the five-slot draw shape is real (not a C2-only fake board) (Grant lock).
- Draw / rotation (already settled in `recruit_question_bank.md`): one from each of **A · B/C · D/E/F · G/H · J**; never repeat prompt; no family within rolling **8** sessions; **70/30** weighted/random; **12-month retirement** preferred. ~272 reviewed prompts survive; live today is C2-only ~81 — publish gate opens with this START ORDER.
- Entitlements: free / daily ceiling count **boards** (Zazu default: ~**2 boards/day** UTC, replacing the 10 question-attempt ceiling).
- Soft timer only — **2 minutes per answer**, display guidance only; **no hard auto-submit** (Zazu confirmed 2026-09-11).
- Mid-board abandon = **incomplete board**; issued prompts count as **seen**; **no fake C1** on incomplete boards (Zazu default).
- Web UI: Q1–Q5 progress; no preview of upcoming questions; board summary only at end.
- API: start-board → next/current Q → submit audio → poll attempt; on board complete → run C1 and release held notes.
- Paid / Stripe live / Play Activate remain **HELD** — out of scope (Grant lock).
- Record START ORDER 2026-09-11 in `recruit_design_decisions.md` and `recruit_scope.md`.

### Out

- Enabling Stripe live, public Play SKUs, or changing Grant-held pricing.
- Promote quiz, DrillGround, department-specific content.
- Showing internal 1–5 scores, route tags, determinations, clause ids, or percentiles to the candidate.
- Re-record / retry a question inside a board.
- Preview of Q2–Q5 before their turn.
- Hard auto-submit when a timer expires.
- Fake C1 (or any whole-board summary) on abandoned / incomplete boards.
- Real-time voice critique between questions.
- Custom question entry, behaviors-acquired engine (BD-R-002 stubs stay as specified there).

### Recommended build phases (Gyro sequencing, not separate products)

1. Schema: boards + five attempt slots + abandon + C1 storage (internal).
2. Bank publish + rotation engine for draw shape (A · B/C · D/E/F · G/H · J).
3. Scorer wire C3 → C4/C5 → C1 whole-board (C2 already live); keep verification gates.
4. API: start-board → next Q → submit → poll; board complete → C1 → release notes.
5. Web UI: progress; hold notes; board-end summary.
6. Entitlements: free/daily = board unit (~2/day default).

### Smallest shippable slice (if Gyro must cut)

Minimum that still honors Grant locks: board of five with real multi-criterion draw (non-C2 published), hold notes until end, per-answer + C1 together, free = one complete board, daily boards ~2, abandon without fake C1. Soft timer UI can follow immediately after if needed.

---

## 3. Acceptance criteria

### Board lifecycle

1. Starting a Recruit practice session creates exactly one **board** with five **slots** (ordinal 1–5). It does not issue five questions up front to the client.
2. At any time the client sees at most the **current** slot’s question text. Upcoming slot prompts are never returned to the client before that slot is current.
3. Each slot is answered once (one recording). No re-record control on a finished slot.
4. After slots 1–4 are submitted, the next issuable question for the next draw group is issued for the following slot. After slot 5 is submitted and the board reaches a terminal complete state, no further mic Record for that board.
5. While a board is in progress, candidate-facing critique `lines` for completed slots are **not** shown (empty to the client even if the worker has finished). Lines are released only when the board is **complete**.
6. When the board is **complete** (five answers with verifiable critiques, or defined terminal policy for critique_failed — see edge cases), the client receives: per-answer candidate-facing notes for each slot **and** a C1 whole-board candidate-facing pass, in one board-end view.
7. Mid-board **abandon** marks the board incomplete. Issued scenario ids for that board count as **seen** for novelty. No C1 whole-board payload is generated or shown. No per-answer notes are released for that abandoned board (held forever for that board instance).
8. Incomplete boards never display a synthetic or placeholder C1 summary.

### Draw / bank

9. For a new board, the five slots draw **one prompt from each** group: **A**, **B/C**, **D/E/F**, **G/H**, **J** (per `recruit_question_bank.md`). A board that is five C2-only prompts is a **fail**.
10. Phase 0 publishes issuable non-C2 families needed for that draw shape (criteria with Grant-approved / publishable rubrics: C1–C5). C2-only ~81 hold is **superseded** for issue by this START ORDER.
11. Never re-issue a prompt the candidate has already been issued (including legacy `c2` wording alias rules already on main).
12. Do not repeat a **family** within a rolling window of **8** boards (sessions) for that candidate.
13. Selection among eligible items is **~70% weighted / 30% random** toward weaker tracked behaviors when that signal exists; until behavior tracking exists, random among eligible is acceptable but the 70/30 seam must exist.
14. **12-month retirement** preferred: a prompt issued ≥12 months ago may become eligible again. Until retirement is implemented, `next_eligible_at` may remain null; never-repeat still holds.

### Critique / C1

15. Each slot's answer is transcribed and critiqued against the criterion/criteria that item loads, with existing verification gates. Internal score/route/determination stay off the candidate payload (BD-R-001 rules).
16. C1 (Answer Construction) runs **once per completed board** across the whole board (audio/transcripts of the five answers), not once per question as the sole board score.
17. **Board-end presentation (Red signed 2026-09-11).** Hold-until-end confirmed: no drip between questions. Abandon = no notes, no fake C1. Order at board-end: framing → per-answer blocks Q1–Q5 → C1 whole-board block.

    Board framing (character-for-character):

    > Board complete. Notes held until the end on purpose — same as a real board.

    Per-answer blocks reuse BD-R-001 shape. BD-R-001 AC7 / AC8 character-for-character:

    > From what you said, this has not come up yet — so there is nothing here to judge you on, and this is not a mark against you.

    > There was not enough in that answer to say anything useful about it yet.

18. **C1 whole-board candidate-facing (Red signed 2026-09-11).** Lead (character-for-character):

    > Across these five answers — how they were built. Not a score on any one of them.

    Headings when points exist: `WHAT HELD ACROSS THE BOARD`; `WHAT STILL COSTS YOU UNDER PRESSURE` (sub-notes in Red review); `OUTSIDE WHAT THIS TOOL CAN HEAR` only when routing presence/eye contact to a person.

    Outside-tool line (character-for-character):

    > Presence, eye contact, and how you sit in the room are outside what this tool can hear. Work those with a mentor mock board, a station visit, or a ride-along — routes, not a booked provider.

    C1 not_answered (character-for-character):

    > There was not enough across these five answers to say anything useful about how they were built yet.

    C1 insufficient evidence (character-for-character):

    > From what you said across this board, there is not enough to judge how the answers were built — and that is not a mark against you.

19. **HARD BAN on board-end:** any 1–5, Delivery Clear/Costly/Blocking as grades, routes, determinations, rubric vocabulary.

### Entitlements

20. **Free:** a candidate with no Recruit entitlement may complete **one** complete five-question board (Grant). `recruit_free_sessions` semantics become **free boards**, default 1. Starting or abandoning does not consume the free board; **completing** a board with released notes does.
21. **Daily ceiling:** counts **boards started** per UTC day, default **2** (Zazu). Exceeding answers **429**. Replaces the default 10 question-attempt daily limit for Recruit practice.
22. Paid Recruit entitlement (`has_recruit_access` / entitlements recruit) still required after free boards are used. Promote entitlement does not grant Recruit (existing gate rule).
23. Stripe live / Play Activate / public paid offer go-live remain **out**; held pricing must not be enabled by this work.

### UI

24. Progress shows current index among five (e.g. question 2 of 5) without revealing future prompts.
25. Soft timer displays **2 minutes** of guidance time per answer; expiry does **not** auto-submit or auto-abandon.
26. Board-end summary is the first place per-answer notes and C1 appear for that board.
27. Empty-bank / exhausted (BD-R-002) still applies when no issuable novel prompts remain for the next slot; mid-board exhaustion is an edge case (see §5).

### Analytics / cost flags

28. Analytics may fire on board_started, board_completed, board_abandoned (names Gyro's call).
29. **Cost:** five transcriptions + five criterion critiques + one C1 whole-board critique per completed board (paid model usage). Schema migration for boards. Bank publish is content/config, not a new vendor.

---

## 4. Data model

Behavior-level persisted shape (names illustrative):

### Board

| Field | Type | Required | Notes |
|---|---|---|---|
| board_id | id | yes | |
| user_id | id | yes | owner |
| status | enum | yes | `in_progress` \| `complete` \| `abandoned` |
| started_at | timestamptz | yes | |
| completed_at | timestamptz | no | set on complete |
| abandoned_at | timestamptz | no | set on abandon |
| soft_timer_started_at | timestamptz | no | if soft timer used |
| c1_internal | structured | no | internal only; never client |
| c1_candidate_lines | string[] | no | released only when `complete` |

### Board slot (five per board)

| Field | Type | Required | Notes |
|---|---|---|---|
| board_id | id | yes | |
| ordinal | int 1–5 | yes | |
| draw_group | enum | yes | `A` \| `BC` \| `DEF` \| `GH` \| `J` |
| scenario_id | string | yes | issued prompt id |
| family | string | yes | for family-within-8 |
| criterion_ids | string[] | yes | rubric load(s) |
| attempt_id | id | no | link to attempt row when submitted |
| question_text | string | yes | frozen at issue |

### Attempt / critique

Reuse Recruit attempt + critique persistence (BD-R-001 path) with `board_id` + `ordinal` linkage. Candidate `lines` exist server-side when critique completes but are **withheld from read APIs** until board `complete`.

### Entitlement counters

| Counter | Counts | Default |
|---|---|---|
| Free boards used | completed boards with released notes | free allowance 1 |
| Daily boards | boards **started** UTC day | limit 2 |

---

## 5. API shapes (behavioral)

Exact paths are Gyro's call; contracts below are required.

### Start board

`POST .../boards` → `{ board_id, status: "in_progress", ordinal: 1, question: { scenario_id, question_text } }`  
Enforces Recruit access using **board** free/daily rules. Draws all five scenario ids server-side; returns only slot 1 text.

### Current / next question

`GET .../boards/{id}/current` → current slot question only, or terminal state.  
Never returns future slot texts.

### Submit answer

`POST .../boards/{id}/slots/{ordinal}/attempts` (audio) → 202 `{ attempt_id, status }`  
Poll attempt status as today, but `lines` remain `[]` until board complete.

### Abandon

`POST .../boards/{id}/abandon` → `{ status: "abandoned" }`  
Marks seen ids; no C1; no note release.

### Board read (end)

`GET .../boards/{id}` when `complete` →  
`{ status, slots: [{ ordinal, question_text, lines }], c1_lines: [...] }`  
When `in_progress` → no `lines` / no `c1_lines`.  
When `abandoned` → no `lines` / no `c1_lines`.

### Legacy single-question routes

`GET /recruit/question` + `POST /recruit/attempts` either: (a) become board-backed wrappers, or (b) are deprecated in favor of board routes in the same slice. Shipping both contradictory products (one-question free session vs five-question free board) is a **fail**.

---

## 6. Edge cases and failure handling

| Case | Behavior |
|---|---|
| Critique fails on one slot | Board cannot go `complete` with released notes until that slot is resolved per Gyro policy: retry worker **or** mark slot `critique_failed` and still allow board-end with a signed non-score failure line for that slot only — **no fake C1** if fewer than five assessable transcripts exist unless Red signs a degraded C1 rule. Default: block C1 until five transcripts exist or board abandoned. |
| Mid-board bank exhaustion | Cannot issue next slot → surface exhausted milestone (BD-R-002); board becomes incomplete/abandoned path; no fake C1. |
| Double-submit slot | Reject; keep first accepted recording. |
| Abandon after five critiques ready but before release | Still abandoned: no release, no C1. |
| Soft timer hits zero (2:00 guidance) | UI may warn; does not submit or abandon. |
| Free user completes board 1 | Free consumed; next start 402 without Recruit entitlement. |
| Free user abandons board 1 | Free not consumed; daily board count still incremented; prompts seen. |
| Entitled user hits 2 boards started today | 429. |
| Promote-only subscriber | No Recruit access (existing). |

---

## 7. Dependencies and prerequisites

- Auth + `has_recruit_access` gate (existing; must keep Promote-separate).
- Attempt/critique persistence and verification gates (BD-R-001 path).
- Grant-approved publishable rubrics C1–C5 on main; C2 already live.
- Reviewed bank (~272) with family/criterion metadata for publish.
- BD-R-002 exhausted UX when issue cannot fill a slot.
- Red sign-off on C1 whole-board **candidate-facing** lines and board-end composition.
- Docs lock PR: START ORDER 2026-09-11 in `recruit_design_decisions.md` / `recruit_scope.md` (supersedes 2026-09-10 “hold full board / hold non-C2 issue”).

**Supersession note:** The 2026-09-10 C2-only publish order held full board and non-C2 issue until scorer wire. This START ORDER **opens** full board build and non-C2 publish as Phase 0. Not a conflict requiring Grant — record as superseded.

---

## 8. Open questions / assumptions

1. **Soft timer duration** — **Settled by Zazu 2026-09-11:** **2 minutes** per answer, display guidance only; no auto-submit. (Design guidance ~1–2 min.)
2. **Daily = boards started** (not completed) — **Confirmed by Zazu 2026-09-11.** Counting completes only would open an abandon-abuse path.
3. **Free consumes only on complete board with released notes** — confirmed (AC20); start/abandon do not consume free.
4. **Degraded C1 when one of five critiques fails** — default block C1 until five transcripts or abandon (AC edge table). Not a Grant blocker.
5. **C1 candidate-facing copy** — **Signed by Red 2026-09-11** (see AC17–AC19). Full review signed 2026-09-11; strings locked in AC17–AC19.

No Grant decision blocking the build. Gyro cleared on display copy (Zazu handed Gyro 2026-09-11).

---

## 9. Test plan (Baymax / Gyro)

- Start board → only Q1 text; slots 2–5 hidden.
- Complete five answers → no notes until board-end; then five note sets + C1 lines.
- Abandon at Q3 → seen ids recorded; GET board has no lines/C1.
- Draw groups unique across A, B/C, D/E/F, G/H, J; fail if all C2.
- Free user: one complete board then 402; abandon then still free.
- Daily: third board start same UTC day → 429.
- Exhausted mid-board → no fake C1.
- Soft timer expiry does not POST audio.
- AC1 locked strings from BD-R-001 still character-for-character on released notes.
- Promote entitlement alone never passes Recruit board start.

---

## Hand-off

1. Docs: record START ORDER 2026-09-11 locks in design_decisions + scope (PR in flight / URL to Zazu).
2. Red: signed 2026-09-11 — board-end framing, C1 lines, hold-until-end, hard ban on scores/bands. Strings in AC17–AC19 character-for-character.
3. Gyro: Zazu handed priority build; implement phases; emit Red-signed strings character-for-character; do not enable paid go-live.
4. Baymax: verify ACs above, especially hold-until-end, signed strings, draw shape not C2-only, free/daily board units.
