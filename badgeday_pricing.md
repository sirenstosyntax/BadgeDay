# BadgeDay — Pricing and Competitive Position

*Recruit and Promote pricing, and what "materially better than Station Visit" has to mean
concretely. Drafted 2026-07-29. Amounts live in Stripe / store products and are never
printed in the app (`web/src/ui/Paywall.tsx`). Recruit paid go-live wire is approved
(START ORDER 2026-09-11); Recruit live price/product IDs remain ops. Promote paid
go-live is approved (START ORDER 2026-09-11 evening); Promote live Stripe prices
are ops-filled.*

---

## START ORDER 2026-09-11 — Recruit paid go-live approved

**Go-live wire approved for Recruit.** Grant opened Recruit paid go-live on 2026-09-11:
checkout may ship; Stripe live mode and Play product-stub Activate are approved for
Recruit. Live Stripe price IDs and Play / App Store product IDs remain **ops to fill**
(Zazu). Env vars may still be blank placeholders until those IDs land — do not invent
IDs in this file. Blank placeholders are expected.

**Promote** paid go-live was opened later the same day — see the Promote subsection
below. Do not treat this Recruit order as holding Promote.

| Module | Offer | Locked amount |
|---|---|---|
| **Recruit** | First oral-board session | Free, no card (`RECRUIT_FREE_SESSIONS=1`) — one complete five-question board |
| **Recruit** | Monthly | **$24.99/mo** — `STRIPE_PRICE_ID_RECRUIT_MONTHLY` / Play / App Store counterparts |
| **Recruit** | 90-day pass | **$59** — `STRIPE_PRICE_ID_RECRUIT_INTENSIVE_90DAY` |
| **Recruit** | 6-month | **$119** — `STRIPE_PRICE_ID_RECRUIT_6MONTH` / Play / App Store counterparts |
| **Recruit** | Annual | **$179/yr** — `STRIPE_PRICE_ID_RECRUIT_ANNUAL` |

On 2026-09-10 Grant reconciled the $119/$179 conflict to the July competitive pairing:
**$119 is 6-month, not annual; $179 is annual.** Monthly ($24.99) and the 90-day pass ($59)
are unchanged. The 2026-09-09 table had named $119 as annual and had no 6-month SKU; that
naming is superseded.

The 2026-07-29 recommendation below ($29 / $119 six-month / $179 annual, no 90-day) remains
the reasoning record. Grant locked the six-month and annual amounts from that pairing; he
did not adopt $29 monthly or drop the 90-day row.

---

## START ORDER 2026-09-11 — Promote paid go-live approved

**Go-live wire approved for Promote.** Grant opened Promote paid go-live on
2026-09-11 (evening): checkout may ship; Stripe live mode is approved for Promote.
Live Stripe price IDs are **ops-filled** (Zazu, 2026-09-11). Azure restarted on
commit `7f5d5a6`. Play production publish is **in flight** — do not claim Play
production is done.

Locked amounts and wired live Stripe prices:

| Module | Offer | Locked amount |
|---|---|---|
| **Promote** | Monthly | **$29/mo** — `STRIPE_PRICE_ID_MONTHLY` (`price_1UEdll1YnX6cB4kb7fXCeMRF`) |
| **Promote** | 90-day intensive | **$129** — `STRIPE_PRICE_ID_INTENSIVE_90DAY` (`price_1UEdlm1YnX6cB4kbfvvc6eAV`) |

Recruit paid go-live remains approved (see the subsection above). Recruit amounts
and IDs are unchanged.

---

## The market, priced

Everything below was retrieved 2026-07-29.

| Offer | What it is | Price |
|---|---|---|
| **[Station Visit](https://stationvisit.com/)** — direct competitor | AI-scored mock oral boards, 5 dimensions | Free: 1 interview, no card · **$19.99/mo** · **$99/yr** · **$49 / 90 days** |
| **[1-11 Fire Prep](https://www.111fireprep.com/)** | Membership: tips, questions, Q&A, discounted coaching | **$29.99/mo**, 3-day free trial |
| **[911 Prep](https://www.911interview.com/)** | Video course + human mock interviews | **$499** course · **$949** with 3 mock interviews |
| **[Aspiring Fire Officers](https://aspiringfireofficers.com/coaching/)** | 1:1 human coaching | **$85/hr** (+$25 per extra person for groups) |
| Other human coaching | Claimed market range | **$350–500/hr** at the top end |
| NTN FireTEAM | The actual test the candidate must pass | $60–95 |
| **BadgeDay Promote** | Existing module | ~$29/mo, ~$129 / 90 days |

**The shape of it:** a self-serve AI tier at **$20–30/month**, and a human tier an order of
magnitude above it at **$85–500/hour** or **$500–950** packaged. Nothing sits in between,
because nothing has been able to — that gap is exactly where an SME-authored rubric applied
by a model can live.

---

## Recommendation

> **Free — the full readiness gap analysis, plus one complete mock board with critique.
> No card.**
>
> **Monthly — $29.**
> **6-month "hiring cycle" — $119** (~$19.83/mo). *The plan to sell.*
> **12-month — $179** (~$14.92/mo).
>
> **No 90-day pass for Recruit.**

### Why give the gap analysis away entirely

This is the strongest single move available and it costs almost nothing.

`recruit_scope.md` already describes pillar 2 as "the module's on-ramp — it is fast, it
delivers something concrete on day one, and it tells a candidate why they need the rest."
That is a description of a free tier. A candidate who completes the intake and receives a
prioritised 6/12/18-month plan naming his three biggest gaps has been told, by something
that clearly knows the trade, exactly why he is not competitive yet. The conversion ask
writes itself, and it is not "buy this to see your score" — it is "you now know what to fix;
the board is the part you cannot fix alone."

It also beats Station Visit's free tier on its own terms. Theirs is one mock interview — a
sample of the paid product. Ours is a **complete deliverable he keeps**, plus a sample of
the paid product. Marginal cost is one model call.

Recruit is also the module with the better free-tier economics: it has no ingestion cost.
A Promote free tier would mean paying Azure Document Intelligence for a stranger's upload.

### Why $29/month, not $19.99

Do not undercut Station Visit. Going in cheaper against an incumbent says we are the budget
option, and if the plan is to be materially better then that is the wrong claim and it
leaves money on the table permanently — the first price is very hard to raise.

$29 also matches Promote, which keeps one brand telling one story about what a BadgeDay
subscription costs, and it sits at the top of the established self-serve band rather than
outside it (1-11 Fire Prep is already at $29.99 for a membership with no AI critique at
all). Against $85/hr for a single hour with a human, $29 for a month is not a hard argument.

### Why the 6-month plan is the hero

The whole product thesis is that the candidate is **6–18 months out** — that is the premise
of the gap analysis. Promote sells a 90-day intensive because a promotional exam has a date
on it. A pre-hire candidate has no date; he has a hiring cycle and a list of things to fix
that take a year. **Selling him a 90-day pass sells him the wrong shape** and quietly
contradicts the advice the product just gave him.

$119 for six months is a real commitment at a real discount, it is the term over which the
gap analysis plan actually plays out, and it lands just above Station Visit's annual $99 —
close enough not to need defending, far enough to signal a different class of product.

### Where the judgment call is

**The 12-month at $179 is 81% above Station Visit's annual $99.** That is the one number in
this recommendation that is genuinely arguable. The case for it: the plan the gap analysis
produces runs 18 months, so annual is the natural term for the candidate it is written for,
and discounting it heavily trains buyers to wait for the discount. The case against: a new
brand with no reputation asking nearly double the incumbent on the flagship term is a real
conversion risk.

If you want the safer version, **$139/yr** (~$11.58/mo) keeps a visible discount ladder and
sits close enough to $99 that the comparison does not sting. I would still open at $179 and
find out — it is one Stripe price ID either way. The July note that Stripe stayed in test
mode until both modules ship is superseded for Recruit and Promote (START ORDER
2026-09-11; Promote evening). Recruit live IDs remain ops; Promote live Stripe
prices are ops-filled.

### Cost does not constrain any of this

Remeasured 2026-09-10 against list ASR and a live critique call. Token telemetry is still
not persisted on attempts, so the critique figure is a remeasurement, not a running mean.
Margin math in this section uses the July competitive pairing (**$119 six-month / $179
annual**), which Grant locked as the Recruit SKUs on 2026-09-10.

Per-answer marginal cost, **retry-adjusted** (the published basis). The whole-board
Criterion 1 pass is one more call per board and is not in these numbers.

- Batch ASR on a 3-minute answer: **~$0.013** (3 × $0.0043/min list)
- Critique: a single call lands around ~$0.15, but thinking-token variance is high,
  `critiquer.py` allows two attempts, and the August reruns showed some answers
  needing both. Retry-adjusted expected critique (≈20% retry) ≈ **~$0.18**
- **~$0.19 per answer** (ASR ~$0.013 + ~$0.18)

**The bank is the bound. The daily cap is abuse throttling.** At the ~290 prompts
recommended in `recruit_question_bank.md`, and with no repeats ever, a candidate
cannot consume more than ~290 × ~$0.19 ≈ **~$55** before the 12-month retirement
rule recycles anything. "Unlimited" stays safe to advertise. (Single-call at
~$0.16/answer would have been bank ~$46 / floor ~61% on $119; that is not the
published basis.)

Margin floor — **retry-adjusted ~$0.19/answer.** Worst case is a **six-month
subscriber who exhausts the bank**:

- Weekly boards for 26 weeks: 5 × ~$0.19 × 26 ≈ **~$25** COGS → **~79%** margin on $119
- Bank-exhausted worst case: ~290 × ~$0.19 ≈ **~$55** → (~$119 − ~$55) / $119 ≈ **~54%**
- Annual at $179: weekly 5 × ~$0.19 × 52 ≈ **~$49** → **~72%**; bank-exhausted
  (~$179 − ~$55) / $179 ≈ **~69%**

Everything else is better than the **~54%** floor. Price on position and value, not
on cost. There is no cost argument for cutting price.

The bank does not protect monthly on its own. A heavy monthly user who runs the daily
cap (10/day) burns through ~290 questions in about a month (≈$55 COGS) — a loss on
month one relative to monthly revenue. Lifetime COGS is still bounded at ~$55; month
two onward is nearly pure margin until 12-month retirement recycles. Cost exposure is
fine. This surfaces a **product** problem: a heavy user can hit "no unseen questions"
inside the term they paid for, and the app needs a design decision on what to say
when the bank is empty (that decision is open; this note does not invent the UX).

### Packaging stays separate

`recruit_scope.md` settled this 2026-07-26 and nothing found here disturbs it: separate
plans, no bundle. A serving Lieutenant candidate and a pre-hire applicant are different
people and a combined plan sells each of them half a product. Structurally this means new
`STRIPE_PRICE_ID_RECRUIT_*` entries alongside the existing pair in `app/config.py`, with the
price-ID → module mapping resolved server-side per the architecture table
(`app/billing/module.py`).

Locked env-var names (Grant, 2026-09-10): `STRIPE_PRICE_ID_RECRUIT_MONTHLY`,
`..._RECRUIT_INTENSIVE_90DAY`, `..._RECRUIT_6MONTH`, `..._RECRUIT_ANNUAL` —
monthly, a 90-day pass, a 6-month hiring-cycle term, and annual. Amounts locked
as in the table above; live IDs are still ops.

---

## "Materially better than Station Visit" — what it has to mean

`recruit_scope.md` step 3 sets the bar comparatively. Here is the comparison made concrete,
so the step 3 decision has something to test against.

### What they do that we must match — table stakes, not differentiation

Losing on any of these makes the rest of the argument irrelevant.

1. **A free first session.** Covered, and beaten, by giving away the gap analysis.
2. **A full mock panel, not a single question.** They run intro → scenario → values →
   motivation → closing. Our current design is one question per session. **This is the
   biggest functional gap and it is not currently in the build order.** A candidate
   comparing the two will read single-question practice as a demo. Recommend a full-board
   session mode composed of five prompts drawn per the rotation rule in
   `recruit_question_bank.md`, with critique per answer plus a whole-board pass — which
   Criterion 1 needs anyway, since its scope is settled as *scored across the whole board*.
3. **Question volume and rotation.** They advertise rotating questions to prevent
   memorisation — the same design decision as ours. Not a differentiator either way.
4. **They ship today and we do not.** The only fix is shipping.

### What they do that we should copy, with a caveat

**Custom question entry** — the candidate types in a question he heard on a real station
visit and gets it scored on the same rubric. It is genuinely useful, it costs little, and it
does not violate the no-upload rule (a prompt is not a document, and there is nothing to
retrieve or cite).

**The caveat is real, though:** our critique is only as good as the rubric authored for that
question family, and an arbitrary pasted question may map to no reviewed criterion at all.
Shipping it naively produces exactly the unanchored career advice the whole architecture
exists to prevent. If we build it, it must classify the pasted question into a known family
first and **decline, visibly, when it cannot** — "this one is outside what we score" is an
acceptable answer and is itself a credibility signal.

### Where we can be materially better

1. **Every critique point names its criterion.** They give a numerical score, strengths, and
   one improvement area. We ship a verification gate that *rejects* any point not tied to a
   named rubric clause or a computed metric — `app/critique/`, 43 tests, already built. This
   is the Promote citation discipline transplanted, and it is the difference between
   feedback and opinion. It is also demonstrable in a screenshot.
2. **No score is shown.** They show a number. §4 says a surfaced number invites optimising
   the number. This is a deliberate advantage that **will read as a missing feature unless
   it is marketed as a position** — say plainly why the number is withheld.
3. **We never write your answer for you.** Their feedback names an improvement area; the
   standing temptation in this category is to supply language. Our gate forbids it outright.
   The pitch is the level 3 anchor itself: the clone answer is correct, generic, and
   indistinguishable, and a tool that hands out phrasing manufactures clone answers at
   scale. No competitor can claim this without rebuilding around it.
4. **Delivery is arithmetic, not an AI opinion.** Their fifth dimension is "delivery
   quality," model-judged. Ours is words per minute, time-to-first-word, filler rate, pause
   count and position, longest unbroken stretch — computed in our own code from word
   timestamps. Deterministic, zero run-to-run variance, honestly comparable across sessions.
   Theirs cannot be compared across sessions and probably should not be.
5. **The readiness gap analysis.** They have nothing like it. It is the reason a candidate
   subscribes for six months instead of cramming for a week, and it is the single largest
   product difference.
6. **Progress as behaviors across novel questions** — *across your last eight answers, to
   eight questions you had never seen, here is what held and here is what drops out under
   pressure.* Strictly more useful than a score trend, and it is the honest way to report a
   scorer whose noise floor we have actually measured (§7).
7. **The author outranks theirs, and we should say so.** Their rubric is attributed to "an
   experienced firefighter-paramedic." Ours is authored by a fire captain with over twenty
   years in the service — real credibility, and `recruit_scope.md` already says to claim it
   plainly and never to dress it up as a department's scoring sheet.
8. **Audio is transcribed, measured, and discarded** unless he opts in. A privacy stance
   worth stating out loud in a category where nobody states one.

### The honest read

Points 1, 3, 4 and 6 are **already built or already decided** and are defensible on day one.
Point 5 is the biggest gap and is pillar 2, now committed for launch. Point 2 is a real
advantage that markets badly and needs copy written for it.

The exposure is table stakes item 2 — **full-board sessions**. Everything else on this page
is an argument we can already make; that one is a feature we do not have and a candidate
will notice within thirty seconds of comparing.
