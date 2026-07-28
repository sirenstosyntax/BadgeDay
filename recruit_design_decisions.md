# Recruit — Design Decisions

Decisions settled in working session, 2026-07-27. Authored by Grant Collings unless noted. Rationale is recorded because several of these look arbitrary without it and will otherwise be re-litigated or quietly reversed.

Status legend: **[SETTLED]** · **[PROVISIONAL]** — holds until contradicted, low confidence · **[OPEN]** — needs a decision

---

## 1. Product purpose

**[SETTLED] Recruit is a coaching instrument, not a selection instrument.**
It exists to help a candidate improve against his own prior performance. It does not rank users, does not predict hiring outcomes, and is not a normed assessment. Every design decision below follows from this.

**[SETTLED] Growth is measured against the candidate's own history, never against other users.**
No leaderboards, no percentiles, no cohort comparison.

**[SETTLED] Scores are internal.**
The number structures critique; it is not the headline of the UI. Surfaced scores get optimized; surfaced gaps get worked on. Progress is reported as behaviors acquired, not as a rising figure.

---

## 2. Rubric structure

**[SETTLED] 1–5 scale.**

**[SETTLED] Generic frame, hand-authored anchors.**
The five-criterion frame is conventional and portable. The anchors — specifically the boundaries between adjacent scores — are hand-authored by a serving fire captain. The frame may be public; the anchors are the asset.

**[SETTLED] Anchors describe motion and behavior, never eligibility.**
Minimum qualifications vary by department and change over time. An anchor referencing "meets minimum qualifications" means something different in every jurisdiction. Score direction and rate instead: what he did, when he last did it, what comes next.

**[SETTLED] Effort is scored relative to opportunity.**
Evidence of pursuit is weighed against time, money, and access available to the candidate. A consequence is that a 4 may hold fewer qualifications than a 3. This is intended — the criterion measures trajectory, not inventory.

**[SETTLED] Criterion 2 uses a compensatory model with route tags.**
Two candidates reach a 4 by opposite routes: drive high / evidence thin (4A), or evidence strong / drive shallower (4B). The score alone is not diagnostic. Scores must carry the route tag and critique must address the axis that is short, or feedback will tell a candidate to do more of what he is already doing.

**[SETTLED] The prepared-but-self-focused candidate is scored under Teamwork, not Motivation.**
The failure is one of fit, and it is scored where it occurs. He may legitimately score 4–5 on Motivation.

> **Open risk:** until Teamwork carries an explicit anchor for the *qualified* self-focused candidate, he passes the rubric unpenalized. Write that anchor first when Criterion 3 is authored.

**[SETTLED] Panels are partly subjective, and the rubric says so.**
A rubric clean enough to be fully objective would describe something that does not happen in the room. Anchors stay behavioral so they can be verified; the human reaction to those behaviors is acknowledged where it bears on the score.

**[SETTLED] The rubric is not total. Every criterion carries a not-assessable outcome, and it is not a low score.** (Raised by Grant 2026-07-28; implementation and wording confirmed by him the same day.)

A criterion-referenced instrument assumes the candidate's life supplies the material the criterion asks about. Not every life does. The clearest case is Teamwork: a candidate who has genuinely never worked alongside anyone — solo trades, long-haul, night shift, self-employment, obligations that kept him out of crews — cannot produce a story about how he treats a crew. He is not thereby unfit for one. **He cannot be expected to talk about people who were never there.**

Forcing that answer onto an anchor is the failure mode. It produces a confident low score that measures his history rather than his fitness, and it does so with a demographic shape — it will land hardest on the young, the rural, and the candidate who has been working alone since he was twenty-one.

So every criterion needs a third outcome alongside the 1–5: **insufficient evidence to assess.** Distinct from a low score, reported as its own thing, and never averaged in as a zero. Rules:

- **Establish the material is genuinely absent, not merely unmentioned.** Most candidates who say they have no team experience are wrong about it — they hear "team" as "paid work crew" and discount military service, sport, a kitchen, a church or community group, caregiving, raising siblings. Surfacing that is a coaching win and consistent with the no-content rule: we ask a better question, we do not supply the story.
- **Where it is genuinely absent, say so plainly and route it.** To the candidate: this is a part of the board that has to be worked on with a person, and here is what would generate the material. To pillar 2 — no team history is a real gap, and a fixable one on the 6–18 month horizon, which is exactly what the readiness gap analysis is for.
- **Do not let it become an escape hatch for the candidate the rubric is meant to catch.** The self-focused candidate *had* a crew and wrote them out of the story. That is a 2. Not-assessable requires that there was no crew.

The general principle behind it, which was already the stated position on Criterion 1's unscoreable half: **there has to be a place for human judgment, and the honest thing is to name where it goes rather than let the rubric quietly cover for its absence.** A model applying a rubric should be able to return "this does not fit," and the product should say so rather than dress a guess up as a score.

Implemented in Criterion 3. Criterion 2 should get the same treatment on review — it bites less hard there, since every candidate has some account of why he wants the job, but the rule is rubric-wide.

---

## 3. Critique generation constraints

**[SETTLED] The advice matters more than the grade, and there are two kinds of it.** (Grant, 2026-07-28.)

The score is instrumental and always was. What the product is actually for is helping a candidate improve **his answers** and **himself as a recruit** — and those are different things that the critique had been collapsing into one.

- **An answer gap.** He has the material and did not deploy it: a real incident buried under a general claim, a specific thing he did that he never got to. The fix is in the telling, and it is available to him today.
- **A development gap.** He does not have the material. On the weak teamwork fixture the candidate covered a man's section for six weeks and never asked him why. No amount of retelling fixes that. The fix is in his life, on the 6–18 month horizon, and it is what pillar 2 exists for.

The second is the more valuable finding and was the one being thrown away. Both were rendered as the same kind of bullet, so a gap requiring him to *go and do something* read like a note about phrasing.

Consequences:

- **Every critique point is classified** as improving the answer, improving the candidate, or recording something that worked. The classification is a routing signal, not a claim the gate can verify.

**[SETTLED] Most gaps do not get classified — they fork, and the candidate resolves them.** (Grant, 2026-07-28.)

The first cut asked the model to decide whether a gap was in the telling or in the man. That was the wrong question to put to it. Deciding requires knowing what is in his life, and all it has is one answer — so it was inferring his history from a single story and asserting the inference confidently to someone who cannot check it. The exact failure this module is built to avoid, arrived at from a new direction.

**He can settle it instantly and we cannot.** So the point says both branches and asks:

> Think about whether there is a better story that would show this. If it is not there, go and pursue the opportunity to get one.

Either branch makes him better, which is why the fork costs nothing. A better story found is the board skill; an experience gone and got is the firefighter. There is no wrong answer to hand him, only a wrong guess for us to make.

This is the same insight as §4's *"the underlying trainable skill is inventory and retrieval, not composition"* — strong interviewees carry eight to ten real incidents and map the asked question onto the best fit. **"Is there a better instance of this?" is that drill**, run against the candidate's own life. §4 was marked provisional; this is a second route to it and it should be read as strengthening it.

Consequences:

- **A third classification, `inventory`, and it is the default for a gap.** `candidate` narrows to the case where the answer *positively establishes* the material is absent — he said he has never done it. `answer` narrows to the case where the material is visibly present in the answer and merely mishandled. Everything between those, which is most of it, forks.
- **An inventory point is a question by construction**, so it must carry an ask, and the ask must carry the consequence of a no. The gate can check the first of those.
- **The prescription guard extends to the no-branch**, since "go and get it" is development advice wearing a different hat.
- **The classifier's risk drops.** It no longer has to be right about a life it cannot see; it only has to be right that something is missing from *this answer*, which is checkable against the transcript.
- **Development gaps are the bridge between the two pillars.** The oral board practice produces exactly the evidence the readiness gap analysis needs, and until now nothing carried it across.
- **Progress reporting needs a second set of behaviours.** The list in §4 — did the answer contain a specific incident, did he name what he would do differently, did he stop when finished — is entirely answer-construction. None of it tracks whether the candidate is becoming someone a department wants. That set is unwritten.
- **This raises the stakes on an open question rather than answering it.** How prescriptive the development advice gets is open question 1 in `recruit_scope.md`, still unanswered, and it now gates more than it did. Naming a gap is low risk. Naming the programme that fills it is career advice with a cost in time and money, delivered to someone who cannot check it — the failure mode this product was built to avoid, and it bites harder here than anywhere in the answer track. **Interim default until Grant sets the line: a development point names what is absent and may name the category; it does not prescribe a specific certification, programme or provider.**

> **Classification spread, run 2026-07-28** — `scripts/recruit_classification_spread.py`.
> Whether the answer/candidate filing is stable, and whether the skew on the weak teamwork
> answer was real or a one-run artifact.
>
> | Fixture | runs | answer | candidate | worked | candidate share |
> |---|---|---|---|---|---|
> | c3 / weak | 20 | **0** | 74 | 17 | 100%, sd 0.00 |
> | c3 / off-topic | 10 | 33 | 5 | 1 | 12%, range 0–50% |
> | c2 / weak | 10 | 2 | 36 | 9 | 95%, range 75–100% |
>
> **The skew is real and total.** Twenty runs of the weak teamwork answer produced 74
> development gaps and **not one** answer gap, with zero variance. It is not a sampling
> artifact and it does not wobble.
>
> **It is also not a global bias**, which is the more useful finding. The off-topic answer
> inverts it — 88% answer gaps — so the classifier discriminates rather than defaulting.
> The pattern it has settled on is defensible: an answer that tells a detailed story
> revealing the candidate never asked *why* exposes something missing from his life; an
> answer that talks about deadlifts when asked about teammates exposes a failure to answer
> the question, which retelling would fix.
>
> **Which means the harness has done all it can, and the remaining question is the one it
> cannot touch.** Perfect consistency on a wrong filing is indistinguishable from perfect
> consistency on a right one. Concretely, on the point I read as misfiled —
>
> > *[c3.anchor.3] The answer closes on a self-description asserting team orientation, but
> > the incident just given shows him working alone around a problem rather than with
> > anyone on it.* → *Can you think of a moment where the team, not just you, was the one
> > who made something work?*
>
> — that ask is fishing for material he may well have, which reads to me like an answer
> gap. The model filed it **candidate 5 times out of 5**. One of us is wrong and the
> harness has no opinion. **This is a fire captain's call and it is the highest-value
> thing outstanding**, because it decides whether the module's most valuable output is
> being routed correctly.
>
> **One rubric finding fell out of it.** `c2.anchor.2` — *preparation is real but stale* —
> split 73% development-gap and 27% *something that worked*. It is a mixed anchor, and the
> model sometimes credits the "real" and sometimes flags the "stale". Worth deciding which
> it is, or splitting it.
>
> **A limitation of the measurement, stated so the number is not over-read.** The
> per-clause split groups by clause, but two genuinely different observations can cite the
> same clause — so a "contested" clause may be two distinct findings rather than one
> ambiguous one, and `c2.anchor.5`'s 50/50 split looks like exactly that on inspection. The
> per-clause figure is a proxy for ambiguity, not a measurement of it.

> **Classification re-run 2026-07-28, after the fork.** Same harness, same fixtures.
>
> | Fixture | runs | inventory | answer | candidate | worked |
> |---|---|---|---|---|---|
> | c3 / weak *(was 0 / 0 / 74 / 17)* | 20 | **61** | 14 | **0** | 7 |
> | c3 / off-topic *(was 0 / 33 / 5 / 1)* | 10 | **35** | 0 | 0 | 0 |
> | c2 / weak *(was 0 / 2 / 36 / 9)* | 10 | **27** | 2 | 6 | 5 |
>
> **The verdict about his life is gone.** Development gaps on the weak teamwork answer went
> from 74 to zero — the pipeline no longer tells a man his history lacks something it cannot
> see. That was the point, and it holds across every run.
>
> **It did not simply relabel everything.** `answer` went from 0 to 14 on the same fixture,
> so narrowing the definitions moved points in both directions: some gaps really are visibly
> in the answer, and the model now says so where it can point at the sentence. The remaining
> `candidate` labels are on the c2 weak answer, where the candidate says outright that the
> academy plan *"got away from me"* — an explicit statement of not having done it, which is
> what that label is now reserved for.
>
> **The real gain is not the labelling, it is what the system no longer claims.** Before, it
> asserted a fact about a life it had one paragraph of evidence about. Now it asserts only
> that something is missing from *this answer* — checkable against the transcript — and puts
> the rest to the man who knows. The class of unsupportable claims got smaller, which matters
> more than the distribution did.
>
> **`c2.anchor.2` got worse and should be split.** *Preparation is real but stale* now splits
> four ways across 22 points — inventory 11, candidate 6, worked 4, answer 1. A finer
> distinction did not resolve a mixed anchor, it exposed it further. The anchor asserts a
> credit and a fault in one sentence and the pipeline cannot tell which it is being asked to
> report.
>
> **Rejections rose from 6 to 14 across all runs**, which is the new gate check (an inventory
> point that asks nothing) and the prescription guard now covering the *go and get it*
> branch. They are caught and retried rather than shipped; single CLI runs still complete on
> one attempt.
>
> The standing caveat is unchanged — consistency is not correctness, and a stable filing can
> still be the wrong filing. But the exposure is smaller than it was, because the filings the
> system now makes are ones the transcript can support.

**[SETTLED] One answer can earn a credit and a fault from the same criterion, and should report both.** (Grant, 2026-07-28.)

A critique is not a verdict to be reached, so nothing has to resolve to a single finding. *Preparation is real but stale* is two true things about one answer: the EMT was earned and that is worth saying, and nothing has happened in four years and that is worth saying too. Reporting only the fault tells him half of what is true about him; reporting only the credit tells him the other half.

So the critique carries **what you did well** and **what you could work on** as its top-level shape, and one rubric clause may legitimately produce a point in each.

This corrects a reading error, recorded because the error is instructive. The classification harness showed `c2.anchor.2` producing four different labels across 22 points and it was written up as a defect — a mixed anchor the pipeline could not resolve, with a recommendation to split it. **That recommendation is withdrawn.** The same write-up already carried the caveat that undoes it: grouping by clause conflates one ambiguous clause with two distinct findings that share a citation. It was applied to `c2.anchor.5` and not to `c2.anchor.2`, where the split was mostly credit-versus-fault rather than disagreement about the same finding.

Two consequences:

- **The harness stops flagging a clause as contested for mixing a credit with a fault.** Contest is measured across the gap labels only. A clause that sometimes credits and sometimes faults is doing its job.
- **What worked is required where it exists, not offered where convenient.** The prompt had *"lead with what the answer did, where there is anything to lead with"*, which invites skipping it. Across twenty runs of the weak teamwork answer only seven points recorded anything positive — roughly one in three critiques said nothing at all about what the man did right, to a man about to be told several things he did wrong.

**[SETTLED] Critique identifies gaps; it never supplies content.**
It may name what is missing and ask for the candidate's own material. It may not provide a model answer, sample language, or an example response.

- Permitted: "You claimed a service motive and gave no instance of it. What's yours?"
- Rejected: "Here's a strong answer to this question." / "Try saying something like…"

*Rationale:* the level 3 anchor is the clone answer — correct, generic, indistinguishable — which exists because candidates all read the same prep advice. A coaching tool that supplies content manufactures clone answers at scale. This is the most-requested feature that must not be built.

**[SETTLED] Critique speaks to how an answer is likely to read, tied to observable behavior.**
It may not assert a score the candidate received, or attribute an internal state.

- Permitted: "Six certifications in forty seconds with no account of why any mattered — that reads as résumé recital."
- Rejected: "You came across as arrogant." / "You don't seem to genuinely care."

**[SETTLED] Answers are not scored independently and summed.**
Real panels build a picture; a flag raised early shapes interpretation of later answers. A pipeline that scores each answer in isolation and sums will not reproduce board behavior.

**[SETTLED] Two classes of critique point flow through the verification gate.**
*Rubric-anchored* points must tie to a criterion. *Measurement-anchored* points tie to a computed metric and are trivially verifiable — the second class is cheap to validate and should be used where it applies.

---

## 4. Practice loop

**[SETTLED] Novel question every session. No preview. Timed. No re-record.**

*Rationale — this is the core insight of the session.* The skill a board tests is not "answer this question well," it is "construct an answer to something you haven't seen, right now." Repeating a question trains the former and produces a candidate who is excellent at one question and back to square one on the next. Allowing a re-record converts construction into rehearsal and the actual skill never gets exercised.

**[PROVISIONAL] The underlying trainable skill is inventory and retrieval, not composition.**
Strong interviewees carry eight to ten real incidents from their own life — what happened, what they did, what they'd do differently — and map the asked question onto the best fit in real time. The surprise is in the retrieval, not the material. Freezing usually means no inventory; rambling means inventory without an index. This is trainable, separable from answer-writing, and consistent with the no-content rule since every incident is the candidate's own.

**[SETTLED] Progress is tracked on question-independent behaviors, not answer quality on a repeated question.**
Askable of any answer to any question: did it contain a specific incident he was personally in, did he name what he'd do differently, did he stop when finished. Far more stable than a quality judgment and portable across a rotating question bank.

Progress view reads roughly: *across your last eight answers, to eight questions you'd never seen, here's what you did consistently and here's what still drops out under pressure.*

---

## 5. Audio input

**[SETTLED] Audio input, not typed answers.**
Text cannot see pace, fluency, hesitation, or length. Audio recovers a real portion of the delivery layer. It does not recover presence, eye contact, or likeability, and the product must not imply otherwise.

**[SETTLED] Architecture: browser capture → batch ASR with word-level timestamps → deterministic metrics computed in our own code → transcript plus metrics into the critique step.**
No streaming, no real-time. A mock board does not need sub-second latency.

**[SETTLED] Most delivery signal is arithmetic on timestamps, not audio ML.**
Words per minute, answer duration, time-to-first-word, pause count and distribution, filler rate per hundred words, longest unbroken stretch. Deterministic, zero variance, comparable across sessions.

**[SETTLED] No voice-based confidence or emotion scoring.**
Unreliable, and carries documented bias by accent, gender, and first language. Scoring how a voice sounds while calling it composure is both wrong and indefensible. Note the distinction: voice recognition means biometric speaker identification and is a different technology from transcription. Recruit does transcription only.

**[SETTLED] Transcribe, compute, discard.**
Audio is retained only if the candidate opts in for self-review. Voice recordings are sensitive in a way typed answers are not, and several states regulate them specifically.

**[PROVISIONAL] Playback of the candidate's own answer may be the strongest feature in this area.**
People are startled by their own filler rate in a way no counter reproduces.

### Implementation warnings

- **Filler words are commonly stripped by default.** Most ASR cleans up disfluencies; Whisper in particular tends to drop "um" and "uh" and tidy false starts. Verify disfluency preservation on our own audio before relying on filler metrics. Most likely silent failure in this feature.
- **Word-level timestamps may be a priced add-on.** Timestamps, diarization, and streaming are commonly unbundled; effective cost can run 2–4× the advertised rate once enabled. Immaterial at our volume, but do not budget off the headline number.
- **ASR accuracy varies by speaker.** Word error rates are higher for non-native and some regional speakers. A worse transcript yields worse critique, degrading feedback quality for exactly the candidates who would benefit most. Spot-check across accents before launch.

---

## 6. Metric reporting rules

**[SETTLED] Bands, not minima.**
Pace, answer length, and pause frequency all have optimal ranges. Any display implying lower-is-better will train stilted delivery. Pace sits near 150 wpm; answer length roughly one to two minutes.

**[SETTLED] The thinking pause and the stall are different metrics.**
A beat before answering is composure — the candidate who fills it with "that's a great question" is doing worse. A gap mid-sentence is losing the thread. Same silence, opposite meaning, distinguished only by position. Lumping them teaches candidates to start talking immediately, which is the wrong lesson.

**[SETTLED] Filler feedback is awareness with context, not a target to minimize.**
Acute self-consciousness typically raises the count before lowering it, and driving it to zero produces dead delivery. Report rate, typical range, and whether it is high enough to distract.

**[SETTLED] One improvement target at a time.**
A candidate working on three metrics works on none.

---

## 7. Validation

**[SETTLED] The validation question is whether critique improves the next answer — not whether the score is accurate.**
Score accuracy is expensive to establish and not what the product claims. Testable now, with three people and no pipeline: hand someone the Criterion 2 anchors, have them answer a fresh question, see whether the second answer is better.

**[SETTLED] Measure the scorer's noise floor before building any progress display.**
Run one answer through the scorer ~20 times and examine the spread. If run-to-run variance exceeds plausible monthly improvement, the progress chart is noise and may show a candidate regressing when he improved. Ten minutes of work. Do it before step 2.

> **Run 2026-07-27** — `scripts/recruit_noise_floor.py`, Criterion 2 anchors, scorer
> `claude-sonnet-5` at effort `high` with adaptive thinking. Three synthetic answers.
>
> | Fixture | n | Distribution | Spread | σ |
> |---|---|---|---|---|
> | Boundary (3/4 territory) | 20 | 3×15, 4B×5 | 1 | 0.43 |
> | Unambiguous 2 | 10 | 2×10 | 0 | 0.00 |
> | Unambiguous 5 | 10 | 5×10 | 0 | 0.00 |
>
> **Away from a boundary the scorer is perfectly stable** — twenty runs across two
> unambiguous answers produced twenty identical scores. All instability is at the
> boundary, it never exceeds one anchor, and it is one-directional: the boundary answer
> came back 3 or 4B, never 2 or 5. Where a 4 was awarded the route tag was 4B all five
> times, so the 4A/4B split held.
>
> **The variance is not noise — it is a specific rubric ambiguity, and it is legible.**
> The deciding-criterion output shows the two camps disagreeing about exactly one thing:
> the 4B boundary rule reads *"any real step past the eligibility list, with something to
> show for it, is a 4B."* The runs scoring 4B treat two unelaborated ride-alongs as a real
> step past the list. The runs scoring 3 accept that they are past the list but hold that
> *something to show for it* is unmet, because the candidate never says what the
> ride-alongs changed. Both readings are faithful to the text. **Tighten that clause and
> the variance should collapse** — the fix is in the anchor, not the model.
>
> **Consequence for the progress display:** it confirms the §4 decision rather than
> overturning it. A score-over-time chart would have been noise-dominated precisely where
> most candidates sit — a candidate genuinely parked between 3 and 4 would appear to
> oscillate 3 → 4 → 3 with nothing about him changing, while a real month of movement on
> this criterion (enrol in something, finish it, be able to say what it changed) is often
> worth less than the one anchor the scorer wobbles by. Progress stays on
> question-independent behaviors. **Those behaviors have not been measured for stability
> and should be, before step 8** — being nearer to binary, they ought to be steadier, but
> that is an expectation rather than a result.
>
> Re-run after any anchor change. The number is a property of the rubric at least as much
> as of the model.

> **Re-run 2026-07-28, after tightening the 3/4B boundary.** The clause now states the
> test explicitly — a step past the eligibility list counts toward 4B only when he can say
> **what it changed** — which is the test the level 4B and level 3 anchors already applied.
> The boundary sentence was the outlier, not the anchors. A fourth fixture was added at the
> same time: a candidate who *can* account for his step past the list but whose pursuit is
> aimed at qualifying rather than at becoming good at the work.
>
> | Fixture | n | Distribution | Spread | σ |
> |---|---|---|---|---|
> | Past the list, cannot account for it | 20 | 3×20 | 0 | 0.00 |
> | Past the list, can account for it | 20 | 4B×20 | 0 | 0.00 |
> | Unambiguous 2 | 10 | 2×10 | 0 | 0.00 |
> | Unambiguous 5 | 10 | 5×10 | 0 | 0.00 |
>
> **Sixty runs, zero variance, and the 4B band is still reachable** — twenty of twenty on
> the new fixture, every one tagged 4B. That second fixture is the one that matters: a
> boundary made stable by becoming unreachable is closed, not fixed, and this shows the
> tightening did not close it. The 4B reasoning also separated the two questions cleanly,
> clearing the boundary on *what it changed* and then placing the answer at 4B rather than
> 5 on *what the pursuit was aimed at*.
>
> **Caveat, and it is not a small one.** The tightened clause carries two worked examples,
> and both fixtures sit close to them — one run cited the example by name. So this
> measures whether the scorer can apply a worked example to roughly the case the example
> was written from, which is easier than the general problem, and some of the zero is that
> rather than a genuinely sharper rubric. The honest read: **the clause is no longer
> ambiguous on the case that split it**, which is what it was asked to fix. Whether it is
> unambiguous generally is untested. The next fixture worth writing is one neither example
> reaches — a partial account, where he says something about what the step changed but not
> much. That is where the boundary will next be soft, and it is not covered here.

> **Criterion 3 draft, run 2026-07-28.** Same harness, `c3`. Criterion 2 was re-run under
> the new scorer-region extraction and is unchanged (3, 4B, 2, 5 — all clean), so the two
> sets stay comparable.
>
> | Fixture | n | Distribution | Spread | σ |
> |---|---|---|---|---|
> | Qualified, self-focused — **the target anchor** | 20 | 2×20 | 0 | 0.00 |
> | Between 2 and 3 (asked, but crew undifferentiated) | 20 | 3×19, 2×1 | 1 | 0.22 |
> | Generic, correct, no incident | 10 | 3×10 | 0 | 0.00 |
> | Changed by a named person | 10 | 5×10 | 0 | 0.00 |
>
> **The level 2 anchor fires on the case it was written for, twenty times out of twenty.**
> That is the gap Criterion 2 recorded, and in draft it is now closed: a candidate who
> scores 4–5 on Motivation and is the only agent in his own team stories lands at 2 here
> instead of passing through unpenalized.
>
> **One soft spot, and it is nameable.** The single dissenting run on the boundary fixture
> did not misfire. It applied scoring note 3 — which flags *"I've always gotten along with
> everyone"* as sometimes a bigger tell than an honest conflict would have been — and read
> that closing line as pulling the answer down to 2. The reading is available because the
> note says a flag exists and **no anchor says where it lands.** Same shape as the 3/4B
> defect: a test stated in one place, unresolved in another. Unlike that one the anchors do
> not already answer it, so it is a genuine judgment rather than an inconsistency to tidy.
> Recorded as an open item, deliberately not fixed.
>
> **The caveat here is much larger than Criterion 2's and the number should be discounted
> accordingly.** Claude wrote both the rubric and the fixtures. A clean run therefore
> measures mostly whether the fixtures match the anchors they were written alongside —
> internal coherence of one draft, checked against itself. It is **not** evidence that the
> anchors are right about the fire service, and it is weak evidence that they would hold up
> on answers written by someone else. Criterion 2's numbers mean more than these do,
> because a fire captain wrote those anchors.
>
> What the run is genuinely good for: it shows the level 2 anchor is **operable** — it
> catches its target reliably and does not swallow the adjacent case. That is the one thing
> a drafted anchor can be checked for without an SME in the room. Everything else waits for
> review.

> **Criterion 3 re-run 2026-07-28, after adding the not-assessable outcome.** Two fixtures
> added for the no-team-history case. **The fix works on the case it was written for and
> made the neighbouring boundary worse.** Both halves are the result.
>
> | Fixture | n | Outcome | Spread | σ |
> |---|---|---|---|---|
> | No team history, genuinely nobody there | 10 | **not assessable ×10** | — | — |
> | No team history, material undersold | 20 | not assessable ×3, 3×15, 2×2 | 1 | 0.32 |
> | Between 2 and 3 *(was 3×19, 2×1)* | 20 | 3×17, 2×2, **4A×1** | 2 | 0.38 |
> | Qualified, self-focused | 20 | 2×20 | 0 | 0.00 |
> | Generic, no incident | 10 | 3×10 | 0 | 0.00 |
> | Changed by a named person | 10 | 5×10 | 0 | 0.00 |
>
> **The escape hatch fires cleanly on the clean case.** Ten of ten on the one-man-shop
> candidate, and the reasoning cites scoring note 3 rather than reaching for a low anchor.
> The candidate who has genuinely never worked alongside anyone is no longer scored 2 for a
> history he could not help. That was the point, and it holds.
>
> **The undersold case splits three ways, and the gap is nameable.** Note 3 says *score what
> he offers and note that he undersold it* — but this candidate offers raising his brothers
> in one clause and immediately discounts it. Three defensible readings followed: it is
> enough to score (3), too thin to score (not assessable), or self-focused within itself
> (2 — one run held that even in the brothers story the siblings are beneficiaries rather
> than agents). **The note does not say what to do when the offer is real but too thin to
> score.** That is the same shape of defect as the 3/4B clause and it wants the same fix.
>
> **The 2/3 boundary regressed: σ 0.22 → 0.38, spread 1 → 2, and a 4A appeared.** The 4
> reasoning held that a teammate saying *"things are fine"* when asked is a named other
> person taking an action, which clears the level 4 boundary. That reading was available
> before and did not surface before. The plausible mechanism — **unproven** — is that note
> 3's instruction to hunt for undersold team material primes the scorer to find agency in
> thin places, and the level 4 boundary does not say what counts as an action. Worth stating
> plainly: **fixing the false negative cost stability at the adjacent boundary.** A rubric is
> not a set of independent clauses, and this is the second time an edit here has moved
> something it was not aimed at.
>
> **Stopping the iteration here, deliberately.** The remaining fixes — what counts as an
> action at the 4 boundary, what to do with a too-thin offer — are the same self-referential
> loop as before: Claude tuning Claude's rubric against Claude's fixtures. Each round makes
> the draft more internally consistent without making it more correct, and increases the
> risk of over-fitting to fixtures nobody else wrote. The draft has done its job when it
> gives a reviewer something specific to disagree with, and it now does.
>
> *Harness note:* roughly 3–5% of calls return generation garbage appended to the free-text
> field, and occasionally unparseable JSON. Not truncation — output runs ~280 tokens against
> a 16k cap and stops on `end_turn`. Scores parse correctly throughout, so distributions are
> unaffected; a single retry was added so a hard failure does not quietly shrink n.

**[SETTLED] Competitive context is now part of the step 3 decision.**
stationvisit.com ships AI-scored mock firefighter oral boards across five dimensions with a rubric attributed to experienced firefighters, free first interview, subscription thereafter. Step 3 is therefore not "is Recruit worth building" in the abstract but "do critiques generated from these anchors read as materially better than what already exists" — a cheaper question, answerable before the pipeline is built.

---

## 8. Provenance

**[SETTLED] The anchors represent one captain's scoring judgment and the product says so.**
Not a national standard, not a survey of practice. A candidate is being told how this panelist reads the answer. For a coaching tool that is legitimate and arguably more useful than a false consensus — but it must be labeled.

**[SETTLED] Published sources are used for coverage, never for anchors.**
Generic material is good for dimension names, scoring conventions, and board structure. It is useless for discrimination between adjacent scores, which is the only part that produces actionable critique.

**[SETTLED] Vendor-authorship screening applies to gap-filling, not just background.**
Most public oral board material is authored by vendors selling preparation services, who have a commercial interest in presenting the board as decodable. Screen any source proposed for filling an anchor gap.

**[SETTLED] The remedy for single-panelist bias is more panelists, not more web content.**
Target two or three captains from departments with differing board formats, scoring against these anchors independently. Agreement indicates trade-wide judgment. Disagreement is documented as a split rather than averaged away.

---

## 9. Superseded decisions

Recorded so they are not re-proposed.

**Pairwise comparison of a new answer against the candidate's prior answer to the same question.**
Proposed as a reliability fix — pairwise comparison is more stable than absolute LLM scoring. **Rejected:** it requires question repetition, which trains the wrong skill (see §4). The reliability concern is real and is addressed instead by scoring question-independent behaviors and leaning on deterministic metrics.

**Anchoring level 2 on "has not met minimum qualifications."**
**Rejected:** collided with level 4, and eligibility varies by department. Replaced with staleness — real steps taken, nothing since, no recent date, no stated next step. Both 2 and 4 have incomplete files; the 4 is moving and the 2 is not.

**Scoring the self-focused candidate at level 1 on Motivation.**
**Rejected:** he may be thoroughly prepared. Routed to Teamwork.

**Treating "comes off as passion, not bragging" as unusable because it is not behavioral.**
**Partially withdrawn.** It is unusable as a scoring instruction, but it accurately describes what happens in the room. Resolution: anchor on behavior, and let critique speak to how that behavior is likely to land.

---

## 10. Open items

| Item | Notes |
|---|---|
| Criterion 1 anchors | Scope settled (see below), anchors unwritten |
| Criterion 1 naming | "Communication" overclaims what audio can see. "Answer Construction" plus a separate delivery sub-score is the candidate. **[OPEN]** |
| Criterion 3 | **Drafted 2026-07-28 by Claude, unreviewed** — `recruit_rubric_c3_teamwork.md`. The qualified-self-focused anchor exists and fires 20/20. Needs SME review before it is anything more than a proposal; the anchors represent nobody's judgment yet. |
| ~~Is the weak teamwork answer really all development?~~ | **Dissolved by Grant 2026-07-28.** It was the wrong question to put to the model. Ask the candidate: is there a better story, and if not, that is the thing to go and get. Development verdicts on that fixture went 74 to zero. |
| ~~c2.anchor.2 — mixed anchor~~ | **Withdrawn 2026-07-28.** Not a defect: the anchor is two true things about one answer, and the critique should report both. See §3. |
| C3 — where the unfalsifiable-claim flag lands | Scoring note 4 flags *"I've always gotten along with everyone"* as a tell but no anchor says whether it pulls an answer to 2 or is just noise on a 3. Found by the harness. |
| C3 — what counts as "an action" at the 4 boundary | A teammate answering *"things are fine"* when asked was read as a named other person taking an action, putting a borderline answer at 4A. The boundary says an action is required and does not say what one is. |
| C3 — a real but too-thin offer | Scoring note 3 says score what he offers; it does not say what to do when the offer is one dismissed clause. Splits three ways between 3, not-assessable, and 2. |
| Not-assessable outcome on other criteria | Implemented on C3. Criterion 2 should get it on review; the rule is rubric-wide even though it bites hardest on Teamwork. |
| **Not assessable vs. did not answer** | Surfaced by the first live pipeline run. An off-topic answer — the candidate talks about department budgets instead of his own motivation — came back not-assessable on one run and 1 on another. These are different things and the rule does not yet separate them: not-assessable is for a life that does not contain the material, whereas an off-topic answer is a *failure to produce* material he may well have. Conflating them lets a non-answer escape scoring, which is the same hole the level 2 escape-hatch clause was written to close. Needs a sentence saying so. |
| Criteria 4, 5 | Unwritten. |
| Metrics spec | Pause classification, band definitions, stall threshold. Definitions matter more than they look. |
| ~~Noise floor test~~ | **Run 2026-07-27** — see §7. Stable away from boundaries; ±1 anchor at the 3/4B boundary, 25% of runs. |
| ~~3/4B boundary anchor~~ | **Tightened 2026-07-28**, re-run clean at 60/60. The test is now *can he say what it changed* — the same test the 4B and 3 anchors already applied. |
| Partial-account fixture | The untested case the tightening leaves behind: he says *something* about what a step changed, but thinly. Neither worked example reaches it, and it is where the boundary will next be soft. |
| Behavior-stability check | The progress display rests on question-independent behaviors, whose run-to-run stability is assumed, not measured. Same harness, before step 8. |
| 4A/4B split | Came out of a single pass. Wants a second panelist before it is settled. The scorer applied it consistently (5/5 runs tagged 4B), which says the split is legible — not that it is right. |
| Question bank | Size and rotation policy undetermined; the novel-question design makes bank depth a hard requirement rather than a nice-to-have. |

**Criterion 1 scope, settled:**
Scored across the whole board rather than on a designated question, so anchors cannot reference a specific answer. Audio can see answer construction (did he answer what was asked, does the answer have a shape, are claims specific, does he stop when done, will he say what he got wrong) plus pace, fluency, and length. It cannot see presence, eye contact, nerves, or likeability. The unscoreable half is real, is scored by actual panels, and the product should say plainly that it has to be worked on with a person.
