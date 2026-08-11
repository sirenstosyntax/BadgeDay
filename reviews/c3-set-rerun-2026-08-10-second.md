# Criterion 3 — second full set re-run

**Run command:** `python scripts/recruit_review_compare.py`
**Model:** `claude-sonnet-5`, effort `high`
**Under test:** the four fixes from the first re-run, and the first repeat observation on
every answer.

## Result

**Eleven of eleven scored. Ten agree. One divergence — and it is my clause, not the model.**

| Ref | SME | Run 1 | Run 2 | |
|---|---|---|---|---|
| A | 2 | 2 | 2 | stable |
| B | 4 | 4b | 4b | stable |
| C | 3 | 3 | 3 | stable |
| D | 4 | 4 | 4 | stable |
| E | 5 | 5 | 5 | stable |
| F | **4** (blind 5) | 4b | 4b | stable |
| G | 1 | 1 | 1 | stable |
| H | not assessable | FAILED | **not assessable** | recovered |
| I | 5 | FAILED | **4b** | **divergence** |
| J | not assessable | not assessable | not assessable | stable |
| K | 4 | 4b | 4b | stable |

## Two good results first

**Zero drift across nine answers between two runs.** Every answer that scored in run 1 returned
the same value in run 2. This is the first repeat observation on this harness, and it is the
only way to tell a rubric finding from pipeline noise on a one-call-per-answer path. Nothing
moved.

**The retry fix worked.** H returned `not assessable` citing `c3.note.4`, matching the SME
exactly. It failed in run 1 on an empty required field — legal output under the schema the API
was actually sent, rejected by our own validator against a `min_length` it never saw. Retried
once, correct on the second attempt, and no truncation anywhere in the run at the raised
`max_tokens`.

## I came back 4B against an SME 5, and the breadth clause caused it

**Predicted:** I holds at 5. **Actual:** 4B, deciding clause `c3.anchor.4B`. The prediction was
wrong and the mechanism is exact.

The breadth clause read:

> **A 5 requires more than one of the behaviours listed above** […] **Where this clause and
> anything below it disagree, this clause governs.**

*Being changed by a named colleague* is **not** in that list. It appears four paragraphs further
down, as its own paragraph, saying it *"is one route to a 5, not the definition of one."* That
route predates the clause by weeks. The clause claimed precedence over everything below it and
therefore **demoted a standing route to 5 into nothing** — silently, because nothing in either
passage mentions the other.

I is the fixture written to test that exact route. Its recorded probe: *"anchor.5 — named person
acts, and the candidate was changed by him."* The clause closed the one thing the answer exists
to check, and the model applied the rubric correctly: it found one listed behaviour (taking the
correction without distributing blame), needed two, and routed to 4.

**This is §7's own warning arriving from the opposite direction.** *"A boundary made stable by
becoming unreachable is closed, not fixed."* The first version of the clause made F stable by
lowering it correctly and made I stable by closing a route nobody re-read.

## Fix

**The being-changed route now clears the breadth clause on its own**, stated in both places —
in the clause, so a reader arriving there knows the list is not exhaustive, and in the route, so
a reader arriving there knows the clause does not close it. Either alone leaves a reader with
the wrong answer, and a test asserts both.

**The reasoning, because it is a judgment and not a mechanical repair.** A man who was told
something hard, took it, and *still works differently because of it* has shown the conduct
twice: once in how he received the correction, and again in the practice he carried away. **The
carried change is the second place.** That is precisely what the clause already asks for — its
own third example is *"a change in how he works that outlasted the incident"* — so this
connects two passages that were always compatible rather than adding a new rule.

Checked against all three answers the SME has ruled on:

| | Persisting conduct? | Band |
|---|---|---|
| **F** | No — one conversation, and the change was *Ryan's* | **4** ✓ |
| **E** | Yes — *"that's how it works"* across three years, plus teaching a newer lad | **5** ✓ |
| **I** | Yes — *"what I do differently now"*, and Dave wrote his reference | **5** ✓ |

Consistent with every blind score he has not revised, and with the one he has.

**The alternative, which is his to take.** If being changed by a colleague should *also* need a
second behaviour beside it, then I is a 4 and his blind 5 on it was wrong. That is a coherent
position and it is not the one implemented here — I have restored the route rather than assume
he wants to close it, because closing it would revise a blind score he has not been asked about.

## Observed again, not fixed

**I came back `4b`, the fourth answer to land on that tag.** B, F, I and K are all 4B; only D
took an unrouted 4. 4B's text reads *"the relationships in his stories are transactional, and
nobody in them appears to matter to him beyond the task"* — which describes none of them, and
least of all a man who kept working with Dave and asked him for a reference.

**Four of five level-4 answers on one tag is not a split doing any work.** It is the pipeline
picking the least bad option because the wanting-versus-able axis has nowhere to put a competent,
warm, single-piece answer. Standing question in §10, now with four observations behind it.

## Disposition

**Two rounds of anchor edits, two rounds of my own over-correction, and the same failure both
times: an edit that moved something it was not aimed at.** 2026-08-10 morning turned a narrow
4B/5 ruling into a general licence and drove F to 5. 2026-08-10 afternoon closed a route to 5
that nothing in the ruling touched and drove I to 4B. In both cases the rubric read cleanly and
the run looked orderly.

**Recommended before any further anchor work:** re-run the set once more to confirm I returns
to 5 and nothing else moved, then leave the anchors alone until the two questions that are the
SME's are answered — the note 10 boundary, and whether 4A/4B survives. The rubric has now been
edited twice in a day on the strength of one answer each time, and `recruit_noise_floor.py c3`
has not been run against any of it.
