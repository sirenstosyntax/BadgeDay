# Criterion 3 — fourth full set re-run

**Run command:** `python scripts/recruit_review_compare.py`
**Model:** `claude-sonnet-5`, effort `high`
**Asked:** did the route-numbering edit move anything it was not aimed at?

## Result

**Eleven of eleven agree. Zero divergences. No band moved.**

| Ref | SME | Run 1 | Run 2 | Run 3 | Run 4 |
|---|---|---|---|---|---|
| A | 2 | 2 | 2 | 2 | 2 |
| B | 4 | 4b | 4b | 4b | 4b |
| C | 3 | 3 | 3 | 3 | 3 |
| D | 4 | 4 | 4 | 4b | 4b |
| E | 5 | 5 | 5 | 4b | 5 |
| F | **4** (blind 5) | 4b | 4b | 4b | 4b |
| G | 1 | 1 | 1 | 1 | 1 |
| H | not assessable | FAILED | n/a | n/a | n/a |
| I | 5 | FAILED | 4b | 5 | 5 |
| J | not assessable | n/a | n/a | n/a | n/a |
| K | 4 | 4b | 4b | 4b | 4b |

*(n/a = not assessable)*

## What this does and does not establish

**It does establish that the route-numbering edit has no gross blast radius.** No band moved.
That is the check §7 now requires after every anchor edit, and it is the first edit today to
come through it clean on the first attempt.

**It does not establish that the edit worked.** E returning 5 is one draw from an answer measured
at 40% top-band six hours ago — no information in either direction, which was stated before the
run rather than after it. Whether the amended clause changed E's rate needs `--runs 20` on the
amended text.

**And a clean table is weak evidence generally.** Eleven single draws produced exactly the
pattern that was withdrawn after run 2 as meaningless. What it rules out is a gross change; it
rules out nothing subtler. `recruit_review_compare.py`'s closing message now says this in both
directions rather than only warning about false divergences — it was quoting the July `5×3 / 4B×2`
figure as its example of a rate, which is the exact number recorded that morning as too small to
be one.

## Deciding-clause churn, fourth observation

Two moved with the band unchanged:

- **A**: `c3.note.1` → `c3.anchor.2`. Both reach 2, and anchor 2 is arguably the better fit — a
  shift lead who absorbed six weeks of a colleague's work and never asked why is the
  crew-is-missing-from-his-own-stories case, where note 1 is the declined-conversation route.
- **F**: `c3.anchor.4` → `c3.anchor.4B`, having gone the other way in run 3.

The verdict is stable and the clause that produced it is not. The calibration report cannot see
this — it compares bands — so it is invisible unless someone reads the determinations, which is
worth remembering given that the *"clause that decided it"* column was rebuilt in July precisely
because it used to name arbitrary clauses.

## 4A, fifth consecutive absence

B, D, F and K all took 4B. Across four full set runs, twenty-five runs of F and twenty of E,
**4A has been assigned once** — on a fixture where it was recorded as a misfire.

## Disposition

**A good place to stop.** State of the criterion after today:

- Every one of the four anchor edits now passes a whole-set check.
- F sits at 4 across four runs, matching the SME's revised ruling.
- E and I both at 5 in the latest run, with E known to be a 40% answer and I stable across two.
- Nothing else has moved from its blind score in four runs.

**Open, and none of it is another anchor edit:**

1. **Where note 5's flag lands** — SME. Still unmeasured, and the answer filed as probing it turns
   out to decide on something else.
2. **Whether 4A/4B survives** — SME. Five observations behind it.
3. **E at n=20 on the amended clause** — measurement, ~90 cents.
4. **`recruit_noise_floor.py c3`** — stale since 2026-07-29, now four anchor edits behind.
