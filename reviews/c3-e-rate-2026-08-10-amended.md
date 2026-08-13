# Answer E at n=20, on the amended breadth clause

**Run command:** `python scripts/recruit_answer_runs.py E --runs 20`
**Model:** `claude-sonnet-5`, effort `high`
**Asked:** did numbering the three routes move E's rate?

## Result

| | Before (`cef1f9f^`) | After |
|---|---|---|
| Distribution | 5×8, 4B×11, 4×1 | **5×19, 4B×1** |
| Top band | 8 of 20 (**40%**) | 19 of 20 (**95%**) |
| Spread | 1 anchor, σ 0.49 | 1 anchor, **σ 0.22** |
| SME (blind) | 5 | 5 |

**The edit worked, and it is the only edit today that can be said to have worked in the sense
that matters** — a measured before and a measured after, on the same answer, at the same n,
with nothing else changed. The other four passed blast-radius checks, which is not the same
claim.

**And it worked for the stated reason**, which is the part worth more than the number. The
5 determination cites the mechanism by name:

> *"a disposition he describes as ordinary rather than as an achievement — 'if someone was slow
> you'd help them out and they'd do the same for you next time, that's how it works' — **which is
> the route-2 breadth condition named directly in the anchor**."*

That is the clause being read the way it was written, quoting the route number added six hours
earlier. The prior run's dissent — *"a general rule about the crew rather than a tied
occasion"* — does not appear anywhere in twenty runs. The untied-route ambiguity is closed.

## The surviving 4B is a different objection, and it is a fair one

The single 4B does not repeat the old reasoning. It concedes the route exists and argues the
material does not satisfy it:

> *"the 'that's how it works' line is **a general restatement of the same kind of help** rather
> than a separate behaviour or occasion, so the breadth anchor 5 requires isn't met."*

Not *"a disposition is untied, therefore it doesn't count"* — which the fix ruled out — but
*"this disposition is the same behaviour as the incident, so it is one behaviour told twice."*

**That is a question the clause genuinely does not answer.** The breadth clause says a 5 needs
more than one of anchor 5's behaviours and that the same behaviour told three times cannot
clear it. Route 2 says a disposition described as ordinary supplies the second. E's incident is
*helping a slower colleague*; E's disposition is *helping slower colleagues is what you do*. On
one reading those are two behaviours in two places; on the other they are one behaviour and its
generalisation.

**Deliberately not fixed, for three reasons.** It is 1 of 20 — inside the noise the harness
prints its own warning about, and not a rate. It runs against the SME's blind 5, so resolving it
toward the dissent would revise a score he gave. And today's lesson, four times over, is that a
sentence written to close a narrow gap moves things it was not aimed at; the standing
recommendation is still to stop editing anchors. **Filed as a question for Grant, not a defect:
does a disposition have to describe conduct different from the incident, or is generalising the
incident into a norm itself the second thing?** If he wants it closed, the clause needs one
sentence and E needs re-measuring after it.

## Grounding check

The 5 determination cites *"a tied occasion where he taught a newer, slower teammate to load the
truck so he stopped fighting it."* That is in the transcript verbatim in substance — *"one lad
who was newer and slower, and I spent a bit of time showing him how to load the truck properly
so he wasn't fighting it."* Not an invented occasion. Checked because a determination that
suddenly names an occasion the previous twenty runs did not emphasise is exactly where a
grounding failure would hide.

## What this does not establish

**Not that E is correctly a 5** — only that the pipeline now agrees with the SME's blind score
95% of the time instead of 40%. Agreement with the score is not evidence the anchor is right,
and E was written by the same party that drafted the anchor.

**Not that the note 5 probe is answered.** E exists to test whether *"I've genuinely never had a
problem with anyone I've worked with"* pulls an answer down. The 5 determination mentions it and
sets it aside — *"a separate, still-open question about delivery risk and does not by itself
demote a pattern of conduct that is otherwise present"* — and the 4B does not mention it at all.
**So across forty runs on this answer, the line has never once decided anything.** The note has
had no landing place since July, and the fixture filed against it has now failed to probe it
twice at n=20. That is not a null result about the note; it is a fixture that does not reach it.
A fixture that isolates the claim — the same answer *without* a second behaviour, so the closing
line is the only thing left to decide on — would.

## The probe line was pointing at the wrong note

The harness printed:

    (E probes: note.4 — the unfalsifiable claim ...)

**Note 4 is *"Some candidates have no team history"*.** The unfalsifiable claim is note **5**,
*"Do not score the teammate"*, which carries the open block about the never-had-a-disagreement
answer. The reference has been wrong since the exercise was built: the 2026-07-29 rewrite
inserted two notes above the old note 3, and the hand-written strings in `review_set.py` did not
move. H's probe was off by one in the same direction — it named the specificity floor while
describing no-team-history.

Small, and worth fixing precisely because of where it prints. `recruit_review_compare.py` shows
*"written to probe"* beside every divergence as the record of what an answer is for, so for six
weeks a divergence report has been aiming its reader at the wrong clause while looking
authoritative. **This is the hand-maintained-list failure that `rubric.py` parses the clause
catalogue to avoid, one layer up and unguarded.**

Both fixed. `tests/test_review_set.py` now resolves every clause reference in every probe
against the real catalogue — which catches a renumbering that runs off the end, and **cannot
catch a swap between two clauses that both exist**, which is what this was. The pairing for E
and H is pinned by ref for that reason.

Note that §10 and the earlier review files say *note 5* throughout and are correct; the code was
the thing that disagreed with them.

## Disposition

- **E's item in §10 closes on the measurement.** 40% → 95%, mechanism confirmed by name.
- **Two things open in its place**, neither an anchor edit: the same-behaviour question above
  (Grant), and the fact that E has never probed what it was written to probe (a fixture, not a
  clause).
- **Standing recommendation unchanged: stop editing anchors.** The measurement queue is empty
  now — this was the last one outstanding. What remains is all SME.
