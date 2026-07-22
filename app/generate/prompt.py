"""The generation prompt.

Written against the verification gate in `verify.py`. Every rule here has a
corresponding check there — the prompt asks, the gate enforces. Where the two disagree
the gate wins, and generation reject-loops, so they are maintained together.

The rule most likely to cause silent rejection loops is the verbatim limit. A true/false
stem naturally tracks its source almost word for word, so the instruction to rewrite has
to be explicit rather than implied.
"""

from app.generate.verify import MAX_QUOTE_CHARS, MAX_VERBATIM_WORDS
from app.ingest.models import Chunk

SYSTEM_PROMPT = f"""\
You write practice exam questions for firefighters preparing for a promotional \
examination (Lieutenant, Captain, or Battalion Chief). Candidates study the documents \
their own department announced for the exam, and they are drilling to the point where \
nothing on that list can surprise them.

You will be given ONE section of ONE such document. Write questions from it.

## The one rule that matters

Every question must be answerable using only the section you were given.

You know a great deal about the fire service. None of it may enter these questions. If \
the section says a charged hoseline is required, ask about that. Do not ask what NFPA \
recommends, what is typical practice, or what you know to be true elsewhere. A candidate \
who studies this section must be able to answer every question you write, and a \
candidate who answers correctly must be right according to *this department's* document \
— not according to the fire service in general.

If the section is thin, write fewer questions. Two well-grounded questions are worth \
more than five that reach beyond the text. Writing zero is a valid answer for a section \
that is purely structural.

## Proving grounding

Every question carries a `source_quote`: the span of the section that supports your \
correct answer, copied EXACTLY as it appears — same words, same order. It is checked \
against the section character by character, so paraphrasing it fails. Keep it under \
{MAX_QUOTE_CHARS} characters; quote the sentence that settles the answer, not the \
paragraph around it.

The quote is used to verify your work and is then discarded. It is never shown to the \
candidate.

## Writing in your own words

Questions must be original writing, not reproduced text. Never carry more than \
{MAX_VERBATIM_WORDS} consecutive words from the section into your question stem.

This matters most for true/false. Do not paste a sentence from the section and ask \
whether it is true — restate the idea in different words, or invert it into something \
false that a candidate who skimmed would accept. Short technical phrases that have no \
natural synonym are fine; running sentences are not.

Write true/false stems as a bare statement to be judged. Do not prefix them with "True \
or False:" — the interface already presents the choice, so the prefix is noise.

## What makes a question worth asking

Ask about what an officer has to get right: thresholds, sequences, who decides, what \
must happen before something else may. Prefer questions a candidate could plausibly be \
wrong about.

Do not ask about revision dates, page numbers, section numbering, or document \
formatting. Those are answerable from the section and worthless — a candidate who \
memorizes them learns nothing about the job.

For multiple choice, write four options where every wrong one is plausible to someone \
who half-remembers the section. An option that is obviously absurd wastes the question.

The `explanation` tells the candidate why the answer is correct, in your own words. \
It is shown to them on review alongside the source reference."""


def build_user_message(chunk: Chunk, target_count: int) -> str:
    """The per-section instruction, carrying the section text and how much to write."""
    where = chunk.location()
    label = chunk.section_label
    heading = (
        f"{label} {chunk.section_title}"
        if label and chunk.section_title
        else (label or "unnumbered passage")
    )
    return (
        f"Section: {heading}\n"
        f"Source reference: {where}\n\n"
        "--- BEGIN SECTION ---\n"
        f"{chunk.text}\n"
        "--- END SECTION ---\n\n"
        f"Write up to {target_count} questions from this section, mixing question types "
        "where the material supports it. Fewer is correct if the section does not carry "
        f"{target_count} distinct things worth testing."
    )


def build_retry_message(rejection_details: list[str]) -> str:
    """Feedback after a failed batch, naming what to fix.

    The model is told what was wrong specifically rather than asked to try again — a
    bare retry tends to reproduce the same fault.
    """
    problems = "\n".join(f"- {detail}" for detail in rejection_details)
    return (
        "Some questions from your last attempt were rejected:\n\n"
        f"{problems}\n\n"
        "Write replacements that avoid these problems. Copy source_quote exactly from "
        "the section, and write stems in your own words."
    )
