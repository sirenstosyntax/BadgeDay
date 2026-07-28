"""Measure the scorer's run-to-run noise floor on a Recruit rubric.

`recruit_design_decisions.md` §7: run one answer through the scorer ~20 times and look at
the spread. If run-to-run variance exceeds plausible monthly improvement, a progress
display built on scores is noise, and can show a candidate regressing when he improved.

    python scripts/recruit_noise_floor.py

Three fixtures rather than one. The 20-run measurement is on a **boundary** answer,
because that is where a real candidate sits and where movement would be read; a fixture
parked at 1 or 5 measures the floor and the ceiling, not the scorer. The two smaller runs
on an unambiguous 2 and an unambiguous 5 exist to show whether any instability is specific
to the boundary or general — a distinction that changes what you do about it.

This is a measurement, not shipped code. There is no critique pipeline yet; the scoring
call here is the thinnest thing that produces a score from the rubric, and it is
deliberately not a draft of step 2. Re-run it whenever the rubric's anchors change — the
number it produces is a property of the rubric at least as much as of the model.

The fixtures are synthetic. No real candidate is described.
"""

import statistics
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Literal

from anthropic import Anthropic
from pydantic import BaseModel, Field

from app.config import get_settings

RUBRIC_PATH = Path("recruit_rubric_c2_motivation.md")

MAX_TOKENS = 16_000
POOL_SIZE = 4

SYSTEM_TEMPLATE = """You are scoring one answer from a fire department entry-level oral
board against a single criterion of an SME-authored rubric. Apply the rubric as written.
You are not forming your own view about fire service hiring — you are applying this
rubric's anchors and scoring notes to this answer.

The candidate answered aloud; what follows is a transcript, so expect the disfluencies of
speech rather than the shape of written prose. Do not penalise an answer for sounding
spoken.

Return the score, the route tag where the rubric calls for one, and the single criterion
or scoring note that most determined the score.

--- RUBRIC ---

{rubric}
"""


class Scoring(BaseModel):
    score: int = Field(ge=1, le=5, description="The 1-5 anchor the answer lands on.")
    route: Literal["4A", "4B", "n/a"] = Field(
        description="Route tag. '4A' or '4B' only when the score is 4; otherwise 'n/a'."
    )
    deciding_criterion: str = Field(
        description="The one anchor or scoring note that most determined this score. One sentence."
    )


# --- Fixtures ---------------------------------------------------------------------
#
# Answers to a designated motivation question: "Why do you want to be a firefighter with
# this department, and what have you done to prepare?"

BOUNDARY = """
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

CLEAR_TWO = """
Yeah, so I took an EMT class, uh, that would have been back in 2021 I think. Maybe 2020.
I passed it. I was going to do the academy but then my hours got picked up at work and it
just, it kind of got away from me, you know how it is.

I still want to do it. I've always thought about the fire service, my uncle was a
volunteer. It's just been a matter of timing, honestly. Things have been busy. But I'm
here, I'm testing, so.
"""

CLEAR_FIVE = """
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


def score_once(client: Anthropic, model: str, effort: str, system: str, answer: str):
    """One scoring pass. Returns None on failure — a dropped run is not a zero."""
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
        print(f"    call failed: {type(exc).__name__}: {exc}")
        return None
    return response.parsed_output


def run(label: str, answer: str, n: int, client: Anthropic, model: str, effort: str, system: str):
    print(f"\n=== {label} — {n} runs " + "=" * 30)

    # One warm-up first, so the rest read the cached rubric rather than all missing at once.
    results = [score_once(client, model, effort, system, answer)]
    with ThreadPoolExecutor(max_workers=POOL_SIZE) as pool:
        results += list(
            pool.map(lambda _: score_once(client, model, effort, system, answer), range(n - 1))
        )

    scored = [r for r in results if r is not None]
    if not scored:
        print("  every call failed")
        return

    scores = [r.score for r in scored]
    dist = Counter(scores)
    modal, modal_n = dist.most_common(1)[0]

    print(f"  n            : {len(scores)} of {n}")
    print(f"  distribution : {dict(sorted(dist.items()))}")
    print(f"  range        : {min(scores)} - {max(scores)}  (spread {max(scores) - min(scores)})")
    print(f"  mean         : {statistics.mean(scores):.2f}")
    if len(scores) > 1:
        print(f"  stdev        : {statistics.pstdev(scores):.2f}")
    print(f"  modal score  : {modal} ({modal_n}/{len(scores)} = {modal_n / len(scores):.0%})")

    routes = Counter(r.route for r in scored if r.score == 4)
    if routes:
        print(f"  route tags at 4: {dict(routes)}")

    print("  deciding criterion, one line each:")
    for r in scored:
        tag = f"{r.score}{r.route if r.route != 'n/a' else ''}"
        print(f"    [{tag}] {r.deciding_criterion.strip()[:110]}")


def main() -> None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set — check .env")
    if not RUBRIC_PATH.exists():
        raise SystemExit(f"{RUBRIC_PATH} not found — run this from the repository root")

    system = SYSTEM_TEMPLATE.format(rubric=RUBRIC_PATH.read_text())
    client = Anthropic(api_key=settings.anthropic_api_key)
    model, effort = settings.generation_model, settings.generation_effort
    print(f"scorer: {model}, effort={effort}, adaptive thinking, rubric = Criterion 2")

    run("BOUNDARY (3/4 territory)", BOUNDARY, 20, client, model, effort, system)
    run("CLEAR 2 (stale preparation)", CLEAR_TWO, 10, client, model, effort, system)
    run("CLEAR 5 (continuous, other-focused)", CLEAR_FIVE, 10, client, model, effort, system)


if __name__ == "__main__":
    main()
