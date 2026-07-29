"""What a transcription gives us, and what we compute from it.

The unit is the word with a start and an end, because that is the smallest thing every
ASR provider agrees on and everything in `metrics.py` is arithmetic over it. Confidence is
carried where a provider supplies it and is deliberately not used for anything yet —
recording it costs nothing and inventing a use for it before we have measured whether it
correlates with anything would be worse than ignoring it.

`punctuated` matters more than it looks. Without punctuation a pause between sentences and
a pause in the middle of one are the same number, and `recruit_design_decisions.md` §6 says
those are opposite signals. The flag exists so the metrics can say *"I could not tell"*
rather than guess, which is the difference between a missing measurement and a wrong one.
"""

from dataclasses import dataclass
from typing import Literal

# Unambiguous fillers. Deliberately conservative: "like", "actually", "so" and "right" are
# all real words doing real work in fire-service speech ("a call like that one", "actually
# arrived first"), and counting them would inflate the rate with false positives. A filler
# rate a candidate cannot recognise as his own is worse than no filler rate, because he
# will conclude the tool is wrong about him and stop believing the rest of it.
CORE_FILLERS = frozenset({"um", "uh", "erm", "er", "ah", "mm", "hmm", "mhm", "uhh", "umm"})

# Multi-word hedges. Counted separately and reported separately, because they are a
# different habit from a vocal filler and the coaching for them is different.
HEDGE_PHRASES = (
    ("you", "know"),
    ("i", "mean"),
    ("sort", "of"),
    ("kind", "of"),
)

PauseKind = Literal["opening", "between_sentences", "mid_sentence", "unclassified"]


@dataclass(frozen=True)
class Word:
    """One word, located in time."""

    text: str
    start: float
    end: float
    confidence: float | None = None

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)

    def normalised(self) -> str:
        """Lowercased, stripped of punctuation, for matching against filler lists."""
        return "".join(c for c in self.text.lower() if c.isalpha() or c == "'")

    def ends_sentence(self) -> bool:
        return self.text.rstrip().endswith((".", "?", "!"))


@dataclass(frozen=True)
class Transcript:
    """A transcribed answer.

    `audio_seconds` is the length of the recording, which is not the same as the span of
    the words: a candidate who sat silent for four seconds and then spoke has an answer
    that starts at 4.0, and that silence is the single most interesting number in the
    whole transcript.
    """

    words: tuple[Word, ...]
    audio_seconds: float
    punctuated: bool = False
    provider: str = "fixture"
    language: str | None = None

    @property
    def text(self) -> str:
        return " ".join(word.text for word in self.words)

    @property
    def is_empty(self) -> bool:
        return not self.words


@dataclass(frozen=True)
class Pause:
    """A gap between two words, and where in the answer it fell."""

    after_index: int  # index of the word the pause follows; -1 for the opening pause
    seconds: float
    kind: PauseKind
