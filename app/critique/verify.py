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

Five checks, ordered by how badly each breaks the product:

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

# Prescribing a remedy rather than naming a gap. Applies to development points only —
# where the finding is that the candidate's *life* lacks the material, not his telling.
#
# Naming a gap is low risk. Naming the programme that fills it is career advice with a cost
# in time and money, delivered to someone who cannot check it, and it is the same failure
# this product was built around — worse here than in the answer track, because a candidate
# can verify a claim about his own answer and cannot verify a claim about his future.
#
# How prescriptive this should be is open question 1 in `recruit_scope.md` and is Grant's
# to settle. Until then the conservative reading holds: name the absence, not the cure.
_PRESCRIBES_REMEDY = re.compile(
    r"""
    \b(
        (?:go\s+)?(?:get|obtain|earn|acquire)\s+(?:your|an?|the)\s+
            (?:emt|emr|paramedic|cpr|ffi|ff1|cdl|certificat|licen|degree|associate)
      | enrol{1,2}\s+in | sign\s+up\s+for | you\s+should\s+(?:take|join|volunteer|apply|enrol)
      | take\s+(?:a|an|the)\s+(?:course|class|academy|programme|program)\b
      | join\s+(?:a|an|the)\s+(?:volunteer|department|academy|programme|program)\b
      | apply\s+to\s+(?:a|an|the)\s+(?:academy|programme|program)\b
      | i\s+recommend | we\s+recommend | you\s+need\s+to\s+(?:get|take|join|enrol)
    )
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

    # 6. An inventory point is a fork put to the candidate, so it has to actually ask
    #    something. Without the question it is just an assertion about his life — which is
    #    the guess the inventory classification exists to avoid making.
    if draft.improvement == "inventory" and not (draft.ask or "").strip():
        return Rejection(
            "inventory_point_asks_nothing",
            "an inventory point must ask whether he has a better instance, and say what "
            "follows if he does not. Without the question it asserts something about his "
            "history rather than letting him settle it.",
        )

    # 7. Prescription, on the branches that give development advice. An answer point telling
    #    him to name what a teammate did is fine; telling him which certification to buy is
    #    a different act with a different cost.
    if draft.improvement in ("candidate", "inventory"):
        match = _PRESCRIBES_REMEDY.search(prose)
        if match:
            return Rejection(
                "prescribes_remedy",
                f"point contains {match.group(0)!r}, which prescribes a "
                "specific remedy rather than naming what is absent. Say what his "
                "experience does not yet contain and leave the route to it open.",
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

    critique = Critique(
        criterion_id=rubric.criterion_id,
        criterion_name=rubric.name,
        assessable=draft.assessable,
        internal_score=draft.internal_score if draft.assessable else 0,
        route=draft.route,
        points=points,
    )
    return critique, rejections
