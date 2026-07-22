"""Verification: the gate a draft must pass to become a stored question.

The brief's rule is that no question ships without a traceable source location, and that
low confidence means generating *fewer* questions rather than ungrounded ones. This
module is where that stops being a policy and becomes code: every draft is either
converted into a `Question` with a citation, or rejected with a reason.

Four things are checked, in order of how badly they break the product:

1. **Grounding.** The model's `source_quote` must actually appear in the chunk. A model
   that paraphrases, embellishes, or invents a supporting passage fails here. This is the
   check that stands between "cited" and "true".
2. **Copyright.** The quote must be short, and the stem must not reproduce a long
   verbatim run from the source. Questions are written in original words; citations point
   at locations rather than carrying the text.
3. **Structural validity.** Options distinct and indexable, answers present for the
   question's type.
4. **Substance.** The stem has to actually ask something.

A rejection is an expected outcome, not an error. The caller regenerates.

## What this cannot check

Verification proves a question is *supported by* the cited text. It cannot prove the
question is *worth asking*. A perfectly grounded, perfectly cited question about a
revision date teaches nothing. Page furniture is filtered upstream in the chunker for
exactly this reason, and heading-only chunks are excluded by `is_generatable` below.
"""

import re
import uuid
from dataclasses import dataclass

from app.generate.models import (
    Citation,
    DraftMultipleChoice,
    DraftQuestion,
    DraftShortAnswer,
    DraftTrueFalse,
    Question,
)
from app.ingest.models import Chunk

# A quote long enough to be a readable extract rather than a functional reference. The
# constraint is "short functional references", and this is where that gets a number.
MAX_QUOTE_CHARS = 240

# Longest run of consecutive words a stem may share with the source before it stops
# being an original question and starts being a reproduction. True/false stems press
# hardest against this, since a statement to judge naturally tracks the source closely —
# which is precisely why the model must be told to rewrite rather than copy.
MAX_VERBATIM_WORDS = 12


@dataclass(frozen=True)
class Rejection:
    """Why a draft did not become a question. Expected flow, not an error."""

    code: str
    detail: str


def _normalize(text: str) -> str:
    """Collapse whitespace and case so quote matching survives line breaks."""
    return re.sub(r"\s+", " ", text).strip().casefold()


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.casefold())


def longest_shared_run(stem: str, source: str) -> int:
    """Longest run of consecutive words appearing in both stem and source."""
    stem_words = _words(stem)
    source_words = _words(source)
    if not stem_words or not source_words:
        return 0

    # Index start positions by word so runs are only extended from real candidates.
    starts: dict[str, list[int]] = {}
    for index, word in enumerate(source_words):
        starts.setdefault(word, []).append(index)

    longest = 0
    for i, word in enumerate(stem_words):
        for j in starts.get(word, ()):
            run = 0
            while (
                i + run < len(stem_words)
                and j + run < len(source_words)
                and stem_words[i + run] == source_words[j + run]
            ):
                run += 1
            longest = max(longest, run)
    return longest


# A numbered section is structurally evidenced as body content, so a modest amount of
# text earns it a question. A chunk with no section number has no such evidence — it is
# as likely to be a title block or a revision stamp as it is to be prose — so it has to
# carry more substance before it is worth spending a request on.
MIN_WORDS_OUTLINE = 10
MIN_WORDS_SEMANTIC = 25


def is_generatable(chunk: Chunk) -> bool:
    """Is there anything in this chunk worth asking about?

    Two ways a chunk fails. A container heading — `304.3 Responsibilities`, whose
    substance lives entirely in its children — holds only its heading line. And a title
    block or revision stamp is prose-shaped but carries nothing an officer needs to know.

    Both would produce questions that are perfectly grounded and perfectly worthless, so
    neither the citation rule nor the verification gate catches them. Skipping is also
    the cheaper answer: the model, asked, correctly returns zero questions for a title
    block — but only after a request has been paid for.
    """
    body = chunk.text.strip()
    if not body:
        return False

    # Word count is the whole test. An earlier version also required more than one line,
    # on the assumption that a chunk is a heading followed by body text. That is wrong
    # for outline items: `PROCEDURE C.4` is a single block whose text *is* the
    # requirement, and it was being skipped as empty. A container heading is caught by
    # word count anyway — "304.3 Responsibilities" is two words.
    if chunk.section_path:
        return len(_words(body)) >= MIN_WORDS_OUTLINE

    return len(_words(body)) >= MIN_WORDS_SEMANTIC


def verify_draft(draft: DraftQuestion, chunk: Chunk) -> Question | Rejection:
    """Convert a draft into a storable question, or explain why it cannot be."""
    quote = draft.source_quote.strip()

    # 1. Grounding.
    if _normalize(quote) not in _normalize(chunk.text):
        return Rejection(
            "quote_not_in_source",
            "source_quote does not appear in the cited section; the question is not "
            "grounded in the text it claims.",
        )

    # 2. Copyright.
    if len(quote) > MAX_QUOTE_CHARS:
        return Rejection(
            "quote_too_long",
            f"source_quote is {len(quote)} characters; the limit is {MAX_QUOTE_CHARS}.",
        )

    shared = longest_shared_run(draft.stem, chunk.text)
    if shared > MAX_VERBATIM_WORDS:
        return Rejection(
            "stem_reproduces_source",
            f"stem shares a {shared}-word verbatim run with the source; the limit is "
            f"{MAX_VERBATIM_WORDS}. Rewrite the question in original words.",
        )

    # 3. Substance.
    if len(_words(draft.stem)) < 4:
        return Rejection("stem_too_short", "stem does not ask a complete question.")

    # 4. Structural validity, per type.
    citation = Citation.from_chunk(chunk)
    question_id = str(uuid.uuid4())

    if isinstance(draft, DraftMultipleChoice):
        options = [option.strip() for option in draft.options]
        if any(not option for option in options):
            return Rejection("empty_option", "one or more options are blank.")
        if len({option.casefold() for option in options}) != len(options):
            return Rejection("duplicate_options", "options are not distinct.")
        if not 0 <= draft.correct_index < len(options):
            return Rejection(
                "correct_index_out_of_range",
                f"correct_index {draft.correct_index} does not address one of "
                f"{len(options)} options.",
            )
        return Question(
            question_id=question_id,
            type="multiple_choice",
            stem=draft.stem.strip(),
            explanation=draft.explanation.strip(),
            citation=citation,
            options=options,
            correct_index=draft.correct_index,
        )

    if isinstance(draft, DraftTrueFalse):
        return Question(
            question_id=question_id,
            type="true_false",
            stem=draft.stem.strip(),
            explanation=draft.explanation.strip(),
            citation=citation,
            correct_answer=draft.correct_answer,
        )

    if isinstance(draft, DraftShortAnswer):
        if len(_words(draft.model_answer)) < 3:
            return Rejection(
                "model_answer_too_short",
                "short-answer questions need a model answer a candidate can grade "
                "themselves against.",
            )
        return Question(
            question_id=question_id,
            type="short_answer",
            stem=draft.stem.strip(),
            explanation=draft.explanation.strip(),
            citation=citation,
            model_answer=draft.model_answer.strip(),
        )

    return Rejection("unknown_type", f"unrecognized draft type {type(draft).__name__}.")


def verify_batch(
    drafts: list[DraftQuestion], chunk: Chunk
) -> tuple[list[Question], list[Rejection]]:
    """Verify a batch, keeping what passes.

    Partial success is the intended behaviour. Generating fewer questions is the
    prescribed response to low confidence, so one bad draft does not discard its
    siblings.
    """
    questions: list[Question] = []
    rejections: list[Rejection] = []
    for draft in drafts:
        result = verify_draft(draft, chunk)
        if isinstance(result, Rejection):
            rejections.append(result)
        else:
            questions.append(result)
    return questions, rejections
