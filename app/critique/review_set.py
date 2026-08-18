"""The answers used to review a rubric against the SME's own judgment.

`recruit_design_decisions.md`: no Recruit item publishes without SME review, and the
anchors — the discrimination between adjacent scores — are the part no public source
supplies and no measurement can settle. The classification and noise-floor harnesses can
show that the pipeline is *consistent*. Only a fire captain can say it is *right*.

This is the instrument for asking him, and it is built to cost him as little time as
possible. He scores these answers from his own judgment with no rubric in front of him;
the pipeline scores the same answers from the anchors; the divergences are the anchors to
rewrite. Agreement needs no further attention, which is what makes it cheap — the review
converges on the handful of clauses that are actually wrong rather than marching through
all fifteen.

**`probes` is not shown to him before he scores.** Telling a reviewer that an answer was
written to test the level 4 boundary tells him where to land, and the whole value of the
exercise is that his judgment arrives independently. It is recorded here because the
comparison needs it afterwards, and because a fixture whose purpose nobody wrote down
stops being a test of anything within a month.

**The clause references in `probes` are hand-written, and they went stale once.** The
2026-07-29 rewrite inserted two scoring notes above the old note 3, shifting every note
below them down by one — and these strings did not move. So from July until 2026-08-10, the
answer written to probe *"do not score the teammate"* pointed at the no-team-history note,
and the answer written to probe no-team-history pointed at the specificity floor. Both are
printed by `recruit_review_compare.py` under *"written to probe"* as the record of what an
answer is for, so a divergence report was aiming the reader at the wrong clause. This is the
hand-maintained-list failure that `rubric.py` parses the catalogue to avoid, one layer up
and unguarded; `tests/test_review_set.py` now resolves every reference here against the real
catalogue, which catches a shift but not a swap between two clauses that both exist.

Answers are synthetic. No real candidate is described.
"""

from dataclasses import dataclass

QUESTION = "Tell us about a time you worked with someone who wasn't doing their share."


@dataclass(frozen=True)
class ReviewAnswer:
    ref: str
    transcript: str
    probes: str  # what this is for. Withheld from the reviewer until after he has scored.


# Deliberately not in ascending order. A set that climbs from weak to strong invites a
# reviewer to score the gradient rather than the answers.
ANSWERS: tuple[ReviewAnswer, ...] = (
    ReviewAnswer(
        "A",
        """
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
        "anchor.2 — the qualified self-focused candidate. The anchor C3 was written for.",
    ),
    ReviewAnswer(
        "B",
        """
At the distribution centre I supervised a team of about nine. We had an issue where two of
the pickers had a running disagreement about zone allocation that was starting to affect
throughput. I sat them both down separately first, got each version, then together, and we
agreed a rotation. It held — no further issues, and neither of them left.

I'd say that's a strength of mine. I don't let things fester and I don't take sides. You
address it, you document it, you move on. Most workplace friction is a process problem
wearing a personality costume.

As for here, the appeal is the structure and the clarity of the role. You know what's
expected, there's a chain of command, and the training is properly resourced.
""",
        "anchor.4B — handles people cleanly, appetite for the crew life unproven.",
    ),
    ReviewAnswer(
        "C",
        """
There was a lad on my shift at the depot, Ryan, who was turning up late fairly regularly.
It was putting the load on the rest of us in the mornings.

So I asked him about it. Just said, look, is everything alright, you've been late a fair
bit. And he said yeah, he was fine, nothing going on. So that was that, really. I kept an
eye on it and covered the first half hour when he wasn't there, and after a few weeks it
sort of settled down on its own.
""",
        "anchor.4 boundary — the teammate responds when spoken to but changes nothing. "
        "Pairs with F. Does answering count as 'an action'?",
    ),
    ReviewAnswer(
        "D",
        """
So, teamwork's probably the biggest thing in this job, right? I've always worked in team
environments. Construction, and before that a couple of years in a restaurant kitchen, and
both of those, you sink or swim together.

If somebody's not pulling their weight I think you've got to address it directly but
respectfully. You don't go straight to the supervisor, you talk to the person first. And
usually people respond to that. I've found most people want to do a good job, they just
sometimes need someone to say something.

We had good crews at both places. Everybody pulled their weight, we got along, we got the
work done.
""",
        "anchor.3 — the clone answer. Correct, generic, no incident, undifferentiated team.",
    ),
    ReviewAnswer(
        "E",
        """
I did three years on a landscaping crew, four of us, and honestly it was fine. Everyone
pulled their weight. If someone was slow you'd just help them out and they'd do the same
for you next time. That's how it works.

There was one lad who was newer and slower, and I spent a bit of time showing him how to
load the truck properly so he wasn't fighting it. He picked it up quick.

I've genuinely never had a problem with anyone I've worked with. I get on with everybody.
""",
        "note.5 — the unfalsifiable claim. Does 'never had a problem with anyone' pull an "
        "answer down, or is it a thing to note without moving the score?",
    ),
    ReviewAnswer(
        "F",
        """
Same sort of thing happened with a lad called Ryan at the depot — late most mornings, and
it was landing on the rest of us.

I asked him what was going on and he told me his mum had come out of hospital and he was
doing her medication before he left the house. He hadn't said anything because he didn't
want it treated as a special case. So he went to the supervisor himself and asked to move
to the back shift for a couple of months, which nobody had thought of, and that fixed it.
He's the one who sorted it — I just asked the question.
""",
        "anchor.4 boundary — the teammate takes real action and changes the situation. "
        "Pairs with C.",
    ),
    ReviewAnswer(
        "G",
        """
Yeah — so on the ambulance service I volunteered with, there was a guy, Marcus, who I got
on with really well. Most of them actually. It's a good crew, we'd do breakfast after night
shifts and I still see a couple of them.

But there was one, Tony, who just wouldn't restock the rig properly. Every shift you'd go
to grab something and it'd be short. I brought it up once, kind of jokingly, and he got a
bit funny about it, so after that I just started checking it myself before we rolled out.
Took me ten minutes. It was easier than having the conversation, honestly.

I loved that crew though. That's the part of this job I want — you're with the same people
for twenty-four hours, you eat together. I've missed it since I moved.
""",
        "anchor.4A — genuine appetite for the crew, real relationships, but friction "
        "handled by going around the person and narrated without discomfort.",
    ),
    ReviewAnswer(
        "H",
        """
Uh, honestly? I don't have a great example for that. I've mostly worked by myself. I did
five years driving long-haul, which is, you're alone in the truck. Before that I was doing
overnight stocking at a grocery warehouse and there were other people there but we weren't
really, we didn't work together — you just had your aisle.

I've got two younger brothers I helped raise after my mum got sick, if that counts. But
that's not a job.

I know that's probably not what you're looking for. I'm not trying to dodge the question, I
just don't want to make something up. I think I'd be alright on a crew, I get on with people
fine, but I can't point to a time it was actually tested the way you're asking.
""",
        "note.4 — a real offer that is too thin to score. He volunteers the caregiving and "
        "discounts it in the same breath.",
    ),
    ReviewAnswer(
        "I",
        """
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
        "anchor.5 — named person acts, and the candidate was changed by him.",
    ),
    ReviewAnswer(
        "J",
        """
Um. I mean, I haven't really had that come up. I've been self-employed since I was
twenty-one — small engine repair, out of my own shop, so it's just me. Customer brings the
thing in, I fix it, they pick it up.

I don't have anybody I've had a conflict with at work because I don't really have anybody
at work. I'm not sure what to tell you there.
""",
        "The not-assessable case: he establishes a solitary working life rather than "
        "declining to answer.",
    ),
    ReviewAnswer(
        "K",
        """
On the volunteer ambulance service there was a paramedic, Sinead, who I crewed with a lot.
She was carrying more than her share of the paperwork because the rest of us were slower at
it, and it was eating into her breaks.

I asked her about it and she said she'd rather do it herself than have it done wrong, which
was fair enough. So instead of just taking some off her we agreed she'd spend a shift
teaching the three of us her shortcuts. She ran that session herself, and after it the
paperwork spread properly and she got her breaks back.

I did two years there. It was useful experience and it's the reason I've got a decent sense
of what the job actually involves day to day. I've moved into logistics since, which pays
better, but I always intended to come back to this.
""",
        "anchor.4B, second attempt. B does not reach 4B — the pickers in it never act, so "
        "anchor.2 fires alongside and wins. Here the other person genuinely acts while the "
        "appetite for the crew stays instrumental. If neither B nor K reaches 4B, the route "
        "is probably unreachable, which bears directly on whether the routes should exist.",
    ),
    # Added 2026-08-17. E has been filed since July as the note 5 probe and has never once
    # probed it: across forty runs at n=20, twice, no determination has decided on "I've
    # genuinely never had a problem with anyone." Both the 5 and the 4B reach a verdict
    # before the closing line is reached, because E supplies a second behaviour — the lad
    # and the truck — and the breadth clause is settled by then.
    #
    # So this is E with that episode removed and nothing else changed. The setting, the
    # reciprocity disposition and the closing claim are E's word for word. What is gone is
    # the one concrete incident, which leaves the unfalsifiable claim as the only thing left
    # to decide on. §10: "a fixture, not a clause."
    #
    # NOT SCORED BY THE SME, and deliberately not slotted into the exercise file: that file
    # is generated, regenerating it would clobber the blind scores already in it, and a
    # fixture written after the exercise was run has no blind judgment behind it anyway.
    # `recruit_review_compare.py` already reports an unscored ref as "not yet scored" rather
    # than dropping it, so this costs the comparison nothing until he scores it.
    ReviewAnswer(
        "L",
        """
I did three years on a landscaping crew, four of us, and honestly it was fine. Everyone
pulled their weight. If someone was slow you'd just help them out and they'd do the same
for you next time. That's how it works.

I've genuinely never had a problem with anyone I've worked with. I get on with everybody.
""",
        "note.5 — the unfalsifiable claim, isolated. E with its second behaviour removed, so "
        "the closing line is the only thing left to decide on. Does it pull the answer below "
        "the generic-but-correct band, or is it a thing to note without moving the score?",
    ),
)

def by_ref(ref: str) -> ReviewAnswer:
    for answer in ANSWERS:
        if answer.ref == ref.upper():
            return answer
    raise KeyError(f"no review answer {ref!r}")
