# Criterion 3 — fifth full set re-run, after the restatement ruling

**Run command:** `python scripts/recruit_review_compare.py`
**Model:** `claude-sonnet-5`, effort `high`
**Asked:** did narrowing route 2 move anything other than E?

## Result

**Eleven of eleven agree. Zero divergences.**

| Ref | SME | Run 1 | Run 2 | Run 3 | Run 4 | Run 5 |
|---|---|---|---|---|---|---|
| A | 2 | 2 | 2 | 2 | 2 | 2 |
| B | 4 | 4b | 4b | 4b | 4b | 4b |
| C | 3 | 3 | 3 | 3 | 3 | 3 |
| D | 4 | 4 | 4 | 4b | 4b | 4 |
| E | **4** (blind 5) | 5 | 5 | 4b | 5 | **4b** |
| F | **4** (blind 5) | 4b | 4b | 4b | 4b | 4b |
| G | 1 | 1 | 1 | 1 | 1 | 1 |
| H | not assessable | FAILED | n/a | n/a | n/a | n/a |
| I | 5 | FAILED | 4b | 5 | 5 | **5** |
| J | not assessable | n/a | n/a | n/a | n/a | n/a |
| K | 4 | 4b | 4b | 4b | 4b | 4b |

**I held at 5 on `c3.anchor.5`.** That was the run's real question. The restatement rule sits
four paragraphs above the being-changed route, and the last clause written into that space
closed the route silently and took two commits to find. It did not happen this time.

## E moved, and this draw is worth more than a single draw usually is

E returned **4B on `c3.anchor.4B`**, against 5 in four of the five set runs.

**This is still one draw and still not a rate.** But the prior is not flat: E was measured at
**95% top band** on the pre-ruling clause six hours ago. A 4B under the null — the edit changing
nothing — is a 1-in-20 event. So this is meaningfully more informative than the usual
single-run result, and the standing caution about clean tables cuts the other way for once.

**What it supports:** the ruling changed something. **What it does not support:** any statement
about E's new rate. 95% → *lower* is what has been shown. 95% → 0% is not, and the difference
between a stable 4B and a 60/40 answer matters, because the second one is the state E was in
before any of today's work.

**`recruit_answer_runs.py E --runs 20` is the last measurement outstanding**, ~90 cents, and it
is the same measurement that turned E's wobble from a mystery into a named clause ambiguity
this afternoon. Worth it here for the same reason: if the rate is not near 100%, the
determinations will say what the residue is arguing.

## The clause named a destination and the pipeline chose a different one

The narrowed clause says an answer failing it is **"a 4 on anchor 4's third route"** — the
unrouted middle route, *one of the things a 5 does, done once and done well.* E landed on
**4B**, whose text is *"the relationships in his stories are transactional, and nobody in them
appears to matter to him beyond the task"* — which does not describe a man who spent his own
time teaching a struggling colleague to load a truck.

So the rubric now contains a routing instruction the pipeline does not follow, and it was
written into the clause this morning. Two readings, and they are not exclusive:

1. **The third route has no tag**, so an answer landing on it still has to be reported as 4A,
   4B, or bare 4. There is nowhere for it to go, and 4B is the default it falls into.
2. **The instruction is prose in anchor 5**, not in anchor 4, and nothing makes a clause in one
   anchor bind routing in another.

Both point at the same standing item rather than at a new one. **Do not fix this by writing
another sentence** — that is the move that has misfired five times today. It is evidence for
the 4A/4B question, which is Grant's.

## 4A, sixth consecutive absence

B, E, F and K took 4B; D took a bare 4. **Four of five level-4 answers on the same tag, and 4A
still assigned once ever** across five set runs, forty-five runs of E, twenty-five of F and the
noise-floor work. The tag is not discriminating; it is absorbing.

And F's row now shows the split from the other side: **verdict `4b`, deciding clause
`c3.anchor.4`.** The clause that decided it is the level, and the tag attached afterwards is one
whose text contradicts the answer.

## Deciding-clause churn, fifth and sixth observations

- **D**: `c3.anchor.4B` → `c3.anchor.4`, back to where it was in runs 1 and 2, band unchanged.
- **A**: `c3.anchor.2` → `c3.note.1`, reversing run 4's move, band unchanged.

Both are reversals of moves recorded one run ago. **The band is stable and the clause behind it
oscillates** — now the most-reproduced unexplained behaviour in the criterion, and invisible to
this report by construction, since it compares bands.

## Disposition

- **The ruling is implemented and has no blast radius.** I held, and the five answers not under
  ruling did not move band.
- **One measurement left, and it is the only one:** E at n=20.
- **Stop editing anchors.** Five anchor edits today, five whole-set checks. What is open is
  three SME questions and one measurement, and none of the three is answerable by writing
  another sentence into the rubric:
  1. **Where note 5's flag lands** — and E has now failed to probe it across forty runs, so the
     fixture needs replacing whatever the answer is.
  2. **Whether 4A/4B survives** — six consecutive absences, and the criterion now contains a
     routing instruction that cannot be honoured because the route it names has no tag.
  3. **What a reuse risk is** — note 10's boundary, all four firings outside it.
