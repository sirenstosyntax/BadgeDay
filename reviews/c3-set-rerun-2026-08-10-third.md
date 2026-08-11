# Criterion 3 — third full set re-run

**Run command:** `python scripts/recruit_review_compare.py`
**Model:** `claude-sonnet-5`, effort `high`
**Under test:** whether restoring the being-changed route returns I to 5.

## Result

**I returned to 5. E fell to 4B. And the "zero drift" claim from the second run is falsified.**

| Ref | SME | Run 1 | Run 2 | Run 3 | |
|---|---|---|---|---|---|
| A | 2 | 2 | 2 | 2 | stable ×3 |
| B | 4 | 4b | 4b | 4b | stable ×3 |
| C | 3 | 3 | 3 | 3 | stable ×3 |
| D | 4 | 4 | 4 | **4b** | band stable, **route moved** |
| E | 5 | 5 | 5 | **4b** | **moved — divergence** |
| F | **4** (blind 5) | 4b | 4b | 4b | stable ×3 |
| G | 1 | 1 | 1 | 1 | stable ×3 |
| H | not assessable | FAILED | not assessable | not assessable | stable ×2 |
| I | 5 | FAILED | 4b | **5** | **restored** |
| J | not assessable | not assessable | not assessable | not assessable | stable ×3 |
| K | 4 | 4b | 4b | 4b | stable ×3 |

## The fix worked

**I is back at 5, deciding clause `c3.anchor.5`.** Restoring the being-changed route in both
passages reached the model. The prediction was made before the run and confirmed by it, which is
the first time in this sequence that has happened in that order.

## E fell, and it is not my edit

The obvious reading is that the previous edit moved something else it was not aimed at — the
third time in a day. **The record says otherwise, and the record is checkable.**

§7's 2026-07-29 table, taken *before* any of today's anchor work:

| Answer | Grant | After the outcome anchor |
|---|---|---|
| E | 5 | **5×3, 4B×2** |

E has been a 60/40 answer at the 4B/5 boundary since July, and §10 has carried
*"one-anchor wobble on E and K"* as an open item ever since. Three set runs returning 5, 5, 4B is
what a 60/40 rate looks like over three draws. **No edit is needed to explain it, and the edit
between run 2 and run 3 only added a sufficient route — it tightened nothing.**

E's probe is the still-open note 5 question: *does "I've genuinely never had a problem with
anyone I've worked with" pull an answer down, or is it a thing to note without moving the score?*
The answer written to test an unresolved clause is unstable at exactly the boundary that clause
governs. That is the same shape as Criterion 2's 3/4B wobble, which turned out to be a nameable
ambiguity rather than model noise.

## The claim I got wrong, and it is worth being precise about

After run 2 this file's predecessor recorded *"zero drift across nine answers between two runs"*
and called it the baseline: *"from here, an answer that moves between runs is a pipeline
question, not a clause question."*

**That was two draws from a distribution containing at least one known coin flip, read as
stability.** Run 3 falsified it immediately. Two answers moved — E across a band, D across a
route — and neither needed an edit to explain.

The general form, and it is the more useful lesson: **a single run per answer measures a value;
a boundary answer has a rate.** Eleven single draws cannot distinguish a rubric finding from a
wobble, however orderly the table looks, and *comparing two such tables* multiplies the error
rather than controlling for it. `recruit_review_compare.py` now says so in its own output and
points at the n=20 harness, because the misreading was mine twice over and the report gave no
warning against it.

## Route assignment is unstable even where the band is not

Two observations that are not divergences and are worth recording:

- **D moved from an unrouted `4` to `4b`** across runs, deciding clause `c3.anchor.4` both times.
  Same band, different tag, same rubric.
- **F held at `4b` but its deciding clause moved** from `c3.anchor.4B` to `c3.anchor.4`.

Neither trips the comparison, because a bare `4` agrees with either route. Both say the route is
being assigned less reliably than the band it sits under.

**And in this run every level-4 answer is 4B — B, D, E, F and K, five of five.** Across three
full set runs, twenty-five runs of F, and the noise-floor work, **4A has been assigned once**, on
a borderline 2/3 fixture where it was recorded as a misfire. §10 has held since July that the
split *"came out of a single pass"* and that the scorer *"applied it consistently (5/5 runs
tagged 4B), which says the split is legible — not that it is right."* Three set runs later, the
kinder reading is no longer available: **4A is a dead letter, and 4B is absorbing every answer at
level 4 regardless of whether its text describes them.** It describes none of these five.

## No anchor edits made

Deliberate. Three edits in one day, each of which moved something it was not aimed at, and the
one thing this run establishes is that the harness cannot currently tell me whether a fourth
would help. The next step is measurement:

```
python scripts/recruit_answer_runs.py E --runs 20
```

That gives E a rate rather than a value, and it either confirms the July 60/40 or shows the
boundary has moved under today's edits — which are different findings with different fixes.

## Disposition

**The breadth clause is confirmed to the extent one run can confirm anything**: F down and
stable across three runs, I restored, and the seven answers away from the 4B/5 boundary stable
across all three. **What remains open at that boundary is older than today's work** — E and K
were logged as wobbling in July, and E's instability is tied to a note the SME has not ruled on.

Recommended: run E at n=20, then stop touching the anchors until the two standing SME questions
are answered — where note 5's flag lands, and whether 4A/4B survives at all. The second has now
had five observations behind it in a single run.
