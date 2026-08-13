# Criterion 3 — noise floor, after four anchor edits

**Run command:** `python scripts/recruit_noise_floor.py c3`
**Model:** `claude-sonnet-5`, effort `high`, adaptive thinking
**Asked:** did any of today's four anchor edits leave the rubric text ambiguous to a scorer?

The number had been stale since 2026-07-29 — seven anchor edits ago across two days — and
§7's standing rule is to re-run after any anchor change.

## Result

| Fixture | n | Distribution | Spread | σ |
|---|---|---|---|---|
| Qualified, self-focused (the target anchor) | 20 | 2×20 | 0 | 0.00 |
| No team history, material undersold | 20 | not assessable ×20 | — | — |
| No team history, genuinely nobody there | 10 | not assessable ×10 | — | — |
| Between 2 and 3 (asked, crew undifferentiated) | 20 | 3×20 | 0 | 0.00 |
| Generic, correct, no incident | 10 | 4B×10 | 0 | 0.00 |
| Changed by a named person | 10 | **5×10** | 0 | 0.00 |

**Ninety runs, zero variance on every fixture.** The cleanest this criterion has measured,
against a previous best of 80/80 — and two of these fixtures have a wobble history: the
undersold answer split three ways in July before note 4 was settled, and the 2/3 boundary
produced a stray 4A. Both are flat now.

## What it establishes

**The four anchor edits introduced no scorer-path ambiguity on anything these six fixtures
reach.** That was the question, and it comes back clean.

**Two of the edits are confirmed by name in the determinations**, which is stronger than a
distribution:

- The being-changed fixture's reasoning quotes the restored route back — *"clears the breadth
  clause on its own, reaching the top band."* That route was closed by my own breadth clause on
  the first set re-run and reopened four commits later; this is independent confirmation from a
  different path that the repair took.
- The generic-correct fixture cites *"anchor 4's third route"* — the numbering added the same
  day, being read as written.

## What it does not establish

**Not approval.** The script's own docstring says so and today has the cleanest example in the
project's history: twenty-five consecutive 5s on answer F were zero variance and the wrong band.
A stable rubric can be stably wrong, and only the SME says otherwise.

**Not the breadth requirement.** No fixture here tests it. The being-changed fixture tests the
*exemption* from it, which is the opposite case. Nothing in these ninety runs speaks to the
two-behaviours question, and that is where answer E lives.

**Not the product.** See below — this is the sharpest thing in the run.

## The unintended controlled comparison

`C3_CHANGED_BY_SOMEONE` **is** review-set answer I. Same Dave transcript, written for the
noise-floor harness and later reused as a review-set answer. So today produced both paths over
one answer, same rubric, same model, same effort, same day:

| Path | Answer I |
|---|---|
| Scorer (`recruit_noise_floor.py`) | **5×10, σ 0.00** |
| Critique (`recruit_review_compare.py`) | 4B, 5, 5 across three set runs |

That is §7's 2026-07-29 path finding reproduced **on a single transcript** rather than inferred
across five, with the confounds a five-answer comparison leaves open — different answers,
different boundaries, a week apart — all closed.

**So a clean scorer floor and a wobbling product are not in tension; they are the same result
seen twice.** 90/90 says the rubric is unambiguous to a reader asked only for a score, and says
nothing about what ships. The script's docstring now says which of the two questions it answers
and points at `recruit_answer_runs.py` for the other.

## Disposition

- §10's *"the noise floor is stale"* item closes. The figure to quote for the current text is
  **90/90 on the scorer path**, with the transfer caveat attached — never bare.
- **Still the standing recommendation: stop editing anchors.** Four edits today, each of which
  read cleanly before a run contradicted it, and three of the four were repairs to over-broad
  sentences of my own rather than new rulings.
- Open, unchanged by this run, and none of it another anchor edit:
  1. **Where note 5's flag lands** — SME. All four risk firings sat outside note 10's stated
     boundary.
  2. **Whether 4A/4B survives** — SME. 4A assigned once ever, across roughly 140 observations.
  3. **E at n=20 on the amended clause** — measurement, ~90 cents.
