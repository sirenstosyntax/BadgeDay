"""Transcription, behind a provider-neutral seam.

Same pattern and same reason as `app/ingest/analyzer.py`: `Transcriber` is the only thing
the rest of the pipeline knows about, so the Recruit loop can run against Deepgram or a
fixture without the API knowing which. `metrics.py` still gets coverage with no ASR
account and no real candidate's voice.

Two requirements a live provider has to meet (see `scripts/asr_check.py`):

1. **Word-level timestamps.** Every metric in `metrics.py` is arithmetic over them.
2. **Preserved disfluencies.** A transcript cleaned up into fluent prose is a *better*
   transcript by the industry's measure and a useless one by ours.

The live `/recruit/attempts` path computes delivery metrics from the returned
words; this module does not. It only turns audio into a `Transcript`.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from app.audio.models import Transcript, Word
from app.config import Settings


class Transcriber(Protocol):
    """Turns an audio file into words located in time."""

    def transcribe(self, path: Path) -> Transcript: ...


@dataclass(frozen=True)
class ProviderRequirements:
    """What a candidate provider has to prove before it is chosen.

    Written down because "we checked" decays into "somebody checked once" within a
    quarter, and because the second requirement is the one a provider's marketing will not
    answer — accuracy pages advertise clean transcripts, which is the failure mode.
    """

    word_timestamps: bool
    disfluencies_preserved: bool
    notes: str = ""

    @property
    def usable(self) -> bool:
        return self.word_timestamps and self.disfluencies_preserved


class FixtureTranscriber:
    """Reads a pre-recorded `Transcript` from JSON.

    Used by tests and by local development without any ASR account. A fixture is exactly
    what the real transcriber would have returned, so a test that passes here is testing
    the arithmetic rather than the mock.
    """

    def __init__(self, fixture_dir: Path) -> None:
        self.fixture_dir = fixture_dir

    def transcribe(self, path: Path) -> Transcript:
        fixture = self.fixture_dir / f"{path.stem}.json"
        if not fixture.exists():
            raise FileNotFoundError(
                f"No transcript fixture for {path.name}. Expected {fixture}. "
                "Set DEEPGRAM_API_KEY to transcribe real recordings."
            )
        return _from_json(fixture.read_text())


def get_transcriber(settings: Settings, fixture_dir: Path | None = None) -> Transcriber:
    """Deepgram when the key is set; the fixture transcriber otherwise."""
    if settings.transcription_configured:
        from app.audio.deepgram import DeepgramTranscriber

        return DeepgramTranscriber(settings)
    return FixtureTranscriber(fixture_dir or Path("tests/fixtures/transcripts"))


def _from_json(raw: str) -> Transcript:
    import json

    data = json.loads(raw)
    return Transcript(
        words=tuple(
            Word(
                text=w["text"],
                start=float(w["start"]),
                end=float(w["end"]),
                confidence=w.get("confidence"),
            )
            for w in data["words"]
        ),
        audio_seconds=float(data["audio_seconds"]),
        punctuated=bool(data.get("punctuated", False)),
        provider=data.get("provider", "fixture"),
        language=data.get("language"),
    )


def synthetic(
    spoken: str,
    *,
    wpm: float = 150.0,
    gaps: dict[int, float] | None = None,
    opening: float = 0.0,
    punctuated: bool = False,
) -> Transcript:
    """Build a transcript with known timings, for testing the arithmetic.

    Not a fake provider — a way of stating "these words, at this pace, with a gap of this
    length after word seven" so a metric can be asserted against a number worked out by
    hand rather than against whatever the code happened to produce.
    """
    gaps = gaps or {}
    per_word = 60.0 / wpm
    words: list[Word] = []
    clock = opening
    for index, token in enumerate(spoken.split()):
        words.append(Word(text=token, start=round(clock, 4), end=round(clock + per_word, 4)))
        clock += per_word + gaps.get(index, 0.0)
    return Transcript(
        words=tuple(words),
        audio_seconds=round(clock, 4),
        punctuated=punctuated,
        provider="synthetic",
    )
