"""Candidate-facing strings for the five-question board.

Red-signed 2026-09-11, character-for-character. Do not paraphrase.
Internal scores, Delivery grades, routes, determinations, and rubric
vocabulary stay off this surface.
"""

BOARD_FRAMING = (
    "Board complete. Notes held until the end on purpose — same as a real board."
)

PER_ANSWER_NOT_ASSESSABLE = (
    "From what you said, this has not come up yet — so there is nothing here to "
    "judge you on, and this is not a mark against you."
)

PER_ANSWER_NOT_ANSWERED = (
    "There was not enough in that answer to say anything useful about it yet."
)

C1_LEAD = (
    "Across these five answers — how they were built. Not a score on any one of them."
)

C1_HELD = "WHAT HELD ACROSS THE BOARD"
C1_COSTS = "WHAT STILL COSTS YOU UNDER PRESSURE"
C1_OUTSIDE = "OUTSIDE WHAT THIS TOOL CAN HEAR"

C1_OUTSIDE_BODY = (
    "Presence, eye contact, and how you sit in the room are outside what this "
    "tool can hear. Work those with a mentor mock board, a station visit, or a "
    "ride-along — routes, not a booked provider."
)

C1_NOT_ANSWERED = (
    "There was not enough across these five answers to say anything useful "
    "about how they were built yet."
)

C1_INSUFFICIENT = (
    "From what you said across this board, there is not enough to judge how "
    "the answers were built — and that is not a mark against you."
)

# Soft timer. Display only — never an auto-submit.
SOFT_TIMER_SECONDS = 120

# Terminal slot with no spoken material. C1 cannot run; Leave abandons.
NOTES_BLOCKED = (
    "These notes can't be finished from that recording. Leave to abandon "
    "this board — no notes will be released."
)
