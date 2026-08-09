"""Verification: the gate a critique point must pass before a candidate sees it.

The direct analog of `app/generate/verify.py`. There, no question ships without a
traceable source location. Here, **no critique point ships without a named criterion or a
computed metric behind it** — `recruit_scope.md`: *a critique that cannot point at the
criterion it came from is a defect, exactly as an uncited question is in Promote.*

The reason this gate matters more than its Promote counterpart is that its failures are
invisible. A bad Promote question is checkable — the candidate opens the SOG and sees we
were wrong. A critique that has quietly stopped referencing criteria still *looks* like
good feedback, and it is being read by someone who has no way to check it, at the moment
he is most inclined to believe it.

Six checks, ordered by how badly each breaks the product:

1. **Anchoring.** The point names a clause that exists in the rubric that was actually
   loaded, or a metric that was actually supplied. A point anchored to nothing, or to an
   invented clause, is free-roaming advice about somebody's career wearing a citation.
2. **Supplied language.** The most-requested feature that must not be built. The level 3
   anchor is the clone answer, so a tool that hands out phrasing manufactures clone
   answers at scale. Quoted text that is *not* in the candidate's transcript is the
   mechanical tell: the model is putting words in his mouth.
3. **Grounding.** Where a point quotes the candidate, the quote must actually appear in
   the transcript. Prevents critique of things he did not say.
4. **Internal-state attribution.** Permitted: how the answer is likely to *read*, tied to
   an observable behaviour. Rejected: claims about what he is or how he came across.
5. **Score disclosure.** Scores are internal. A point that tells him his number defeats
   the reason it is internal — surfaced scores get optimised, surfaced gaps get worked on.
6. **Rubric vocabulary.** The instrument does not talk about itself to the candidate. A
   point that names a criterion, an anchor or a scoring note is written to the rubric
   rather than to the man reading it, and it reads as a machine grading rather than as
   somebody who has done the job telling him what he did.

A rejection is an expected outcome, not an error. The caller regenerates, telling the
model exactly what was rejected — the same loop Promote's generator runs.

## What this cannot check

The gate proves a point is *anchored*. It cannot prove the point is *right*, and it
cannot prove the rubric it is anchored to is any good. A perfectly anchored critique
drawn from a bad anchor is exactly as confident and exactly as wrong. That is what SME
review is for, and no amount of verification substitutes for it.
"""

import re
from dataclasses import dataclass

from app.critique.models import Critique, DraftCritique, DraftPoint, Metric, Point
from app.critique.rubric import Rubric

# Longest quoted run a point may contain that is *not* the candidate's own words. Short
# quoted fragments are usually naming a rubric term ("a real step past the list"); a long
# one that is not in his transcript is a scripted sentence.
MAX_FOREIGN_QUOTE_WORDS = 4

# Shortest matching head that counts as evidence a quote *began* as real speech rather
# than coinciding by accident. Below this, report the quote as simply absent.
MIN_DIVERGENCE_PREFIX_CHARS = 20

# Handing the candidate words. Deliberately blunt: the cost of a false positive is one
# regenerated point, and the cost of a false negative is the product's central prohibition
# quietly failing.
_SUPPLIED_LANGUAGE = re.compile(
    r"""
    \b(
        try\s+saying | you\s+(?:could|should|might|can)\s+say | say\s+something\s+like
      | something\s+like | for\s+example,?\s+say | phrase\s+it | word\s+it
      | a\s+(?:stronger|better|good)\s+answer\s+would\s+(?:be|have\s+been|sound)
      | a\s+(?:stronger|better)\s+version | instead,?\s+say | rather\s+than\s+saying
      | here'?s\s+(?:how|what|a) | consider\s+saying | frame\s+it\s+as
      | you\s+might\s+put\s+it
    )\b
    """,
    re.I | re.X,
)

# Claims about the person rather than the answer. "That reads as résumé recital" is
# permitted; "you came across as arrogant" is not. The distinction is the subject of the
# sentence, so the patterns target the person-directed forms specifically.
_INTERNAL_STATE = re.compile(
    r"""
    \b(
        you\s+(?:came|come)\s+(?:across|off) | you\s+seem(?:ed)? | you\s+appear(?:ed)?
      | you\s+(?:clearly\s+)?(?:don'?t|do\s+not|didn'?t)\s+(?:care|want|value)
      | you\s+are\s+(?:arrogant|selfish|uncaring|dishonest|lazy)
      | you'?re\s+(?:arrogant|selfish|uncaring|dishonest|lazy)
      | your\s+attitude | you\s+genuinely
    )\b
    """,
    re.I | re.X,
)

# Telling him the number. Includes the rubric's own vocabulary, since "this is a level 2
# answer" discloses the score just as plainly as "you scored 2".
_SCORE_DISCLOSURE = re.compile(
    r"""
    \b(
        you\s+scored | your\s+score | scored?\s+a\s+[1-5]\b | (?:a|an)\s+level\s+[1-5]\b
      | level\s+[1-5]\s+answer | rated?\s+(?:a\s+)?[1-5]\b | [1-5]\s+out\s+of\s+5
      | this\s+is\s+a\s+[1-5]\b
    )\b
    """,
    re.I | re.X,
)

# Prescribing *the* remedy rather than offering possible ways to meet a gap.
#
# The settled line (`recruit_design_decisions.md` §3) is **possible ways, plural**: name
# routes people take and let him pick the one his life allows. Naming the single thing he
# must do is career advice with a cost in time and money, delivered to someone who cannot
# check it — and a menu is far harder to be badly wrong with than an instruction.
#
# So this guard is narrower than it looks. It targets the *directive* forms — second-person
# imperatives and first-person recommendations — and the definite singular, which smuggles
# the one-true-route back in under a different phrasing. It deliberately does **not** block
# the neutral naming of a route, because that is what a menu is made of: an earlier version
# rejected "join a volunteer department" outright, which made offering options impossible.
_PRESCRIBES_REMEDY = re.compile(
    r"""
    \b(
        you\s+(?:should|need\s+to|have\s+to|must|ought\s+to)\s+
            (?:get|take|join|enrol|enroll|apply|volunteer|sign|start|find|do)
      | (?:i|we)\s+(?:recommend|suggest|advise)
      | (?:go|go\s+and)\s+(?:get|join|enrol|enroll|sign\s+up|apply)\b
      | the\s+(?:best|right|only|obvious)\s+way\s+to
      | what\s+you\s+need\s+(?:to\s+do\s+)?is
      | your\s+next\s+step\s+(?:is|should\s+be)\b
    )
    """,
    re.I | re.X,
)

# The rubric's own vocabulary, leaking into what the candidate reads.
#
# Found by SME review 2026-08-06: a critique that was substantively right described the
# answer as failing "the cast-of-story test" and explained that "this criterion runs" across
# the whole board. Both are true and neither is candidate-facing — they are the instrument
# talking about itself to a man who is preparing for a board and has never seen it.
#
# This is a narrower failure than the ones above and costs less, but it costs on every
# critique rather than occasionally, and it is the difference between feedback that reads as
# a captain talking and feedback that reads as a machine grading. `determination` is
# deliberately not checked: it is internal, and naming the clause is its job.
_RUBRIC_JARGON = re.compile(
    r"""
    \b(
        (?:this|the|each|every|a)\s+criterion | criterion\s+\d
      | (?:this|the)\s+rubric | \brubrics?\b
      | (?:the|this|that|an|a|each)\s+anchors?
      | scoring\s+note | \bnotes?\s+\d\b
      | c\d\.(?:anchor|note)\.[0-9a-z]+
      | \b[1-5][AB]\b
      | cast[-\s]of[-\s](?:the[-\s])?story
      | deciding\s+clause | \bclause\s+\d | this\s+dimension
    )\b
    """,
    re.I | re.X,
)

# Quoted runs. Apostrophes are NOT treated as quote delimiters unless they sit at a word
# boundary on both sides, because this domain's prose is conversational and full of
# contractions: an earlier version read the apostrophes in "he'd ... what you're" as an
# open and close pair and rejected the whole span between them as a scripted phrase. That
# false positive is expensive — it either loses a sound point or burns a retry — and it
# fired on real output the first time the pipeline ran.
_QUOTED = re.compile(
    r"""
      "([^"]{2,}?)"                    # straight double
    | “([^”]{2,}?)”      # smart double
    | (?<!\w)'([^']{2,}?)'(?!\w)       # single, only at word boundaries
    """,
    re.X,
)


def _quoted_spans(text: str) -> list[str]:
    return [group for match in _QUOTED.finditer(text) for group in match.groups() if group]


@dataclass(frozen=True)
class Rejection:
    """Why a point did not survive the gate. Expected flow, not an error."""

    code: str
    detail: str


def _normalize(text: str) -> str:
    """Collapse whitespace, case and smart punctuation so quote matching survives speech."""
    text = text.replace("’", "'").replace("‘", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("—", "-").replace("–", "-")
    return re.sub(r"\s+", " ", text).strip().casefold()


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.casefold())


def _foreign_quotes(text: str, transcript: str) -> list[str]:
    """Quoted runs in a point that do not appear in the candidate's own words."""
    haystack = _normalize(transcript)
    foreign = []
    for quoted in _quoted_spans(text):
        if len(_words(quoted)) <= MAX_FOREIGN_QUOTE_WORDS:
            continue
        if _normalize(quoted) not in haystack:
            foreign.append(quoted)
    return foreign


def _quote_divergence(quote: str, transcript: str) -> str:
    """Say *where* a quote stops matching, not just that it failed.

    The first version of this message showed the quote's opening 60 characters, which on a
    spliced quote are the part that matched perfectly — so it told the reader (and the
    retry loop, which is fed this text) that a passage does not appear while showing them
    a passage that does. Pointing at the divergence makes the rejection actionable: a
    quote that stitches together two things the candidate said separately is the common
    case, and it is invisible from the opening words.
    """
    haystack = _normalize(transcript)
    needle = _normalize(quote)

    low, high = 0, len(needle)
    while low < high:
        middle = (low + high + 1) // 2
        if needle[:middle] in haystack:
            low = middle
        else:
            high = middle - 1

    # A prefix of one or two characters matches almost any transcript, so a short match is
    # not evidence of splicing — it is noise, and reporting it would point the retry loop
    # at a meaningless fragment. Only a substantial matching head means "this began as
    # something he really said".
    if low < MIN_DIVERGENCE_PREFIX_CHARS:
        return (
            f"answer_quote {quote[:80]!r} does not appear in the transcript at all; the "
            "point is about something the candidate did not say."
        )
    return (
        f"answer_quote stops matching the transcript after {needle[:low]!r}. The rest of "
        f"the quote ({needle[low:][:80]!r}) is not in the answer — it looks like two "
        "separate things the candidate said, joined into one quotation. Quote a single "
        "continuous passage, or drop the quote and describe what is missing."
    )


def verify_point(
    draft: DraftPoint,
    rubric: Rubric,
    transcript: str,
    metrics: dict[str, Metric],
) -> Point | Rejection:
    """Convert a draft point into a showable one, or explain why it cannot be."""
    prose = f"{draft.observation} {draft.ask or ''}"

    # 1. Anchoring.
    if draft.kind == "rubric":
        clause = rubric.clause(draft.source_id)
        if clause is None:
            return Rejection(
                "clause_not_in_rubric",
                f"point cites {draft.source_id!r}, which is not a clause of "
                f"{rubric.criterion_id}. Every point must name a clause that exists.",
            )
        metric = None
    else:
        metric = metrics.get(draft.source_id)
        if metric is None:
            return Rejection(
                "metric_not_supplied",
                f"point cites metric {draft.source_id!r}, which was not measured for this "
                f"answer. Available: {sorted(metrics) or 'none'}.",
            )
        clause = None

    # 2. Supplied language.
    match = _SUPPLIED_LANGUAGE.search(prose)
    if match:
        return Rejection(
            "supplies_language",
            f"point contains {match.group(0)!r}, which offers the candidate words to use. "
            "Name what is missing and ask for his own material instead.",
        )

    foreign = _foreign_quotes(prose, transcript)
    if foreign:
        return Rejection(
            "supplies_language",
            f"point quotes {foreign[0]!r}, which the candidate did not say — that is a "
            "scripted phrase, not an observation about his answer.",
        )

    # 3. Grounding.
    if draft.answer_quote is not None:
        quote = draft.answer_quote.strip()
        if not quote:
            return Rejection("empty_quote", "answer_quote is present but blank.")
        if _normalize(quote) not in _normalize(transcript):
            return Rejection(
                "quote_not_in_answer",
                _quote_divergence(quote, transcript),
            )

    # 4. Internal-state attribution.
    match = _INTERNAL_STATE.search(prose)
    if match:
        return Rejection(
            "attributes_internal_state",
            f"point contains {match.group(0)!r}, a claim about the candidate rather than "
            "about his answer. State how the answer is likely to read, tied to a behaviour.",
        )

    # 5. Score disclosure.
    match = _SCORE_DISCLOSURE.search(prose)
    if match:
        return Rejection(
            "discloses_score",
            f"point contains {match.group(0)!r}. The score is internal — report what is "
            "missing, not the number.",
        )

    # 6. Rubric vocabulary in candidate-facing prose. The point may be entirely sound and
    #    still be written to the instrument rather than to the man reading it.
    match = _RUBRIC_JARGON.search(prose)
    if match:
        return Rejection(
            "rubric_jargon",
            f"point contains {match.group(0)!r}, which is the rubric talking about itself. "
            "The candidate has never seen the rubric. Say what the answer did or did not "
            "do, in the words a captain would use across a table; the clause is recorded "
            "in source_id.",
        )

    # 7. An inventory point is a fork put to the candidate, so it has to actually ask
    #    something. Without the question it is just an assertion about his life — which is
    #    the guess the inventory classification exists to avoid making.
    if draft.improvement == "inventory" and not (draft.ask or "").strip():
        return Rejection(
            "inventory_point_asks_nothing",
            "an inventory point must ask whether he has a better instance, and say what "
            "follows if he does not. Without the question it asserts something about his "
            "history rather than letting him settle it.",
        )

    # 8. Prescription, on the branches that give development advice. An answer point telling
    #    him to name what a teammate did is fine; telling him which certification to buy is
    #    a different act with a different cost.
    if draft.improvement in ("candidate", "inventory"):
        match = _PRESCRIBES_REMEDY.search(prose)
        if match:
            return Rejection(
                "prescribes_remedy",
                f"point contains {match.group(0)!r}, which tells him the one thing "
                "to do. Offer possible ways the gap could be met instead — more than one, "
                "as routes rather than named providers, and spanning what they cost in "
                "money and time so a candidate without either can still act on one.",
            )

    return Point(
        kind=draft.kind,
        improvement=draft.improvement,
        clause=clause,
        metric=metric,
        answer_quote=draft.answer_quote.strip() if draft.answer_quote else None,
        observation=draft.observation.strip(),
        ask=draft.ask.strip() if draft.ask else None,
    )


def _verify_outcome(
    draft: DraftCritique, points: list[Point], rubric: Rubric
) -> Rejection | None:
    """Check the criterion-level conclusion, which is where the costly error lives.

    The two ways of declining to score are not symmetric. Saying *he did not answer* costs
    him one question. Saying *his life does not contain this* is a claim about a person,
    made to that person, on the strength of one paragraph — so it has to be earned the same
    way a Promote question is: by pointing at the words that support it.

    The outcome is anchored here on the same principle as a point. An outcome that names no
    clause of the loaded rubric is a score with nothing behind it — and unlike a stray point
    it cannot be dropped and the critique still stand, because everything else is built on
    the level it claims.
    """
    if rubric.clause(draft.deciding_clause_id) is None:
        return Rejection(
            "deciding_clause_not_in_rubric",
            f"the outcome cites {draft.deciding_clause_id!r} as the clause that decided it, "
            f"which is not a clause of {rubric.criterion_id}. Name the anchor the answer "
            "lands on, or the scoring note that overrode it.",
        )

    if draft.outcome == "not_assessable" and not any(p.answer_quote for p in points):
        return Rejection(
            "unsupported_not_assessable",
            "the critique concludes his history does not contain this material but quotes "
            "nothing that establishes it. The quote must be about his life ('it's just me', "
            "'I've worked alone since'), not about the question ('I don't have anything for "
            "that one') — the second says he is not producing a story now, which is not "
            "evidence he never has. Quote him on his history, or return 'not_answered' and "
            "ask.",
        )
    if draft.outcome == "not_answered" and not any(p.ask for p in points):
        return Rejection(
            "not_answered_asks_nothing",
            "a not-answered outcome must ask him for the material. Without the question it "
            "is a low score with better manners.",
        )
    return None


def verify_critique(
    draft: DraftCritique,
    rubric: Rubric,
    transcript: str,
    metrics: dict[str, Metric] | None = None,
) -> tuple[Critique, list[Rejection]]:
    """Verify a critique, keeping the points that pass.

    Partial success is intended, mirroring generation: one bad point does not discard its
    siblings. The caller decides whether what survived is enough, and regenerates with the
    rejections if not.
    """
    metrics = metrics or {}
    points: list[Point] = []
    rejections: list[Rejection] = []

    for draft_point in draft.points:
        result = verify_point(draft_point, rubric, transcript, metrics)
        if isinstance(result, Rejection):
            rejections.append(result)
        else:
            points.append(result)

    outcome_problem = _verify_outcome(draft, points, rubric)
    if outcome_problem is not None:
        rejections.append(outcome_problem)

    critique = Critique(
        criterion_id=rubric.criterion_id,
        criterion_name=rubric.name,
        outcome=draft.outcome,
        deciding_clause=rubric.clause(draft.deciding_clause_id),
        determination=draft.determination.strip(),
        internal_score=draft.internal_score if draft.outcome == "scored" else 0,
        route=draft.route,
        points=points,
    )
    return critique, rejections
