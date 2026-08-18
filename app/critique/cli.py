"""Command-line critique: answer + rubric -> criterion-referenced critique.

CLI-first by design, for the same reason Promote's ingestion was: the pipeline is
exercisable against real answers before any UI, database, queue or audio capture exists.
That is what makes it possible to look at what the critique step actually produces rather
than at what its tests assert — which is the whole point of build-order step 3, where a
fire captain reads real critiques and decides whether they are good enough to ship.

    badgeday-critique --rubric c3 --fixture self_focused
    badgeday-critique --rubric c2 --answer path/to/transcript.txt
    badgeday-critique --rubric c3 --all-fixtures

The four fixtures build order step 2 asks for — a strong answer, a weak one, an off-topic
one and an empty one — are built in, so the gate can be exercised end to end without
anyone having to write an answer first.
"""

import argparse
import logging
import sys
from pathlib import Path

from anthropic import Anthropic

from app.config import get_settings
from app.critique import rubric as rubric_module
from app.critique.critiquer import critique_answer

# Re-exported: the run harnesses and the render tests import it from here, and the split
# into render.py is about where a candidate-facing view lives, not about moving the
# inspection one out from under its callers.
from app.critique.render import render_critique, render_for_candidate  # noqa: F401

QUESTIONS = {
    "c2": (
        "Why do you want to be a firefighter with this department, and what have you "
        "done to prepare?"
    ),
    "c3": "Tell us about a time you worked with someone who wasn't doing their share.",
}

# Fixtures are synthetic. No real candidate is described.
FIXTURES: dict[str, dict[str, str]] = {
    "c2": {
        "strong": """
So I got my EMT in 2022 and I've been running as a volunteer with a district about forty
minutes from my house since about six months after that. I re-certed last year and picked
up my Firefighter I and II in between, and I'm about halfway through a paramedic program
right now — that one nobody asked me to do, it's not on any of the postings I've applied
to. I did it because on the volunteer side almost every call we ran was medical, not fire,
and I was the guy standing there able to do the basics and not much else.

What changed for me was a call about a year in. Elderly woman, difficulty breathing, and
her daughter was there and completely coming apart. I realised the medicine was maybe half
of what that house needed. The medic who ran that call talked to that daughter for probably
four minutes and it changed the whole thing. That's the part I didn't know I'd be doing,
and it's the part I want to be good at.
""",
        "weak": """
Yeah, so I took an EMT class, uh, that would have been back in 2021 I think. Maybe 2020. I
passed it. I was going to do the academy but then my hours got picked up at work and it
just, it kind of got away from me, you know how it is.

I still want to do it. I've always thought about the fire service, my uncle was a
volunteer. It's just been a matter of timing, honestly. Things have been busy. But I'm
here, I'm testing, so.
""",
        "off_topic": """
Yeah so the thing about this city is the response times are all over the place depending
which side of the river you're on. I looked it up. The east side stations are running,
what, six, seven minutes on a lot of calls and that's, that's a staffing question really,
it's a budget question.

I think if you brought back the station on Fourteenth you'd fix half of it. That's what
I'd do. I've got a lot of thoughts about how the department's run, honestly.
""",
        "empty": "Uh. Sorry, can you repeat the question?",
    },
    "c3": {
        "strong": """
When I was volunteering there was an engineer named Dave who I did not get along with at
first. He was blunt with me in a way I took personally for about the first two months. I
thought he had a problem with me.

And then we had a call — car into a pole — and I was slow getting the stabilisation struts
because I was second-guessing myself. Afterwards he pulled me aside and said, "I'm hard on
you because you hesitate, and hesitating is going to get somebody hurt." Which was not fun
to hear. But he was right.

What I do differently now is I say out loud what I'm about to do before I do it. Dave does
that — I picked it up off him. It stopped the second-guessing, because once you've said it
you're committed. He and I are good now. He wrote one of my references.
""",
        "weak": """
Yeah, so at my last job — I was a shift lead at a warehouse — I had a guy on my crew who
just wasn't keeping up. Consistently. And look, I'm not going to let the numbers slip
because one person's having a hard time, so what I did was I restructured how we ran the
floor. I took his section on top of mine for about six weeks and I just absorbed it. Came
in early, stayed late.

And honestly the numbers went up that quarter. My manager noticed. I ended up getting the
scheduling responsibility off the back of it, which at that site was a big deal.

I think that's what I'd bring here. I'm a team player, I don't complain, and if something
needs doing I'll pick it up and carry it.
""",
        "off_topic": """
Honestly the biggest thing for me is fitness. I'm in the gym six days a week, I've got my
deadlift up to four hundred, and I think that matters more than people say for this job
because you're carrying somebody down a stairwell, you're not negotiating with them.

A lot of guys wash out of the academy because they can't hold up physically. That's the
part I've made sure I'm ready for.
""",
        "empty": "I don't really have anything for that one.",
        # The case not-assessable exists for: he explains a genuinely solitary working
        # life. The distinction from "empty" is the whole point — one establishes an
        # absence, the other establishes nothing.
        "no_history": """
Um. I mean, I haven't really had that come up. I've been self-employed since I was
twenty-one — small engine repair, out of my own shop, so it's just me. Customer brings the
thing in, I fix it, they pick it up.

I don't have anybody I've had a conflict with at work because I don't really have anybody
at work. I'm not sure what to tell you there.
""",
    },
}


def _run_one(label: str, transcript: str, rubric, client, settings, draft: bool) -> bool:
    print(f"\n{'-' * 78}\nfixture: {label}")
    outcome = critique_answer(
        rubric=rubric,
        question=QUESTIONS[rubric.criterion_id],
        transcript=transcript,
        client=client,
        settings=settings,
    )

    for rejection in outcome.rejections:
        print(f"  rejected [{rejection.code}] {rejection.detail}")

    if outcome.failure:
        print(f"  FAILED: {outcome.failure}")
    if outcome.critique is not None and outcome.critique.points:
        render_critique(outcome.critique, draft)

    print(f"\n  ({outcome.attempts} attempt(s), {len(outcome.rejections)} point(s) rejected)")
    return not outcome.failed


def main() -> int:
    parser = argparse.ArgumentParser(description="Critique an oral board answer against a rubric.")
    parser.add_argument("--rubric", default="c3", choices=rubric_module.available())
    parser.add_argument("--answer", type=Path, help="File containing a transcript.")
    parser.add_argument("--fixture", choices=sorted(FIXTURES["c3"]), help="Use a built-in answer.")
    parser.add_argument("--all-fixtures", action="store_true", help="Run every built-in answer.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )

    settings = get_settings()
    if not settings.anthropic_api_key:
        print("ANTHROPIC_API_KEY is not set — check .env", file=sys.stderr)
        return 2

    try:
        rubric = rubric_module.load(args.rubric)
    except (KeyError, ValueError, OSError) as exc:
        print(f"could not load rubric: {exc}", file=sys.stderr)
        return 2

    is_draft = args.rubric in rubric_module.DRAFT_RUBRICS
    client = Anthropic(api_key=settings.anthropic_api_key)

    if args.answer:
        jobs = [(args.answer.name, args.answer.read_text())]
    elif args.all_fixtures:
        jobs = list(FIXTURES[args.rubric].items())
    elif args.fixture:
        jobs = [(args.fixture, FIXTURES[args.rubric][args.fixture])]
    else:
        parser.error("choose --answer, --fixture or --all-fixtures")

    print(f"rubric: {rubric.name}  ({len(rubric.clauses)} citable clauses)")
    print(f"scorer: {settings.generation_model}, effort={settings.generation_effort}")

    ok = [_run_one(label, text, rubric, client, settings, is_draft) for label, text in jobs]
    print(f"\n{'=' * 78}\n{sum(ok)}/{len(ok)} produced a verified critique")
    return 0 if all(ok) else 1


if __name__ == "__main__":
    raise SystemExit(main())
