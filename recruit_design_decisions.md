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

---

## 3. Critique generation constraints

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
| Criteria 3, 4, 5 | Unwritten. Teamwork first, and within it the qualified-braggart anchor first. |
| Metrics spec | Pause classification, band definitions, stall threshold. Definitions matter more than they look. |
| ~~Noise floor test~~ | **Run 2026-07-27** — see §7. Stable away from boundaries; ±1 anchor at the 3/4B boundary, 25% of runs. |
| **3/4B boundary anchor** | The one thing the noise-floor run turned up. *"Something to show for it"* is doing all the work and is untested — decide whether an unelaborated ride-along clears it. Then re-run the measurement. |
| Behavior-stability check | The progress display rests on question-independent behaviors, whose run-to-run stability is assumed, not measured. Same harness, before step 8. |
| 4A/4B split | Came out of a single pass. Wants a second panelist before it is settled. The scorer applied it consistently (5/5 runs tagged 4B), which says the split is legible — not that it is right. |
| Question bank | Size and rotation policy undetermined; the novel-question design makes bank depth a hard requirement rather than a nice-to-have. |

**Criterion 1 scope, settled:**
Scored across the whole board rather than on a designated question, so anchors cannot reference a specific answer. Audio can see answer construction (did he answer what was asked, does the answer have a shape, are claims specific, does he stop when done, will he say what he got wrong) plus pace, fluency, and length. It cannot see presence, eye contact, nerves, or likeability. The unscoreable half is real, is scored by actual panels, and the product should say plainly that it has to be worked on with a person.
