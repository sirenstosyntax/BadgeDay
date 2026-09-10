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

**Not assessable is a finding, and a non-answer is not evidence for it.** (2026-07-28, closing the gap the pipeline exposed.)

Two runs of the same empty answer came back *not assessable* once and *1* the other, and the instability was in the rule rather than the model. *Not assessable* had been doing two jobs: reporting that a candidate's life lacks the material, and reporting that an answer gave us nothing to go on. Those are opposite epistemic positions — the first is a conclusion, the second is the absence of one — and collapsing them means a man who simply did not answer gets told something about his history that nobody established.

Three outcomes, not two:

- **Scored.** The answer supplies enough to apply an anchor.
- **Not assessable.** The answer *positively establishes* that his life does not contain the material — he says he has driven alone since he was twenty-one, that there was nobody else there. A conclusion, and it must be earned.
- **Not answered.** Silence, a refusal, a request to repeat the question, a pivot to something else. No basis either way. **This is the fork again, one level up**: we cannot tell and he can, so the honest output asks him rather than concluding anything.

The gate enforces the asymmetry mechanically, because the two errors do not cost the same. A wrong *not answered* costs him one question. A wrong *not assessable* tells a man his life is missing something on evidence nobody has:

- **A not-assessable outcome must quote the words that establish it.** If the model cannot point at him saying he has not done the thing, it may not conclude that he has not. This is the same discipline as citation grounding, applied to a claim about a person rather than a claim about a document.
- **A not-answered outcome must ask.** Without the question it is just a low score with better manners.

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

**[SETTLED 2026-08-17] The advice is a gate requirement, not a preference. A critique must give the candidate at least one thing to act on.** (Grant, restating the decision above when it turned out the work had drifted off it.)

The decision at the head of this section had been stated and then not enforced, and the measurement said so: **twenty runs of a strong answer produced five critiques carrying anything forward-looking; the other fifteen were pure credit.** Every point in those fifteen passed the whole gate — anchored, grounded, correctly classified, no supplied language. Nothing was wrong with any point. What was wrong was the set, and no per-point check can see that.

Prompt-tuning had already been tried on it: 1-in-5 → 5-in-20, and then it stopped. That is what asking nicely buys. So it is now `_verify_actionable` in `app/critique/verify.py` — a critique whose every point is `improvement: "none"` is rejected and regenerated, the same way an uncited point is.

Three things the rule deliberately does not do:

- **It does not require praise.** One-directional on purpose. An off-topic answer honestly has nothing to praise and a gate demanding some would manufacture it, teaching a candidate that a weak answer was half good. The shape *"here is what worked, here is something to consider"* is the usual output, not the enforced one.
- **It does not require fault.** The actionable point on a strong answer is usually an `inventory` one — has he a better instance — or a `risk`. Neither says he did badly.
- **It does not loosen the prescription guard.** Something to act on is required; supplying him with wording, or with the one true next step, is still rejected. The two rules meet on every inventory ask and both have to be satisfied at once.

**What this demotes.** Score-boundary precision is now explicitly not where effort goes. The score is internal, the candidate never sees it, and several of the longest-running items in §10 — the 4A/4B split, band distribution, one-anchor wobble at 4B/5 — are about a number nobody reads. They are not thereby worthless: a route tag exists to send critique at the axis that is short, so the question to ask of 4A/4B is *does the critique address the right thing*, not *is 4A ever assigned*. Judge them by what reaches the candidate, and close the ones that do not.

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
- **[SETTLED] How prescriptive development advice gets.** **A development point names what is absent and may name the category; it does not prescribe a specific certification, programme or provider.** Naming a gap is low risk; naming the programme that fills it is career advice with a cost in time and money, delivered to someone who cannot check it — and it dates badly, since a provider named today is wrong in eighteen months and nothing in the product will notice.

  **This entry was stale and said the question was open.** It was settled on 2026-07-28 and recorded in `recruit_scope.md` open question 1 — *"offer possible ways the improvement could be met — plural, routes not providers, spanning the cost and access range"* — while this section went on carrying an "interim default until Grant sets the line" that described the same rule. Reconciled 2026-08-17 after Grant re-confirmed the same terms. The two documents agreed on the substance and disagreed on whether it had been decided, which is the more expensive kind of drift: it does not produce a wrong build, it produces a decision made twice.

  `_PRESCRIBES_REMEDY` in `app/critique/verify.py` is the enforcement, deliberately narrower than the rule — it blocks the directive forms and the definite singular while permitting a route to be named neutrally, because the rule asks for a menu and a menu is made of routes.

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

**[SETTLED] Development advice offers possible ways to meet the gap — plural, and never one.** (Grant, 2026-07-28. Settles open question 1.)

Naming a gap and leaving him to work out what to do about it is unhelpfully austere. Naming the single thing he must do is career advice we cannot stand behind. The line is **possible ways**: here are routes people take to build this, pick the one that fits your life.

The plural is the whole safeguard, and it does three things at once. It does not presume his circumstances — a man with a mortgage and two children cannot do what a nineteen-year-old can. It leaves the choice where the fork already leaves it, with the person who knows his own constraints. And it is far harder to be badly wrong with a menu than with an instruction: if one route does not fit, another may, whereas a single prescription that does not fit is simply bad advice delivered confidently.

Rules:

- **More than one route, always.** A single route stated on its own is a prescription wearing different clothes. So is *"the best way to…"* — definite framing smuggles the singular back in.
- **Routes, not providers.** A category is durable and safe: volunteering with a district, riding along, taking work that puts him on a crew, a certification. A named academy, vendor or programme is an endorsement, it dates, and we have no basis for it.
- **Span the cost and access range deliberately.** This is where it would quietly fail. Offer three routes that all cost money and free weekends and the candidate the *effort relative to opportunity* note exists to protect has been handed a list he cannot act on — and told, in effect, that the answer is to be someone with more money. At least one route should cost nothing but time.
- **Still never supply the words.** Unchanged and unrelated. Ways to build experience are fine; sentences to say at the board are not.

Mechanically the gate narrows rather than opens. It keeps rejecting the directive forms — *you should*, *you need to*, *I recommend*, *go get your…* — and stops rejecting the neutral naming of a route, which is what a menu is made of.

> **Criterion 3 SME review, 2026-07-29 — Grant scored blind, 11 answers.** Three
> agreements, eight divergences, and the divergences are not scattered.
>
> | | you | anchors | |
> |---|---|---|---|
> | A — qualified, self-focused | 2 | 2 | **agree** |
> | I — changed by a named person | 5 | 5 | **agree** |
> | K — other person acts, appetite instrumental | 4 | 4B | **agree** |
> | B — handles friction, people as process | 4 | 3 | +1 |
> | C — teammate answers but changes nothing | 3 | 2 | +1 |
> | D — the clone answer | 4 | 3 | +1 |
> | F — teammate discloses and fixes it | 5 | 4B | +1 |
> | E — never had a problem with anyone | 5 | 2 | **+3** |
> | G — loves the crew, ducked the conversation | 1 | 4A | **−3** |
> | H — thin offer (brothers) | *incomplete* | not assessable | — |
> | J — one-man shop | *incomplete* | not assessable | — |
>
> **The anchor the criterion was written for is right.** A is the qualified self-focused
> candidate — the gap Criterion 2 recorded and the reason C3 exists — and it scored 2 from
> both. So does the top of the scale. The load-bearing parts hold.
>
> **The anchors are systematically harsh.** Five of the six numeric divergences run the same
> way: Grant scores *higher*, mostly by exactly one level. That is not scatter, it is a
> calibration offset — the draft reads a competent answer as a mediocre one and a mediocre
> one as a poor one. **`c3.note.2` decided five of the eight divergences**, which makes the
> behavioural-frame clause the single biggest lever in the rubric and the first thing to
> loosen.
>
> **G is the reverse, it is the largest gap, and it is the most valuable data point in the
> exercise.** The candidate volunteers on an ambulance service, talks warmly about the crew
> by name, and then: a colleague repeatedly fails to restock the rig, he raises it once
> "kind of jokingly", the man gets funny about it, and he quietly starts checking it himself
> — *"it was easier than having the conversation, honestly."* The draft read the warmth as
> dominant and scored 4A. Grant scored **1**, the anchor reserved for the problem being in
> the room.
>
> No inference in the draft would have produced that, and it is exactly the class of
> judgment `recruit_oral_board_sources.md` says only experience supplies. Grant's reasoning
> is recorded in the next entry rather than guessed at here.
>
> **"Incomplete" is not a value the exercise offered**, and he used it for both H and J —
> the thin offer and the genuinely solitary working life. The rubric treats those as
> different outcomes (`not assessable` is a finding about a life; `not answered` is the
> absence of one). He treated them as the same thing and as a property of the *answer*.
> That bears directly on §2's three-outcome rule and is an open question, not a scoring
> disagreement.

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

**[SETTLED] A critique carries a reuse or delivery risk, and it is not a gap.** (Grant, 2026-08-06.)

A fourth classification, `risk`, from the answer F calibration. A candidate takes one good story to several boards, and how he introduces it is not fixed the way the events are — so there is a class of thing worth telling him that **is not a fault in the answer he gave**. The case that produced it: opening strong evidence with an unsupported self-assessment, which invites a panel to weigh the claim instead of the story.

The reason it needs its own class rather than a bullet among the gaps is the reason `candidate` needed one. A risk names something *absent* from the answer. Rendered among the faults it tells a man he did badly at something he did not do, and it is attached to material that worked, which is the reverse of a gap.

- **It never moves the score.** There is nothing here to deduct for. Scoring note 10 on Criterion 3 says so where the scorer reads it.
- **At most one.** A list of cautions is a fault list wearing a different hat.
- **Names the pattern, never the replacement**, which is the standing prohibition rather than a new one.
- Where the wording is actually *in* the answer it is not a risk; the anchors govern it. This is also why the ruling **does not settle Criterion 3's note 5** — where that flag lands when he really says it is still open.

**[SETTLED] The rubric's own vocabulary never reaches the candidate.** (Grant, 2026-08-06.)

The same review found a critique that was substantively right and written to the instrument: the answer failed *"the cast-of-story test"*, and *"this criterion runs"* across the whole board. Both true, neither candidate-facing. He has never seen the rubric, and feedback in its vocabulary reads as a machine grading rather than as somebody who has done the job telling him what he did.

A sixth check in the gate, on `observation` and `ask` only. `determination` is internal and naming the clause is its job, so it is deliberately not checked. The guard is narrow on purpose — a false rejection costs a sound point or a retry, which is the lesson from the contraction bug in the supplied-language check.

**[SETTLED] Answer-specific coaching is separated from the broader evidence inventory, in the ordering and in the words.** (Grant, 2026-08-06.)

The same review again. An inventory gap — that the candidate has not shown himself delivering an uncomfortable correction anywhere — was presented as the primary weakness of a strong answer. It was not: it would have been equally true of a better answer, and it is a broad observation that happened to surface here.

The distinction already existed in the `improvement` field and was invisible on the page, which is where it matters. So: the strongest thing the answer establishes leads, answer-specific gaps come before inventory gaps, the inventory heading says *beyond this answer*, and risks are last under their own heading. Whatever comes first is read as the verdict.

---

## 4. Practice loop

**[SETTLED] Novel question every session. No preview. Timed. No re-record.**
The post-take Record again control was removed 2026-09-09 (Grant) so the UI matches this constraint.

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

**[PROVISIONAL] Deepgram is the first candidate, and Azure is not — despite Azure already being in the stack.** (2026-07-28, from documentation only.)

The obvious choice was Azure. Document Intelligence already runs in `sts-examgen-rg`, hosting is Azure Container Apps, and adding a second vendor means a second account, a second key and a second bill. The evidence went the other way.

- **Deepgram** documents `filler_words=true` as an explicit switch, at no extra cost and no latency impact, and returns per-word `start`, `end`, `confidence` and `punctuated_word` by default rather than as a priced add-on. `punctuated_word` matters more than it looks: it is what lets a pause between sentences be told from one mid-sentence, which §6 says are opposite signals.
- **Azure AI Speech** documents disfluency removal as *off by default*, which reads as though filler words survive. Microsoft's own Q&A says otherwise: users migrating from other services report "uh", "um" and "gonna" missing from Azure transcripts that competitors returned, and the Microsoft answer attributes it to model sensitivity rather than a setting — so there is nothing to switch on. **A documented default of "we keep them" and a practical result of "they are gone" is precisely the silent failure §5 warns about**, and it is the more dangerous shape because the docs read as reassurance.
- **CrisperWhisper** is purpose-built for verbatim transcription with word timestamps around disfluencies, and is the strongest fit on capability. It is a model rather than an API, so it means running inference ourselves. Noted as the fallback if the hosted options fail, not as a V1 choice — a self-hosted GPU dependency is a large operational commitment to take on for one metric.

**This is documentation, not evidence, and the file should not pretend otherwise.** Marketing pages advertise clean transcripts, which is the failure mode; Azure's own docs said the right thing and the practice did not match. `scripts/asr_check.py` is the instrument that settles it, and it needs thirty seconds of real speech — not TTS, whose "um" is pronounced as a full clear word and would pass a test that real hesitation fails.

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

> **Criterion 3 re-run 2026-07-29, on the rubric as rewritten from Grant's blind review.**
> Same harness, same fixtures, so the numbers are comparable to the two runs above.
>
> | Fixture | n | Outcome | Spread | σ |
> |---|---|---|---|---|
> | Qualified, self-focused | 20 | 2×20 | 0 | 0.00 |
> | No team history, material undersold *(was 3-way split)* | 20 | **not assessable ×20** | 0 | 0.00 |
> | No team history, genuinely nobody there | 10 | not assessable ×10 | 0 | 0.00 |
> | Between 2 and 3 *(was 3×17, 2×2, 4A×1)* | 20 | 3×20 | 0 | 0.00 |
> | Generic, correct, no incident *(was 3×10)* | 10 | **4B×10** | 0 | 0.00 |
> | Changed by a named person | 10 | 5×10 | 0 | 0.00 |
>
> **Eighty runs, zero variance, and the two regressions the previous run recorded are both
> gone.** The undersold offer went from splitting three ways to not-assessable twenty times
> out of twenty, which is the settlement written into note 4. The 2/3 boundary that had
> regressed to σ 0.38 with a stray 4A is back to 3×20. The rewrite did not trade one
> boundary for another — the first edit here that has not.
>
> **The generic-correct fixture deliberately moved 3 → 4B**, ten out of ten, which is the
> rewrite's intent rather than drift: a candidate who states the right approach plainly is
> now a 4 short of evidence rather than a 3. Worth flagging because it is the largest
> single behavioural change in the criterion and it raises the floor for a whole class of
> answer. Whether that is *right* is Grant's call, not the harness's.
>
> The Criterion 2 caveat about self-referential tuning is now weaker but not gone: the
> anchors were rewritten from an SME's scores on answers he had not seen scored, which is
> real external signal, but the fixtures are still Claude's and still written alongside an
> earlier draft of the anchors.

**[SETTLED] The noise floor is a property of the path, not just the rubric — measure the one that ships.**
Measured 2026-07-29 and it was not expected. The two runs above put the revised Criterion 3 at **80 runs, zero variance on the scorer path**. The same rubric text, on the same answers, through **`critique_answer` — the path that actually ships — moves by up to three anchors.**

Two consecutive full runs of `scripts/recruit_review_compare.py` disagreed with each other on **four of eleven** answers, having changed nothing but a bug fix that touched one unrelated answer. Five runs per answer on the five that moved:

| Answer | Grant | Pipeline over 5 runs | Spread |
|---|---|---|---|
| B | 4 | 4B×4, 2×1 | 3 anchors |
| E | 5 | 4B×3, 3×1, 2×1 | 3 anchors |
| F | 5 | 4B×4, 5×1 | 2 anchors |
| I | 5 | 5×3, 4B×1, 4A×1 | 2 anchors |
| K | 4 | 4B×5 | 0 |

E never once reached the score Grant gave it and swung from 2 to 4B. Both paths read the identical rubric region — `app/critique/rubric.py` respects the `scorer:start`/`scorer:end` markers — so this is not the authorship-banner confound the harness was built to exclude.

**Consequences, in order of how much they cost:**

1. **Both calibration reports are artifacts.** The first reported five divergences, the second reported one, from the same rubric. Neither is a finding about a clause, and rewriting an anchor from either would be chasing noise. Any divergence smaller than the pipeline's own spread is unreadable, and right now that is most of them.
2. **The report's "the clause that decided it" column is a fiction.** `pipeline_verdict` derives it from `critique.points[0].clause` — the clause the *first point* happened to cite. Point order is not causation, and nothing in the schema records which anchor the model actually applied. So the loop of "divergence → this is the clause to rewrite" has been pointing at arbitrary clauses, which is worse than pointing at none.
3. **The 60/60 and 80/80 results do not transfer to the product.** They are properties of the scorer prompt, which asks for a score and the single deciding criterion and nothing else. They were read as properties of the rubric.

**The likely mechanism, and it is a design consequence rather than a bug.** The critique prompt tells the model the score is internal and instrumental and that *the advice is the product* — correctly, per §1 — and then asks for the score as one field among four, with no requirement to commit to an anchor or say why. Every other claim in this system has to name what it rests on: a point cites its clause, a not-assessable outcome must quote the words that earn it, and the scorer names its deciding criterion. **The outcome itself is the one judgment in the pipeline that is not anchored to anything**, and it is the one that moves.

**[SETTLED] The outcome carries its own anchor, like every other claim in the pipeline.**
Decided by Grant 2026-07-29. `DraftCritique` gains two required fields — `deciding_clause_id`, gated against the loaded rubric exactly as a point's clause is, and `determination`, the reasoning in a sentence or two. **Field order is load-bearing**: structured output is emitted in declaration order, so the determination is written before the score. A model that emits the number first and the reasoning after has decided nothing; it has guessed and then justified.

The prompt now says to decide the outcome and name what decided it before writing the critique, and the passage calling the score *internal and instrumental* was qualified — instrumental was being read as casual.

**Measured after, same five answers, five runs each:**

| Answer | Grant | Before | After |
|---|---|---|---|
| B | 4 | 4B×4, 2×1 | **4B×5** |
| E | 5 | 4B×3, 3×1, 2×1 | 5×3, 4B×2 |
| F | 5 | 4B×4, 5×1 | **4B×5** |
| I | 5 | 5×3, 4B×1, 4A×1 | **5×5** |
| K | 4 | 4B×5 | 4B×4, 5×1 |

**Three of five now stable where one was, and the worst spread drops from three anchors to two.** I is the clearest result: the paradigm 5 was landing on three different anchors and is now 5 five times out of five, matching the SME. E moved from never once reaching his score to reaching it in a majority of runs. K got marginally worse.

**Not fixed, improved.** E and K still move by one anchor, which is the same one-anchor boundary wobble Criterion 2 showed before its clause was tightened, and it is a rubric question rather than a pipeline one. The claim this change earns is narrower than "the scorer is stable": **a divergence of one anchor is still not readable, and a divergence of two or more now is.**

**The full calibration run after the change: ten of eleven agree, F the only divergence.** Worth stating what that is and is not evidence of. It is not "the anchors are right" — §7's standing caveat applies, and ten answers written by the same party that drafted the anchors cannot establish that. What it is evidence of is that **the exercise now produces the same answer twice**, which it demonstrably did not before: the two pre-change runs disagreed with each other on four answers, and F itself came back 5 in one and 4B in the other.

**What that bought: the first trustworthy finding the exercise has produced.** F is now 4B in all six post-change observations — five spread runs plus the full calibration run — against Grant's 5. He is the candidate who asks Ryan what is going on, gets a real answer about his mother coming out of hospital, and Ryan goes to the supervisor and fixes it himself.

The deciding clause is `c3.anchor.4B` in some runs and `c3.note.1` in others, and **that is not instability — the two are not in competition.** Note 1 is the gate he passes (he had the conversation) and 4B is where he lands afterwards. Both readings agree he asked once, got a real answer, and did not himself do anything further. The disagreement with Grant is about whether that reaches the top of the criterion: the anchors say the other person acting is what makes it a 4B, and Grant reads the asking as the thing that made it happen. That is a specific clause, a specific reading, and a specific disagreement worth putting in an anchor.

> **F rerun 2026-08-10, after the anchor edits** — `scripts/recruit_answer_runs.py F --runs 5
> --show`, `claude-sonnet-5` at effort `high`. Full write-up in
> `reviews/c3-f-rerun-2026-08-10.md`.
>
> | Requirement | Result |
> |---|---|
> | Preserve the 5 | **5×5, spread 0, σ 0.00** |
> | Name the persistence past the deflection | 2 of 5 critiques; 3 of 5 determinations |
> | Ryan's own action as the strongest evidence | `c3.anchor.5` leads all 5 |
> | Separate answer-specific from inventory | held once — only one gap in five runs |
> | One labelled reuse risk | **0 of 5** |
> | No rubric jargon | clean, zero gate rejections |
>
> **The score result is the one that matters and it is unambiguous.** F was 4B in all six
> post-outcome-anchor observations against Grant's 5; it is now 5 five times out of five with
> zero spread, and the determinations quote the new 4/5 boundary test rather than paraphrasing
> it. The divergence §10 had carried since 2026-07-29 is closed. The claim that earns is
> narrow: **the anchor now says what the SME says.** Nothing here speaks to answers F does not
> cover.
>
> **The reuse-risk class never fired, and the failure is larger than one requirement.** Four of
> five runs gave the candidate only credit — no ask, no caution, nothing to act on. Defensible
> on the score, wrong as coaching, for a man who is about to tell this story to another panel.
> The prompt described the class as optional and the model took the option.
>
> **A confound that will keep biting: the determination is not the critique.** The persistence
> reading is present in most determinations and absent from most critiques, and the internal
> field is the one that reads best. Any requirement about what the candidate sees has to be
> measured on `observation` and `ask` — reading the determination and calling it a pass is the
> same error as reading the scorer path and calling it the pipeline (see above).
>
> Three prompt edits followed and are unverified. Requirement 2 at 2 of 5 sits inside the range
> where five runs cannot separate a fix from noise; the next run needs more than five.

> **F re-run at n=20, 2026-08-10, after those three prompt edits.** Full write-up in
> `reviews/c3-f-rerun-2026-08-10-n20.md`.
>
> | Requirement | n=5 | n=20 |
> |---|---|---|
> | Preserve the 5 | 5×5, σ 0.00 | **20×5, σ 0.00** |
> | Name the persistence past the deflection | 2 of 5 | **18 of 20** |
> | Ryan's own action as the strongest evidence | leads 5 of 5 | **leads 19 of 20** |
> | Separate answer-specific from inventory | 1 gap | 1 gap in 20 |
> | One labelled reuse risk | 0 of 5 | **4 of 20, all four outside note 10** |
> | No rubric jargon | clean | clean |
>
> **Twenty-five consecutive observations at 5** across the two runs, against 4B six times out of
> six before the anchor edits. The F divergence is closed, and the determinations quote the new
> boundary test rather than paraphrasing it.
>
> **Requirement 2 is the clearest evidence a prompt edit did what it was written to do** — 2 of 5
> to 18 of 20 on the same rubric text, the only change being *name the move, not the category*.
> Worth recording as a counterweight to §7's standing caveat: prompt-level fixes to
> *what reaches the candidate* are measurable in a way rubric edits are not, because the target
> is a property of the output rather than a judgment about the fire service.
>
> **The reuse-risk class is now reachable and firing outside its own definition.** That is the
> finding, and it is a question about what a risk *is* rather than a tuning problem — see §10.
>
> **One methodological note that will recur: n=5 could not see any of this.** It reported
> requirement 2 as a partial failure that n=20 shows as a pass, and reported requirement 5 as a
> flat failure that n=20 shows as a boundary dispute. Both readings at n=5 were wrong in the
> direction of pessimism, and the earlier run said so at the time. **Five runs is for reading a
> critique; twenty is the floor for a claim about a rate.**

> **Noise floor re-run 2026-08-10, after all four anchor edits** — `scripts/recruit_noise_floor.py c3`,
> scorer path, `claude-sonnet-5` at effort `high`.
>
> | Fixture | n | Distribution | Spread | σ |
> |---|---|---|---|---|
> | Qualified, self-focused | 20 | 2×20 | 0 | 0.00 |
> | No team history, undersold | 20 | not assessable ×20 | — | — |
> | No team history, nobody there | 10 | not assessable ×10 | — | — |
> | Between 2 and 3 | 20 | 3×20 | 0 | 0.00 |
> | Generic, correct, no incident | 10 | 4B×10 | 0 | 0.00 |
> | Changed by a named person | 10 | **5×10** | 0 | 0.00 |
>
> **Ninety runs, zero variance on every fixture** — the cleanest this has been, against a
> previous best of 80/80. Two of these had a wobble history: the undersold fixture split three
> ways in July before note 4 was settled, and the 2/3 boundary produced a stray 4A. Both are
> flat. **The four anchor edits introduced no scorer-path ambiguity on anything these six
> fixtures reach.**
>
> **Two edits are confirmed by name in the determinations.** The being-changed fixture's
> reasoning quotes the restored route back — *"clears the breadth clause on its own, reaching the
> top band"* — and the generic-correct fixture cites *"anchor 4's third route"*, the numbering
> added the same day. Both are being read as written.
>
> **What it does not touch.** No fixture tests the breadth requirement itself — the
> being-changed fixture tests the *exemption* from it. Nothing here speaks to the
> two-behaviours case, which is where E lives.
>
> **And it is fresh evidence for the path decision below rather than against it.** The
> being-changed fixture *is* review-set answer I, the same transcript. Same rubric, same model,
> same effort, same day:
>
> | Path | Answer I |
> |---|---|
> | Scorer (`recruit_noise_floor.py`) | **5×10, σ 0.00** |
> | Critique (`recruit_review_compare.py`) | 4B, 5, 5 across three set runs |
>
> One answer, two paths, two different stabilities — which is exactly the 2026-07-29 finding
> reproduced on a single transcript rather than inferred across five. **A clean scorer floor and
> a wobbling product are not in tension; they are the same result seen twice.** So 90/90 says the
> rubric is unambiguous to a reader asked only for a score, and says nothing about what ships.

> **Answer E re-measured 2026-08-10 on the amended clause** — `recruit_answer_runs.py E --runs 20`,
> the shipping path. **5×8 / 4B×11 / 4×1 → 5×19 / 4B×1. Top band 40% → 95%, σ 0.49 → 0.22.**
>
> **The only edit today that can be said to have worked in the strong sense** — measured before,
> measured after, same answer, same n, one variable. The other four passed blast-radius checks,
> which establishes that nothing else moved, not that the thing worked. Worth distinguishing,
> because four clean set runs read like four confirmations and are not.
>
> **The mechanism is confirmed, not just the number.** The 5 determination quotes the route
> number added six hours earlier — *"which is the route-2 breadth condition named directly in the
> anchor"* — and the previous run's dissent (*"a general rule about the crew rather than a tied
> occasion"*) does not appear once in twenty runs. **A rate that moves is evidence; a rate that
> moves and names the sentence that moved it is a different quality of evidence**, and it is
> available here only because the n=20 harness prints the determination behind each distinct
> outcome. That printout is now the most useful thing in the harness.
>
> **The surviving 4B is a new objection and a fair one.** It concedes route 2 exists and argues
> the material misses it: the disposition is *"a general restatement of the same kind of help"* —
> one behaviour told twice rather than two behaviours. The clause does not answer that. Filed for
> Grant rather than fixed; 1 of 20 is inside the harness's own unreadable band, and the fix would
> revise his blind 5. See `reviews/c3-e-rate-2026-08-10-amended.md`.

**[SETTLED] A set run reports values; a boundary answer has a rate. Do not read one as the other.**
Established by getting it wrong, twice, on 2026-08-10. Three consecutive set runs produced an orderly table that read as stability, and the third falsified the second: E crossed a band and D crossed a route with no edit to explain either. E has been measured at **5×3, 4B×2** since 2026-07-29 — a 60/40 answer, logged in §10 as a known wobble the whole time — so 5, 5, 4B across three runs is exactly what it should have produced.

**Comparing two single-draw tables multiplies the error rather than controlling for it.** The stability of nine answers across two runs was reported as a baseline and was worth nothing: the answers that were going to move were the two nobody had a rate for.

So the division of labour between the harnesses is not a preference:

- **`recruit_review_compare.py`** answers *where do the anchors and the SME disagree*, across the whole set, one draw each. It cannot tell a finding from a wobble and should never be asked to.
- **`recruit_answer_runs.py <REF> --runs 20`** answers *does this answer have a value or a rate*. Any single-run divergence gets a rate before it gets an edit.

A divergence on an answer with no measured rate is not yet a finding, and an anchor edit made on one is a coin flip with paperwork.

**And a five-run figure is not a rate either.** Recorded because the rule was broken the same afternoon it was written: E's fall in the third set run was explained away as pre-existing on the strength of §7's `5×3, 4B×2` from July. Three of five has a confidence interval running from roughly 15% to 95% — it cannot establish a baseline, and using it to exonerate an edit is the same error one level down. At n=20 E came back 40% top-band against July's 60%, with intervals that overlap: **no shift demonstrated in either direction, and July was too small to detect one against.** Where a rate matters, n=20 is the floor for the measurement *and* for anything it is compared with.

**[SETTLED] An anchor edit is re-run against the whole set, not against the answer that prompted it.**
Learned twice in one day, the same way both times. The morning's edit turned a narrow 4B/5 ruling into a general licence and drove answer F to 5 in twenty-five consecutive runs. The afternoon's correction claimed precedence over everything below it in the anchor and thereby closed *being changed by a named colleague* — a standing route to 5, four paragraphs down, weeks older than the clause and mentioned nowhere in the ruling — driving answer I to 4B against a blind 5.

**Neither looked wrong.** Both times the rubric read cleanly, the run was orderly, and the harm was invisible until an answer that nobody was thinking about moved. That is the whole argument for the set re-run: an anchor edit aimed at one answer is checked by the answers it was *not* aimed at, and a single-answer re-run cannot see its own blast radius however many times it is repeated.

Two practical consequences, both cheap:

- **A clause that claims precedence has to be read against every route it now outranks.** *"Where this clause and anything below it disagree, this clause governs"* is a strong sentence, and the second failure was entirely contained in not re-reading what sat below it.
- **Pin a restored route with a test in both passages.** A route named in one place and constrained in another is a route that can be closed again by an edit to either, and the failure mode is a clean run.

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

**Answer F is a 5.** (Held 2026-08-06 to 2026-08-10.)
**Reversed by Grant 2026-08-10: F is a strong 4, and a 5 should need more than one incident.** The `reviews/c3-f-pipeline-comparison-2026-08-06.md` review recorded *"the pipeline assigned the correct score of 5"* and made *"preserve the score of 5"* requirement 1 of its own acceptance test. That requirement is withdrawn.

**What survives the reversal, and it is most of the reasoning.** The 2026-08-06 rulings about the *sequence* still stand: the disclosure is the evidence that the candidate got past a withheld answer, the colleague acting on it himself is evidence the conversation worked rather than a cap, and *"he's the one who sorted it — I just asked the question"* is precise crediting rather than an admission of passivity. None of that was wrong. **What was wrong was the band it landed in** — the sequence being handled well is a 4, and the top of the criterion needs volume the answer does not have.

**What this reveals about the anchor edit.** The 2026-08-10 edit to anchor 5 turned a narrow ruling about the 4B/5 boundary into a general licence — *"the other man solving it himself is the strongest fact in an answer, not a cap on it"* removed the only thing holding F below the top band and left the anchor with **no headroom requirement at all**. A candidate with a genuinely exceptional crew history now has nowhere above F to land. That is the defect to fix, and it is a defect introduced by the fix to the previous one.

**And it inverts the n=20 result.** Twenty-five consecutive 5s were read as the anchor agreeing with the SME. They are now the anchor being **stably wrong** — the tightening worked exactly as designed and drove the criterion to the wrong band with zero variance. Recorded because it is the cleanest example in this project of the standing §7 caveat: a measurement of consistency says nothing about correctness, and a clean run is not approval.

**Answer E is a 5.** (Blind, 2026-07-29. Held through two n=20 measurements.)
**Reversed by Grant 2026-08-10 as a consequence of a clause ruling, not a re-read:** *"a disposition that just restates the incident isn't a second behaviour."* E's incident is teaching a slower colleague; E's disposition is that helping slower colleagues is what you do. One behaviour at two altitudes, so E is a 4 on anchor 4's third route.

**Recorded separately from F's reversal because it is a weaker record.** F moved because he looked at F. E moved because a general ruling, given with E in view, turns out to be decisive when applied to it — and nothing in the machinery distinguishes the two once the revision is in the block. Stated in `reviews/c3-scoring-exercise.md` and announced by every comparison run, which is the most the tooling can do about it.

**The second reversal in five days, both in the same direction: an answer scored 5 blind, later read as a 4.** Worth naming as a pattern rather than two incidents. **The blind exercise is the only external signal this rubric has**, and two of its eleven data points have now moved — both downward, both after the anchors were tightened, both toward the tightening. That is the shape the standing §10 item about **distribution** predicts: with no target for what share of candidates reach each band, the top band is calibrated one answer at a time, and each correction is free to overshoot in the direction of the last one. Nothing here shows that E and F are wrongly revised. It shows there is no check that would catch it if they were.

---

## 10. Open items

**Audited 2026-08-17.** The table below had grown to fifty-five rows, of which thirty-one
read as live. Five of those were resolved and never struck — one of them re-run and
confirmed twice while still carrying the words *"Not re-run"*, and one describing a wobble
on an answer that has not moved in five consecutive set runs. A list that reports settled
work as outstanding gets the SME re-deciding things he has already decided, which is the
failure this file exists to prevent. They are struck below with the evidence.

What survives, and what it costs:

| | Count | Who |
|---|---|---|
| Decisions only Grant can make | 4, plus the route-tag question below (C1/C4/C5 naming and full-board session shape settled 2026-09-10; remaining four are C3 judgment calls still in the table) | Grant |
| Reading (not deciding) — the C3 rewrite he has not read | 1 | Grant |
| Authoring — C1/C4/C5 adjacent-band rewrites (structure drafts landed PR 46; not publishable) | 3 | Grant |
| Measurement runs and fixture work | 5 | Claude, no SME needed |
| Code and gate work | 4 | Claude, no SME needed |
| Product decisions not yet on the critical path | 2 | Grant, later |

**The route-tag rows are one decision, not five.** *4A is a dead letter*, *the split has
nowhere to put a competent single-incident answer*, *anchor 4 gained a third route,
unrouted*, *the narrowed clause names a destination the pipeline does not take*, and the
standing *4A/4B split* entry are all evidence for a single question: **do route tags
survive at all?** They are kept separate below because each carries its own evidence, but
they close together or not at all — and if they go, they go from Criterion 2 as well.

**Priority follows §3, not the size of the evidence.** The score is internal and the
candidate never sees it, so an item is urgent in proportion to what it changes about *what
he is told*. By that test the most important open item in this table is **"what a reuse
risk is"** — it decides what a strong answer gets to act on, which is the half of the
product Grant restated on 2026-08-17. The route-tag question matters for whether critique
addresses the axis that is short, which is a critique question wearing a scoring question's
clothes. The distribution item, the deciding-clause instability, and the boundary-definition
items are all about a number nobody reads; they are real, and they are not what is holding
the module up.

| Item | Notes |
|---|---|
| Criterion 1 anchors | Scope settled (see below). Structure-approved draft landed via PR 46 (`recruit_rubric_c1_answer_construction.md`) — **NOT PUBLISHABLE** until Grant rewrites adjacent bands. |
| Criterion 1 naming | **Settled 2026-09-10: Answer Construction** (not Communication). Structure approved the same day: clean 1–5 construction (no 4A/4B); Delivery three-band Clear/Costly/Blocking; owns-a-miss on the 5; practice sessions = full board of five; whole-board scoring. Draft landed on main via PR 46 (`recruit_rubric_c1_answer_construction.md`) — **STRUCTURE APPROVED / NOT PUBLISHABLE** until Grant rewrites adjacent bands. |
| Criterion 3 | **Rewritten 2026-07-29 from Grant's blind scores** — `recruit_rubric_c3_teamwork.md`. No longer represents nobody's judgment: the anchors were rewritten from an SME's scores on answers he had not seen scored, and note 1 (will he say the difficult thing) came from him. Still wants a pass over the rewritten text itself, which he has not read. **Amended again 2026-08-06** with the F rulings and a new scoring note 10, and **again 2026-08-10** four times for the breadth correction. **Stable at 90/90 on the scorer path as of 2026-08-10** — with the three cautions below attached; that figure does not transfer to the product and is not approval. |
| ~~C3 — the noise floor is stale~~ | **Re-run 2026-08-10 after all four anchor edits: 90 runs, zero variance on all six fixtures** — `reviews/c3-noise-floor-2026-08-10.md`. Two edits confirmed by name in the determinations, including the restored being-changed route. **Three cautions travel with the figure and it should not be quoted bare.** It is not approval (twenty-five consecutive 5s on F were zero variance and the wrong band). No fixture tests the breadth requirement — the being-changed fixture tests the *exemption* from it — so nothing here speaks to the two-behaviours case where E lives. And it is a scorer-path number: the same transcript wobbles 4B/5/5 through the product. See §7. |
| ~~The whole review set needs re-running~~ | **Run 2026-08-10** — `reviews/c3-set-rerun-2026-08-10.md`. **Nine of eleven agree, zero divergences among the answers that scored.** F fell to 4 and E held at 5, both as predicted, and the other seven did not drift — which was the specific risk of raising the bar. Two answers produced no critique (see below), so I is unmeasured rather than falsified and is the one prediction still outstanding. |
| ~~C3 — the breadth clause closed a route to 5 that nothing in the ruling touched~~ | **Closed by the 2026-08-17 audit: it was fixed, re-run, and confirmed twice, while still carrying the words "Not re-run."** I returned to 5 on `c3.anchor.5` in the third set run and held at 5 through the fourth and fifth — `reviews/c3-set-rerun-2026-08-10-third.md` and `-fifth.md`. The confirmation was already recorded two rows below, under a second entry for the same defect; the discovery row was never updated to match it. **One defect, two rows, one of them struck and one not** — which is how a fixed thing keeps being reported as broken. Original entry follows. **Found by the second set re-run, `reviews/c3-set-rerun-2026-08-10-second.md`: I came back 4B against a blind 5.** The clause said *"more than one of the behaviours listed above"* and claimed precedence over everything below it — and *being changed by a named colleague* is not in that list; it sits four paragraphs down as its own standing route to 5, weeks older than the clause. So the clause demoted a route to nothing, silently, and the answer written to test that exact route is the one that fell. §7's warning arriving from the other side: *a boundary made stable by becoming unreachable is closed, not fixed.* **Fixed** — the route now clears the clause on its own, stated in both passages with a test on both, on the reasoning that a change he still carries is the conduct's second appearance. **Not re-run.** |
| **C3 — does being changed by a colleague need a second behaviour beside it?** | The judgment inside that fix, and Grant's to take. I restored the route rather than close it, because closing it revises his blind 5 on I — a score he has not been asked about. If he does want it closed, I is a 4 and the clause needs no change; if he confirms the restoration, the discriminator across all three ruled answers is **conduct that outlasts the episode** (F has none, E and I both do), which is worth stating as the principle rather than leaving as three worked cases. |
| ~~C3 — two answers produced no critique~~ | **Fixed and confirmed 2026-08-10.** H returned `not assessable` matching the SME on its retry, and no answer truncated at the raised `max_tokens`. Eleven of eleven scored on the second run. |
| ~~Zero drift across nine answers between two set runs~~ | **Withdrawn 2026-08-10 by the third set run, which falsified it immediately.** E moved across a band and D across a route, neither needing an edit to explain. Two draws from a distribution containing a known coin flip were read as stability. **The general form is the lesson: one run per answer measures a value, and a boundary answer has a rate.** Eleven single draws cannot separate a rubric finding from a wobble however orderly the table looks, and comparing two such tables multiplies the error rather than controlling for it. `recruit_review_compare.py` now says so in its own output and points at the n=20 harness. |
| ~~C3 — the breadth clause closed the being-changed route~~ | **Fixed and confirmed 2026-08-10 (third set run).** I returned to 5 citing `c3.anchor.5`. Prediction made before the run and confirmed by it. |
| **C3 — E's rate on the narrowed clause is the last measurement outstanding** | The fifth set run returned E at **4B** against 95% top band six hours earlier. **One draw, and worth more than a single draw usually is**: under the null — the ruling changing nothing — a 4B is a 1-in-20 event, so this is evidence the ruling moved something. **It is not evidence about the new rate.** 95% → lower is shown; 95% → 0% is not, and the difference between a stable 4B and a 60/40 answer matters, because the second is where E was before any of today's work. `recruit_answer_runs.py E --runs 20`, ~90 cents. |
| **C3 — the narrowed clause names a destination the pipeline does not take** | The restatement clause says a failing answer is *"a 4 on anchor 4's third route"*. E landed **4B**, whose text describes transactional relationships and nobody mattering beyond the task — not a man who spent his own time teaching a colleague to load a truck. Two non-exclusive causes, both pointing at the standing 4A/4B item rather than a new one: **the third route has no tag**, so an answer reaching it must still be reported as 4A/4B/bare-4 and falls into the default; and **the instruction is prose in anchor 5**, with nothing making a clause in one anchor bind routing in another. **Do not fix by writing another sentence** — that is the move that has misfired five times today. |
| **C3 — the deciding clause is less stable than the band it produces** | Six observations, and the two newest are *reversals of moves recorded one run earlier*: **D** went `c3.anchor.4B` → `c3.anchor.4`, back to runs 1-2; **A** went `c3.anchor.2` → `c3.note.1`, reversing run 4. It oscillates rather than drifts, which rules out a slow effect of the day's edits. **Now the most-reproduced unexplained behaviour in the criterion.** Earlier count follows. Four observations. **D** moved from an unrouted `4` to `4b`; **F**'s deciding clause went `c3.anchor.4B` → `c3.anchor.4` → back again; **A** moved `c3.note.1` → `c3.anchor.2` in the fourth set run, both reaching 2. The verdict holds and the clause behind it does not. **Invisible in the calibration report by construction** — it compares bands, and a bare `4` agrees with either route — so this only surfaces by reading determinations. Worth weighing against the July rebuild of the *"clause that decided it"* column, which was done precisely because the old version named arbitrary clauses: the column is honest now, and the thing it reports turns out to move. |
| ~~C3 — the route-numbering edit needs a whole-set check~~ | **Run 2026-08-10, clean** — `reviews/c3-set-rerun-2026-08-10-fourth.md`. Eleven of eleven agree, no band moved, first edit today to pass a blast-radius check on the first attempt. **It does not establish that the edit worked**: E returning 5 is one draw from a 40% answer, stated before the run rather than after. Needs `--runs 20` on the amended text. |
| **C3 — 4A is a dead letter** | **Sixth consecutive absence, 2026-08-10 fifth set run**: B, E, F and K on 4B, D on a bare 4. Four of five level-4 answers on one tag. **4A still assigned once ever** across five set runs, forty-five runs of E, twenty-five of F and the noise-floor work — the tag is not discriminating, it is absorbing. F's row now shows the split from the other side too: **verdict `4b`, deciding clause `c3.anchor.4`** — the clause that decided it is the level, and the tag attached afterwards has text that contradicts the answer. Earlier evidence follows. The standing doubt below, now with the kinder reading no longer available. In the third set run **every level-4 answer took 4B — B, D, E, F and K, five of five** — and across three full set runs, twenty-five runs of F, and the noise-floor work, **4A has been assigned once**, on a borderline 2/3 fixture where it was recorded as a misfire. §10 has held since July that the scorer *"applied it consistently (5/5 runs tagged 4B), which says the split is legible — not that it is right."* Five of five later: 4B is absorbing every answer at level 4 regardless of whether its text describes them, and it describes none of these five. |
| **The 4A/4B split has nowhere to put a competent, warm, single-incident answer** | Predicted when the third route went into anchor 4 without a tag, and **observed on 2026-08-10**: F came back **4b**, whose text reads *"the relationships in his stories are transactional, and nobody in them appears to matter to him beyond the task"* — which is not F at all. B and K also landed 4b and D came back an unrouted 4, so **three of four level-4 answers took the same tag**. That is what a split does when it has nowhere to put a case. The split is drawn on wanting-versus-able and this class of answer is neither; fresh evidence for the standing doubt below about whether routes should survive review. |
| **Distribution is unset, and it is the question behind the question** | The reversal came from *"there's no way 25 straight 5s would be given in real life"* — a claim about a **rate**, and the rubric has never had one. Nothing in it says what share of candidates should reach each band, so every anchor edit is calibrated one answer at a time with no check that the resulting distribution resembles a real panel's. Worth setting a target (a 5 is roughly one candidate in *N*) before the next anchor edit, or this loop repeats on the next answer that scores higher than it feels. |
| ~~Pipeline score instability~~ | **Largely fixed 2026-07-29** by anchoring the outcome in the schema — see §7. Three of five previously-unstable answers are now stable and the worst spread fell from three anchors to two. What remains is a one-anchor wobble on two answers, tracked below as a rubric question rather than a pipeline one. |
| ~~C3 — E's wobble has a nameable cause, and it is not the note 5 probe~~ | **Fixed and confirmed 2026-08-10 by re-measurement: 40% → 95% at the top band, σ 0.49 → 0.22** — `reviews/c3-e-rate-2026-08-10-amended.md`. The 5 determination names the mechanism (*"the route-2 breadth condition named directly in the anchor"*) and the old dissent does not appear in twenty runs. The original entry follows. |
| ~~C3 — is a disposition that generalises the incident a *second* behaviour?~~ | **Settled by Grant 2026-08-10: no.** *"A disposition that just restates the incident isn't a second behaviour."* Route 2 survives, narrowed to dispositions about conduct the incident did not show, with an operational test in the clause — remove the incident and ask whether the disposition still says anything new. **The 1-of-20 dissent was right**, which is the first time all day a minority run has been vindicated rather than corrected. **This reverses the blind 5 on E**, recorded in the revisions block as a derivation from the ruling rather than a re-read of the answer. **Re-run 2026-08-10, clean** — `reviews/c3-set-rerun-2026-08-10-fifth.md`. Eleven of eleven agree, **I held at 5** on the being-changed route, and E moved to 4B. |
| **C3 — the ruling was a clause, and E's revision is derived from it** | Every other entry in `scores-revised` came from Grant looking at the answer. E's comes from applying a general ruling to an answer he did not separately re-score, and `recruit_review_compare.py` weighs the two identically. The derivation is stated in the exercise file and announced at the top of every comparison run, so it cannot sit there quietly — but if the ruling was meant to leave E at 5 by some route not considered, that line is what to delete. |
| ~~C3 — route 2's example was the line the ruling excludes~~ | **Closed by the 2026-08-17 audit: the defect is fixed and says so in its own text** — *"Both are now addressed in the clause."* What is left is the general lesson, which is worth keeping and is not an open item: **a ruling that narrows a route must be checked against that route's own example, and against any prose elsewhere the example was drawn from.** Filed as open because the row carried both the fix and the lesson, and nothing distinguished them. Original entry follows. Caught while implementing, and worth recording as a class. Route 2's worked example *was* E's *"if someone was slow you'd just help them out…"* — so the clause would have taught the opposite of the ruling while carrying it, and the anchor's opening paragraph still names reciprocity-as-ordinary as top-band conduct, which is the argument the 5s were making. Both are now addressed in the clause. **The general form: a ruling that narrows a route must be checked against that route's own example, and against any prose elsewhere that the example was drawn from.** Nothing enforces this; the fifth instance today of a sentence interacting with one it does not sit next to. |
| **C3 — E has never once probed what it was written to probe** | **Fixture written 2026-08-17, not run** (no API key in the session that wrote it): answer **L** in `review_set.py` is E with its second behaviour — the lad and the truck — removed and nothing else changed, so the closing claim is the only thing left to decide on. Not scored blind by the SME, and deliberately not slotted into the generated exercise file, which regenerating would clobber; `recruit_review_compare.py` already reports an unscored ref rather than dropping it. **Run `recruit_answer_runs.py L --runs 20` to close this.** Original entry follows. Across **forty runs at n=20, twice**, no determination has decided on *"I've genuinely never had a problem with anyone."* The 5 sets it aside as *"a separate, still-open question about delivery risk"*; the 4B does not mention it. Noted after the first n=20 and now reproduced on the amended clause, which makes it a property of the fixture rather than of the rubric text. **This is not a null result about note 5** — the answer supplies two behaviours, so it is decided before the closing line is reached. Isolating the claim needs the same answer *without* a second behaviour, so the line is the only thing left to decide on. A fixture, not a clause. |
| ~~The original E entry~~ | **Measured 2026-08-10 at n=20: 5×8, 4B×11, 4×1 — 40% at the top band, σ 0.49.** `reviews/c3-e-rate-2026-08-10.md`. The determinations agree on the facts and split on one sentence: does *"that's how it works"* count as a second behaviour? The 5s counted it; the 4 rejected it as *"a general rule about the crew rather than a tied occasion"*. That is route 2 of the breadth clause being read out of the clause by the sentence above it — **the clause had already answered the question and was being read against itself.** Fixed by numbering the three routes and stating that two of them are deliberately untied. **Not re-run.** Note also that **none of the three determinations decided on the unfalsifiable claim**, so the answer filed since July as probing note 5 has been answering a different question — and that probe remains unmeasured. |
| ~~C3 — one-anchor wobble on E and K~~ | **Closed by the 2026-08-17 audit: neither half of it is true any more, and one half never was.** E's wobble was named, fixed and re-measured — 40% → 95% at the top band, σ 0.49 → 0.22 — and is recorded four rows above. **K has returned 4b in all five set runs and has never moved once**; the entry pairs it with E on the strength of a wobble nothing in `reviews/` shows it having. What remains at that boundary is E's rate on the *narrowed* clause, which is its own row below and is a measurement rather than an instability. Original entry follows. The residue after the outcome anchor: E moves 5/4B, K moves 4B/5, both at the 4B/5 boundary. Same shape as Criterion 2's 3/4B boundary before it was tightened, and that one turned out to be a nameable clause ambiguity rather than model noise. Worth the same treatment. A one-anchor divergence is still unreadable in the calibration report. **The 2026-08-06 edit states a test at exactly this boundary** — did anything he did alter what the other man could do — so E and K should be re-run with F rather than treated as untouched. |
| ~~**C3 — F is a real divergence at 4B vs 5**~~ | **Settled by Grant 2026-08-06: 5, and the reasoning is now in two anchors.** Note 1 gains the distinction the divergence was actually about — asking is the floor, finding out is what is measured, and staying in the conversation past the first deflection is the decisive move. Anchor 5 gains the ruling that the other man solving it himself is the strongest fact in the answer rather than a cap at 4B, and the 4/5 boundary now tests whether anything the candidate did altered what the other man could do. **Not yet re-run** — see below. |
| ~~C3 — anchor 5 has no headroom requirement~~ | **Written 2026-08-10** as the breadth clause: a 5 requires **more than one of the behaviours anchor 5 lists**, appearing in more than one place in the account. Grant chose breadth of conduct over a count of occasions, so one richly told episode carrying two behaviours can clear it and the same behaviour told three times cannot. The clause is marked as governing anything below it in the anchor, because the sentences it corrects are still there and still read persuasively. **Not re-run.** |
| ~~C3 — "one exchange does not supply two behaviours" is my call, not Grant's~~ | **Attribution corrected 2026-08-17: it came after Grant's input, not from Claude unaided.** The entry was wrong about its own provenance, which matters more than the clause does — an item filed as *"the SME has not ruled on this"* stays on the blocking list and gets re-raised in every review, and this one was raised as a blocker weeks after it had in fact been settled. **The general form is the lesson: a provenance claim in this file is load-bearing, because the whole point of the review chain is knowing whose judgment a line carries.** Original entry follows. *F arguably shows two of anchor 5's behaviours already — he raises the difficult thing and he credits precisely — so a bare "more than one behaviour" clause would have left F at 5 and implemented nothing. The clause excludes two halves of a single conversation, which is what makes F a 4.* |
| **C3 — anchor 4 gained a third route, unrouted** | F needs a home and neither 4A (*says the difficult thing imperfectly*) nor 4B (*handles people, relationships transactional*) describes it — asking after a man's mother and not escalating over his head is neither clumsy nor transactional. Anchor 4 now carries a middle route, **one piece of the conduct done well**, deliberately without a route tag. That is fresh evidence for the standing doubt below about whether the 4A/4B split should exist at all: the split is drawn on wanting-vs-able, and this class of answer is neither. |
| **What a reuse risk is — note 10's boundary is drawn too narrowly, or the model is out of bounds** | **The finding from the n=20 run, and it needs Grant.** The `risk` class now fires (4 of 20, up from 0 of 5) and **all four firings quote wording that is present in the answer**, which note 10 explicitly excludes — the note says a risk names something *absent*. Two flag F's opening back-reference (a fixture seam, see below); two flag the closing *"he's the one who sorted it — I just asked the question"* as risking a panel reading his role as smaller than it was. That second one **contradicts anchor 5**, which now says the same sentence is precise crediting and the conduct at the top of the criterion. Both readings are defensible — the anchor scores conduct, the risk is about how a room hears it on a retelling — so the question is whether note 10 should widen to cover *present wording that lands differently elsewhere*. Widening is the more useful product and puts the risk class in standing tension with the anchors on any line that is both strength and liability. **Not tuned. This is a definition, not a defect.** |
| ~~C3 — the reuse-risk class has never fired~~ | **Reachable as of 2026-08-10** — 4 of 20 after the prompt edit that says a strong answer is where the class earns its keep. What remains is the boundary question above, and the coaching shortfall below. |
| ~~C3 — a strong answer still usually gets nothing to act on~~ | **Fixed 2026-08-17 by making it a gate rather than a request** — `_verify_actionable` in `app/critique/verify.py`, and the settled decision in §3. A critique whose every point is `improvement: "none"` is now rejected and regenerated, so the count is 20 of 20 by construction instead of by prompt-tuning. **This was the most important row in the table and it was filed as one of thirty**, between two entries about which route tag a level-4 answer takes. Original entry follows. Counting risks and gaps together, **5 of 20 runs gave the candidate anything forward-looking**; fifteen are pure credit. Up from 1 of 5, still a critique that tells a man he is finished with a story he is about to retell to another panel. |
| ~~C3 — persistence reaches the determination, not the candidate~~ | **Fixed 2026-08-10.** 2 of 5 → **18 of 20** naming the disclosure as something he had to get past, 14 of those in the strong form. Run 9 produced the distinction unprompted: *"not that you asked, but that something real came out of it."* Two runs still give the category only; a residue, not worth another edit. |
| ~~C3 — a point contradicted its own determination~~ | **Did not recur across 20 runs** after the prompt rule was added. Held on the single gap that appeared, so this is absence of evidence rather than evidence of absence. |
| ~~F's opening is a fixture seam being read as candidate behaviour~~ | **Closed by the 2026-08-17 audit: it is a standing caveat, not a task.** The row says so itself — *"deliberately not fixed"*, because editing F changes an answer Grant scored blind and breaks comparability with every prior run. Nothing is going to happen to it, so it does not belong on a list of things to do; it belongs with the reading instructions for the review set, which is where it now is. Original entry follows. *"Same sort of thing happened with a lad called Ryan at the depot"* is the review set's connective tissue — F's probe records *"Pairs with C"* — and two runs correctly flagged it as leaning on a story a cold panel has not heard. Faithful to the text, worthless as calibration, and it means **two of four risk firings measure the harness rather than the pipeline**. **Deliberately not fixed:** editing F changes an answer Grant scored blind and breaks comparability with every prior run on this set. Standing caveat for any answer in the set that opens with a back-reference. |
| **Rubric content leaks into candidate prose where the jargon gate cannot see it** | **Attempted 2026-08-17 and abandoned, with numbers.** The row said the false-positive cost was high; it is higher than that. A lexical detector was built and measured against the real C3 scorer region (5,721 words, 1,021 distinct): flagging words that are **rare in the rubric and absent from the transcript** marks **545 of 1,021** — more than half the rubric's vocabulary — so any critique of ordinary length fires. Adding a baseline corpus (Criterion 2's rubric plus all eleven review answers) to exclude ordinary domain language made it **worse in both directions**: still 423 flagged, and it now excludes `rig` — the one true positive, the word from note 1's worked example — because `rig` is ordinary fire-service language that appears in the answers too. **The signal a lexical check has access to does not separate the two cases.** What distinguishes *"a rig short on excuses"* from sound critique prose is not word rarity, it is that the sentence references a scenario absent from the candidate's answer — a semantic property, and reading it needs a model in the loop rather than a regex. That is the shape any future attempt should take, and it needs the API key this repository does not have. Code and tests deleted rather than left in: a check with a 50% false-positive rate is worse than none, because it trains a reviewer to skip it. Original entry follows. The gate tests *vocabulary* — criterion names, anchor names, clause ids — and passed all 20 runs clean. It cannot see rubric **content**: run 17 ended a point with *"what separated Ryan's real problem from a rig short on excuses"*, a mangled reach for note 1's rig-going-out-short example and close to incoherent to a reader who has never seen the rubric. The harder failure of the two. A gate would have to diff prose against the rubric text, and the false-positive cost is high. Flagged, not fixed. |
| **C3 — requirement 4 is untested, not passed** | One inventory gap across five runs, so the answer-specific / beyond-this-answer separation was exercised exactly once — and that run is the one that broke requirement 2. A five-run pass here is not a result. |
| ~~C3 — the probe strings named the wrong scoring notes~~ | **Fixed 2026-08-10.** E's probe said `note.4` (*no team history*) while describing note 5 (*do not score the teammate*); H's said `note.3` (*specificity*) while describing note 4. The 2026-07-29 rewrite inserted two notes above the old note 3 and the hand-written strings in `review_set.py` did not move, so both were off by one from July until the E re-run printed one. **Small, and it prints where it matters**: `recruit_review_compare.py` shows *"written to probe"* beside every divergence as the record of what an answer is for, so six weeks of divergence reports aimed the reader at the wrong clause while looking authoritative. **The hand-maintained-list failure that `rubric.py` parses the catalogue to avoid, one layer up and unguarded.** `tests/test_review_set.py` now resolves every probe reference against the real catalogue — which catches a renumbering that runs off the end and **cannot catch a swap between two clauses that both exist**, which is what this was, so the E and H pairings are pinned by ref as well. §10 and the review files said *note 5* throughout and were right; the code disagreed with them. |
| ~~The inspection renderer is not a candidate preview~~ | **Fixed 2026-08-17.** `app/critique/render.py` now holds both views over a shared `sections()`, so the order — which carries the 2026-08-06 review finding — cannot fork between them. The candidate view renders `observation` / `ask` / `answer_quote` only: no clause ids, no anchor labels, no internal score, no determination, each pinned by a test. Inspection output is byte-identical. **It returns lines rather than printing**, so step 5's API renders from the same function the CLI previews, and what a reviewer sees is what a candidate gets. Original entry follows. `render_critique` prints each point's clause id and the rubric's own heading as its label — correct for an SME tool, and it means the rendered output shows a candidate things requirement 6 exists to keep from him. Any candidate-facing surface renders `observation` / `ask` / `answer_quote` only. Worth settling before step 4 builds one, because the inspection view reads like a finished artifact. |
| ~~C3 — the generic-correct answer moved 3 → 4B~~ | **Confirmed intended by Grant 2026-07-29.** A candidate who states the right approach plainly has answered the question and is short of evidence, which is a lesser fault than lacking the instinct. 10/10 on the fixture. |
| ~~Is the weak teamwork answer really all development?~~ | **Dissolved by Grant 2026-07-28.** It was the wrong question to put to the model. Ask the candidate: is there a better story, and if not, that is the thing to go and get. Development verdicts on that fixture went 74 to zero. |
| ~~c2.anchor.2 — mixed anchor~~ | **Withdrawn 2026-07-28.** Not a defect: the anchor is two true things about one answer, and the critique should report both. See §3. |
| C3 — where the unfalsifiable-claim flag lands | **Now scoring note 5** (the rewrite renumbered the notes). It flags *"I've always gotten along with everyone"* as a tell but no anchor says whether it pulls an answer to 2 or is just noise on a 3. Found by the harness, and the rewrite left the question open where it stood. **Narrowed 2026-08-06, not closed:** where the claim is *absent* and the risk is that he opens with one next time, that is note 10 and it does not touch the score. The case the harness found — where he actually said it — is still unanswered. |
| C3 — what counts as "an action" at the 4 boundary | A teammate answering *"things are fine"* when asked was read as a named other person taking an action, putting a borderline answer at 4A. The boundary says an action is required and does not say what one is. **Quieter after the rewrite** — the 2/3 fixture is back to 20/20 — but the rewrite demoted the cast-of-the-story test rather than defining an action, so the question is dodged rather than answered. |
| ~~C3 — a real but too-thin offer~~ | **Settled by Grant 2026-07-29**, now scoring note 4: a single dismissed clause names a setting and nothing else, so it returns not assessable and asks him about it. He is not declining to answer and his life is not empty, so neither a low score nor *not answered* is honest. 20/20 on the fixture that used to split three ways. |
| Not-assessable outcome on other criteria | **Drafted into Criterion 2 on 2026-08-17 as scoring note 7 — awaiting SME review, flagged in that rubric's provenance section rather than in its scorer region.** Substantively mechanical: the rule was settled on C3 and this restates it. **One judgment call inside it, and it is the thing to attack:** the note says insufficient-evidence should be *rarer* here than on Teamwork and that the default when in doubt is *not answered*, reasoning that Teamwork has a real population who genuinely worked alone while every candidate in front of a panel has some account of why he is there. That is inference from purpose, not experience. |
| ~~Not assessable vs. did not answer~~ | **Fixed 2026-07-28.** Three outcomes: scored, not assessable (a conclusion, must quote the words that establish it), not answered (no basis either way — ask him). See §2. |
| Criteria 4, 5 | **Named 2026-09-10: C4 Integrity & Ethics; C5 Judgment & Composure.** Structure approved the same day (both: designated+corroboration; clean 1–5). C4: never-refuse-any-order = low-band tell; escalate past peer talk for harm/theft/impairment/illegal; C3/C5 overlap as drafted. C5: composure = conduct/content only (no voice-quality); self-awareness mostly C5; ranking traps score reasoning not secret correct order. Drafts landed via PR 46 (`recruit_rubric_c4_integrity_ethics.md`, `recruit_rubric_c5_judgment_composure.md`) — **STRUCTURE APPROVED / NOT PUBLISHABLE** until Grant rewrites adjacent bands. |
| Metrics spec | Pause classification, band definitions, stall threshold. Definitions matter more than they look. |
| ~~Noise floor test~~ | **Run 2026-07-27** — see §7. Stable away from boundaries; ±1 anchor at the 3/4B boundary, 25% of runs. |
| ~~3/4B boundary anchor~~ | **Tightened 2026-07-28**, re-run clean at 60/60. The test is now *can he say what it changed* — the same test the 4B and 3 anchors already applied. |
| Partial-account fixture | **Written 2026-08-17 — `C2_PARTIAL_ACCOUNT` in `scripts/recruit_noise_floor.py`, n=20, not run** (no API key in the session that wrote it). A ride-along that was *"eye-opening"* and *"made it more real"*, with nothing he did differently afterwards — so the clause's test, can he say what it changed, is not cleanly unmet. Deliberately far from both worked examples, which is the point: the 60/60 clean re-run carried a caution that both its fixtures sat close to the examples the clause carries and one run cited an example by name, so part of that zero was pattern-matching rather than reading. |
| Behavior-stability check | The progress display rests on question-independent behaviors, whose run-to-run stability is assumed, not measured. Same harness, before step 8. |
| 4A/4B split | Came out of a single pass. Wants a second panelist before it is settled. The scorer applied it consistently (5/5 runs tagged 4B), which says the split is legible — not that it is right. |
| Question bank | Size and rotation policy undetermined; the novel-question design makes bank depth a hard requirement rather than a nice-to-have. |

**Criterion 1 scope, settled:**
Scored across the whole board rather than on a designated question, so anchors cannot reference a specific answer. Audio can see answer construction (did he answer what was asked, does the answer have a shape, are claims specific, does he stop when done, will he say what he got wrong) plus pace, fluency, and length. It cannot see presence, eye contact, nerves, or likeability. The unscoreable half is real, is scored by actual panels, and the product should say plainly that it has to be worked on with a person.

### Settles 2026-09-10 (Grant)

Naming and structure for Criteria 1, 4 and 5 — recorded so the open table above does not keep reporting them as unwritten:

- **C1 named Answer Construction** (not Communication). Structure: clean 1–5 construction (no 4A/4B); Delivery three-band Clear / Costly / Blocking; owns-a-miss on the 5; **practice sessions = full board of five**; whole-board scoring.
- **C4 named Integrity & Ethics.** Structure: designated+corroboration; clean 1–5; never-refuse-any-order = low-band tell; escalate past peer talk for harm / theft / impairment / illegal; C3/C5 overlap as drafted.
- **C5 named Judgment & Composure.** Structure: designated+corroboration; clean 1–5; composure = conduct/content only (no voice-quality); self-awareness mostly C5; ranking traps score reasoning, not a secret correct order.
- Draft files on main via PR 46: `recruit_rubric_c1_answer_construction.md`, `recruit_rubric_c4_integrity_ethics.md`, `recruit_rubric_c5_judgment_composure.md`. **STRUCTURE APPROVED / NOT PUBLISHABLE** until Grant rewrites adjacent bands. Do not invent measurement numbers; do not claim these anchors are SME-authored or publishable.
- C2 remains SME-approved. C3 still owes a text pass on rewritten anchors.
- Question bank growth and five-question board *build* remain held behind publishable rubrics (session shape settle exists; implementation not started).
