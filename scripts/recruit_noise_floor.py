"""Measure the scorer's run-to-run noise floor on a Recruit rubric.

`recruit_design_decisions.md` §7: run one answer through the scorer ~20 times and examine
the spread. If run-to-run variance exceeds plausible monthly improvement, a progress
display built on scores is noise, and can show a candidate regressing when he improved.

    python scripts/recruit_noise_floor.py            # every rubric
    python scripts/recruit_noise_floor.py c3         # one rubric

**This measures consistency, not correctness.** A rubric can be perfectly stable and still
be wrong about the fire service — zero variance says the anchors are unambiguous, never
that they are right. Only SME review says that. Do not read a clean run as approval.

**And it measures the scorer path, not the product.** The prompt below asks for a score and
the deciding criterion and nothing else. `critique_answer` — the path that ships — asks for
a whole critique against the same rubric region and is markedly less stable on the same
answers; §7 records 80/80 here beside a three-anchor spread there, and 2026-08-10 got both
readings from one transcript (`C3_CHANGED_BY_SOMEONE` is review-set answer I: 5×10 σ 0.00
here, 4B/5/5 through `recruit_review_compare.py`). So the question this script answers is
**whether the rubric text is ambiguous to a reader asked only to score** — a real question,
and not the same one as whether the product is stable. For that, use
`scripts/recruit_answer_runs.py <REF> --runs 20`.

Fixture design follows two rules learned the hard way:

1. **Boundaries, not exemplars.** A fixture parked at 1 or 5 measures the floor and the
   ceiling, not the scorer. The long runs go on answers that sit between two anchors.
2. **Do not test against the worked examples.** Where an anchor carries a worked example,
   a fixture resembling it measures whether the scorer can match an example to the case it
   was written from — easier than the real problem, and the resulting zero is partly an
   artifact. The Criterion 2 run of 2026-07-28 has this limitation and says so; the
   Criterion 3 fixtures were written to avoid it.

Only the region between the `scorer:start` and `scorer:end` markers of a rubric is shown
to the scorer. Authorship banners, provenance and grounding notes live outside it, so a
draft rubric is not scored differently for announcing that it is a draft.

The fixtures are synthetic. No real candidate is described.
"""

import statistics
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from anthropic import Anthropic
from pydantic import BaseModel, Field

from app.config import get_settings

MAX_TOKENS = 16_000
POOL_SIZE = 4

SCORER_START = "<!-- scorer:start"
SCORER_END = "<!-- scorer:end -->"

SYSTEM_TEMPLATE = """You are scoring one answer from a fire department entry-level oral
board against a single criterion of a structured rubric. Apply the rubric as written. You
are not forming your own view about fire service hiring — you are applying this rubric's
anchors and scoring notes to this answer.

The candidate answered aloud; what follows is a transcript, so expect the disfluencies of
speech rather than the shape of written prose. Do not penalise an answer for sounding
spoken.

Return the outcome the rubric directs — a score, or, where the rubric provides for it, a
determination that the criterion cannot be assessed from this answer. Include the route tag
where the rubric calls for one, and the single criterion or scoring note that most
determined the outcome.

--- RUBRIC: {name} ---

{rubric}
"""


class Scoring(BaseModel):
    assessable: bool = Field(
        description=(
            "False when the answer gives no basis to apply this criterion at all — the "
            "candidate's history does not contain the material the criterion asks about. "
            "This is not a low score; it is the absence of a measurement."
        )
    )
    score: int = Field(
        ge=0,
        le=5,
        description="The 1-5 anchor the answer lands on, or 0 when assessable is false.",
    )
    route: Literal["4A", "4B", "n/a"] = Field(
        description="Route tag. '4A' or '4B' only when the score is 4; otherwise 'n/a'."
    )
    deciding_criterion: str = Field(
        description=(
            "The one anchor or scoring note that most determined this outcome. One sentence."
        )
    )


# --- Criterion 2 fixtures ----------------------------------------------------------
#
# Answers to a designated motivation question: "Why do you want to be a firefighter with
# this department, and what have you done to prepare?"

C2_PAST_LIST_NO_ACCOUNT = """
Um, so I've wanted to do this since I was probably nineteen. I got my EMT-B two years ago,
uh, I went through the community college program, and then I finished a fire academy last
spring — the certificate program. I've done a couple of ride-alongs, one with the county
and one over in, uh, the next district. And I've been working construction in the meantime
just to, you know, stay working while I test.

I think what draws me to it is, it's not a desk job. Every day is different, you're helping
people on probably the worst day of their life. And the crew aspect of it — I liked that in
construction, being part of a crew that depends on each other, and this is that but it
actually matters. So, yeah. I've got the certs, I'm testing everywhere I can, and I'm just
trying to get on somewhere.
"""

# A step past the list he *can* account for, but pursuit aimed at qualifying rather than at
# becoming good at the work. This fixture exists to catch the failure mode of tightening the
# 3/4B boundary — a boundary that is stable because nothing can reach it is closed, not fixed.
C2_PAST_LIST_ACCOUNTED = """
So I got my EMT-B in 2023 and finished the academy — the certificate program — last year.
Uh, I also did the wildland pack test and got my red card, which isn't on the posting here,
I just figured more certs makes me more competitive.

I've done four ride-alongs, three with one department and one here. And honestly the first
one changed what I thought this job was. I went in picturing fires and, uh, we ran eleven
calls that shift and one was a fire. The rest was medical, a lift assist, a car alarm. I
came out of that and signed up for more EMT clinical hours, because I realised that's the
actual job and I'd been preparing for the wrong one.

So that's where I'm at. I've got the certs, I've got the red card, I test everywhere I can,
and I think I'm a stronger candidate than I was two years ago.
"""

# The case the 2026-07-28 tightening left behind, and the one §10 named as where the boundary
# would next be soft. He says *something* about what a step past the list changed — so the
# clause's test, "can he say what it changed", is not cleanly unmet — but the account is one
# clause thick and he never names anything he did differently afterwards.
#
# Deliberately far from both worked examples. The 60/60 clean re-run carried a caution that
# both its fixtures sat close to the two examples the clause carries, one run citing an
# example by name, so part of that zero was the scorer matching a worked example to roughly
# the case it was written from. This fixture is neither example's territory, which is the only
# way to learn whether the clause is unambiguous generally or only on the case that split it.
C2_PARTIAL_ACCOUNT = """
So I got my EMT-B a year and a half ago and I did the academy certificate program after
that. I've been driving a delivery route since, mostly to keep the money coming in while I
test.

I did a ride-along with the county back in the spring. It was good, it was — it was
eye-opening honestly. Definitely made it more real for me, seeing how they operate as a crew
and how much of it is the medical side. I'd tell anyone to do one.

And then I've just been testing wherever it comes up. I did this one in March, one in
January over the other side of the county. I'm on two eligibility lists at the minute. I
think I'd be good at it — I get on with people, I don't mind the hours, and I'm not
squeamish.
"""

C2_STALE = """
Yeah, so I took an EMT class, uh, that would have been back in 2021 I think. Maybe 2020.
I passed it. I was going to do the academy but then my hours got picked up at work and it
just, it kind of got away from me, you know how it is.

I still want to do it. I've always thought about the fire service, my uncle was a
volunteer. It's just been a matter of timing, honestly. Things have been busy. But I'm
here, I'm testing, so.
"""

C2_CONTINUOUS = """
So I got my EMT in 2022 and I've been running as a volunteer with a district about forty
minutes from my house since about six months after that. Uh, I re-certed last year and I
picked up my Firefighter I and II in between, and I'm about halfway through a paramedic
program right now — that one nobody asked me to do, it's not on any of the postings I've
applied to. I did it because on the volunteer side almost every call we ran was medical,
not fire, and I was the guy standing there able to do the basics and not much else.

What changed for me was, uh, a call about a year in. Elderly woman, difficulty breathing,
and her daughter was there and completely, you know, coming apart. And I realised the
medicine was maybe half of what that house needed. The medic who ran that call talked to
that daughter for probably four minutes and it changed the whole thing. That's the part I
didn't know I'd be doing, and it's the part I want to be good at.

So the paramedic program is that. I ride out with the volunteer district, I've done
ride-alongs with two career departments, and I test everywhere I can get to.
"""


# --- Criterion 3 fixtures ----------------------------------------------------------
#
# Answers to a designated teamwork question: "Tell us about a time you worked with someone
# who wasn't doing their share."
#
# The level 2 anchor lists its tells explicitly, so these were written to exhibit the
# *pattern* without reciting the list — the fixture has to be a plausible, sympathetic
# answer a real candidate would give, or it tests nothing.

# The target case: qualified, competent, and the only agent in his own story.
C3_SELF_FOCUSED = """
Yeah, so at my last job — I was a shift lead at a warehouse — I had a guy on my crew who
just wasn't keeping up. Consistently. And look, I'm not going to let the numbers slip
because one person's having a hard time, so what I did was I restructured how we ran the
floor. I took his section on top of mine for about six weeks and I just absorbed it. Came
in early, stayed late.

And honestly the numbers went up that quarter. My manager noticed. I ended up getting the
scheduling responsibility off the back of it, which at that site was, uh, that was a big
deal.

I think that's what I'd bring here. I'm a team player, I don't complain, and if something
needs doing I'll pick it up and carry it. Nobody's ever had to worry about whether I did my
part.
"""

# The hard case, and the point of the run: between 2 and 3. He *did* ask — which is not a
# level 2 tell — but the crew is undifferentiated and the situation resolves itself.
C3_BOUNDARY_2_3 = """
Um, so we had a situation on my crew where one of the guys was kind of checked out for a
while. And the way we handled it was, uh, we all sort of picked up a little extra where we
could. I definitely took on some of it.

I did talk to him at one point — just asked if everything was alright. He said things were
fine so I didn't push it. And it kind of sorted itself out after a few weeks, I think some
stuff at home settled down for him.

I don't know, I just think you've got to be willing to carry a bit extra sometimes. That's
what a crew is. I've always gotten along with everyone I've worked with.
"""

C3_GENERIC = """
So, teamwork's probably the biggest thing in this job, right? Uh, I've always worked in team
environments. Construction, and before that a couple years in a restaurant kitchen, and both
of those, you sink or swim together.

If somebody's not pulling their weight I think you've got to address it directly but
respectfully. You don't go straight to the supervisor, you talk to the person first. And
usually people respond to that. I've found most people want to do a good job, they just
sometimes need someone to say something.

We had good crews at both places. Everybody pulled their weight, we got along, we got the
work done.
"""

C3_CHANGED_BY_SOMEONE = """
Uh, yeah. When I was volunteering there was an engineer named Dave who I did not get along
with at first. He was blunt with me in a way I took personally for about the first two
months. I thought he had a problem with me.

And then we had a call — car into a pole — and I was slow getting the stabilisation struts
because I was second-guessing myself. Afterwards he pulled me aside and said, you know,
"I'm hard on you because you hesitate, and hesitating is going to get somebody hurt." Which
was not fun to hear. But he was right.

What I do differently now is I say out loud what I'm about to do before I do it. Dave does
that — I picked it up off him. Sounds small, but it stopped the second-guessing, because
once you've said it you're committed. And he and I are good now. He wrote one of my
references.
"""


# No paid team history, but he volunteers material and dismisses it ("if that counts", "but
# that's not a job"). Scoring note 3 says that is the tell to look for — the material is
# unmentioned rather than absent. The interesting question is whether the scorer finds it.
C3_NO_TEAM_UNDERSOLD = """
Uh, honestly? I don't have a great example for that. I've mostly worked by myself. I did
five years driving long-haul, which is, you're alone in the truck. Before that I was doing
overnight stocking at a grocery warehouse and there were other people there but we weren't
really, we didn't work together — you just had your aisle.

I've got two younger brothers I helped raise after my mom got sick, if that counts. But
that's not a job.

I know that's probably not what you're looking for. I'm not trying to dodge the question, I
just don't want to make something up. I think I'd be alright on a crew, I get on with people
fine, but I can't point to a time it was actually tested the way you're asking.
"""

# Genuinely nobody there, and nothing offered. This is the case the not-assessable outcome
# exists for — the failure mode being that he falls to a 2 for a history he cannot help.
C3_NO_TEAM_EMPTY = """
Um. I mean, I haven't really had that come up. I've been self-employed since I was
twenty-one — small engine repair, out of my own shop, so it's just me. Customer brings the
thing in, I fix it, they pick it up.

I don't have anybody I've had a conflict with at work because I don't really have anybody at
work. I'm not sure what to tell you there.
"""


RUBRICS = {
    "c2": {
        "name": "Criterion 2 — Motivation & Preparation",
        "path": Path("recruit_rubric_c2_motivation.md"),
        "fixtures": [
            ("Past the list, cannot account for it", C2_PAST_LIST_NO_ACCOUNT, 20),
            ("Past the list, can account for it", C2_PAST_LIST_ACCOUNTED, 20),
            # Between the two above, and near neither worked example. Where the boundary is
            # expected to be soft; unrun as of 2026-08-17.
            ("Past the list, accounted for thinly", C2_PARTIAL_ACCOUNT, 20),
            ("Stale preparation", C2_STALE, 10),
            ("Continuous, other-focused", C2_CONTINUOUS, 10),
        ],
    },
    "c3": {
        "name": "Criterion 3 — Teamwork & Interpersonal",
        "path": Path("recruit_rubric_c3_teamwork.md"),
        "fixtures": [
            ("Qualified, self-focused (the target anchor)", C3_SELF_FOCUSED, 20),
            ("No team history, material undersold", C3_NO_TEAM_UNDERSOLD, 20),
            ("No team history, genuinely nobody there", C3_NO_TEAM_EMPTY, 10),
            ("Between 2 and 3 (asked, but crew undifferentiated)", C3_BOUNDARY_2_3, 20),
            ("Generic, correct, no incident", C3_GENERIC, 10),
            ("Changed by a named person", C3_CHANGED_BY_SOMEONE, 10),
        ],
    },
}


def scorer_region(path: Path) -> str:
    """The part of a rubric the scorer sees.

    Bounded by markers so that a draft rubric's authorship banner and its grounded/invented
    annotations stay out of the prompt. Without this, a rubric would be scored differently
    for admitting it is a draft, and the measurement would be of the banner.
    """
    text = path.read_text()
    if SCORER_START not in text or SCORER_END not in text:
        raise SystemExit(f"{path} is missing its scorer:start / scorer:end markers")
    body = text.split(SCORER_START, 1)[1].split(SCORER_END, 1)[0]
    # Drop the remainder of the marker's own comment line.
    return body.split("-->", 1)[1].strip()


def score_once(
    client: Anthropic, model: str, effort: str, system: str, answer: str, tries: int = 2
):
    """One scoring pass. Returns None if every attempt failed — a dropped run is not a zero.

    A small share of calls (~3-5%) come back with generation garbage appended to the
    free-text field, and occasionally with unparseable JSON. It is not truncation: output
    runs ~280 tokens against a 16k cap and stops on `end_turn`. Scores themselves parse
    correctly, so the distributions are unaffected; the retry exists so a hard failure does
    not quietly shrink n and make a run look cleaner than it was.
    """
    for attempt in range(tries):
        try:
            response = client.messages.parse(
                model=model,
                max_tokens=MAX_TOKENS,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": f"Candidate's answer:\n\n{answer.strip()}"}],
                thinking={"type": "adaptive"},
                output_config={"effort": effort},
                output_format=Scoring,
            )
        except Exception as exc:  # noqa: BLE001 - a measurement; surface it and keep going
            if attempt == tries - 1:
                print(f"    call failed after {tries} attempts: {type(exc).__name__}")
                return None
            continue
        return response.parsed_output
    return None


def run(label: str, answer: str, n: int, client: Anthropic, model: str, effort: str, system: str):
    print(f"\n--- {label} — {n} runs")

    # One warm-up first, so the rest read the cached rubric rather than all missing at once.
    results = [score_once(client, model, effort, system, answer)]
    with ThreadPoolExecutor(max_workers=POOL_SIZE) as pool:
        results += list(
            pool.map(lambda _: score_once(client, model, effort, system, answer), range(n - 1))
        )

    returned = [r for r in results if r is not None]
    if not returned:
        print("  every call failed")
        return

    # Not-assessable is a distinct outcome, never a zero. Averaging it in would reintroduce
    # exactly the error the outcome exists to prevent.
    scored = [r for r in returned if r.assessable and r.score > 0]
    unassessable = len(returned) - len(scored)

    print(f"  n            : {len(returned)} of {n}")
    if unassessable:
        share = unassessable / len(returned)
        print(f"  NOT ASSESSABLE: {unassessable}/{len(returned)} = {share:.0%}")
    if not scored:
        print("  no run returned a score")
        return

    scores = [r.score for r in scored]
    dist = Counter(scores)
    modal, modal_n = dist.most_common(1)[0]

    print(f"  distribution : {dict(sorted(dist.items()))} (of the {len(scores)} scored)")
    print(f"  range        : {min(scores)} - {max(scores)}  (spread {max(scores) - min(scores)})")
    print(f"  mean         : {statistics.mean(scores):.2f}")
    if len(scores) > 1:
        print(f"  stdev        : {statistics.pstdev(scores):.2f}")
    print(f"  modal score  : {modal} ({modal_n}/{len(scores)} = {modal_n / len(scores):.0%})")

    routes = Counter(r.route for r in scored if r.score == 4)
    if routes:
        print(f"  route tags at 4: {dict(routes)}")

    seen = set()
    print("  deciding criterion, first sighting of each distinct outcome:")
    for r in returned:
        key = "n/a" if not r.assessable or r.score == 0 else r.score
        if key in seen:
            continue
        seen.add(key)
        route = r.route if r.route != "n/a" else ""
        tag = "NOT ASSESSABLE" if key == "n/a" else f"{r.score}{route}"
        print(f"    [{tag}] {r.deciding_criterion.strip()}")


def main() -> None:
    wanted = [a.lower() for a in sys.argv[1:]] or list(RUBRICS)
    unknown = [w for w in wanted if w not in RUBRICS]
    if unknown:
        raise SystemExit(f"unknown rubric(s) {unknown}; choose from {list(RUBRICS)}")

    settings = get_settings()
    if not settings.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set — check .env")

    client = Anthropic(api_key=settings.anthropic_api_key)
    model, effort = settings.generation_model, settings.generation_effort
    print(f"scorer: {model}, effort={effort}, adaptive thinking")
    print("this measures consistency, not correctness — a stable rubric can still be wrong")

    for key in wanted:
        spec = RUBRICS[key]
        if not spec["path"].exists():
            raise SystemExit(f"{spec['path']} not found — run this from the repository root")
        system = SYSTEM_TEMPLATE.format(name=spec["name"], rubric=scorer_region(spec["path"]))
        print(f"\n{'=' * 78}\n{spec['name']}\n{'=' * 78}")
        for label, answer, n in spec["fixtures"]:
            run(label, answer, n, client, model, effort, system)


if __name__ == "__main__":
    main()
