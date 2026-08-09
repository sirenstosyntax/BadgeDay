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
from app.critique.models import Critique

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


def render_critique(critique: Critique, draft: bool) -> None:
    """Print a critique for inspection. Public because the run harnesses reuse it.

    A second renderer beside this one would drift, and the point of the harnesses is to
    look at what the pipeline actually produces — which is only true if they show what the
    CLI shows.
    """
    print(f"\n=== {critique.criterion_name} ===")
    if draft:
        print("    (DRAFT RUBRIC — anchors are unreviewed; critique shown for inspection only)")

    if critique.outcome == "not_assessable":
        print("\n  NOT ASSESSABLE — this answer establishes the material is not in his history.")
        print("  Not a low score. A finding, and one the points below have to support by")
        print("  quoting him.")
    elif critique.outcome == "not_answered":
        print("\n  NOT ANSWERED — nothing here to judge either way.")
        print("  Not a low score and not a finding about his life. He was silent on it,")
        print("  which is not the same as never having done it. The points below ask.")
    else:
        # The score is internal and deliberately not rendered. It is printed here behind a
        # label that says so, because this is an inspection tool for the SME rather than a
        # candidate-facing surface, and step 3 is a judgment about whether the score and
        # the critique agree.
        route = f" ({critique.route})" if critique.route != "n/a" else ""
        print(f"\n  [internal, never shown to a candidate: {critique.internal_score}{route}]")
        # The determination is the part worth reading at step 3. The number says the anchors
        # and the SME disagree; this says which clause did it and on what reading, which is
        # the difference between a divergence you can act on and one you can only count.
        if critique.deciding_clause:
            print(f"  [decided by {critique.deciding_clause.clause_id}: {critique.determination}]")

    def show(point) -> None:
        anchor = point.clause.clause_id if point.clause else f"metric:{point.metric.name}"
        print(f"\n  • [{anchor}] {point.anchor_label()}")
        if point.answer_quote:
            print(f'      you said: "{point.answer_quote}"')
        print(f"      {point.observation}")
        if point.ask:
            print(f"      → {point.ask}")

    # Three sections, because that is how feedback is read: what he did, then what to work
    # on, then what to watch when he reuses this. The routing distinction sits underneath
    # the middle one rather than beside the first — a man reading four headings, three of
    # them faults, has been handed a verdict. One clause can appear in more than one
    # section, and often should.
    if critique.worked:
        print("\n  WHAT YOU DID WELL")
        for point in critique.worked:
            show(point)

    # Answer-specific coaching first and broader inventory gaps after, with the heading
    # saying which is which. SME review 2026-08-06: an evidence-inventory gap was read as
    # the primary weakness of a strong answer, which it was not — it would have been just
    # as true of a better one. The order and the wording are what stop it being read that
    # way, since whatever comes first is taken as the verdict.
    work = [
        ("in this answer — it is here and handled badly", critique.answer_gaps),
        (
            "beyond this answer — your stock of examples, not what you just said. "
            "is there a better story? if not, that is the thing to go and get",
            critique.inventory_gaps,
        ),
        ("beyond this answer — you said you have not done this", critique.development_gaps),
    ]
    if any(points for _, points in work):
        print("\n  WHAT YOU COULD WORK ON")
        for note, points in work:
            if not points:
                continue
            print(f"\n    — {note}")
            for point in points:
                show(point)

    # Its own section, and last. A risk is a caution attached to material that worked; among
    # the gaps it reads as a fault, which is the one thing scoring note 10 says it is not.
    if critique.risks:
        print("\n  IF YOU USE THIS STORY AGAIN")
        print("    Nothing below is wrong with the answer you gave. It is what would cost")
        print("    you the next time you tell it.")
        for point in critique.risks:
            show(point)


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
