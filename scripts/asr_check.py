"""Decide whether an ASR provider is usable for Recruit, on our own audio.

    python scripts/asr_check.py path/to/recording.m4a

`recruit_design_decisions.md` §5 names this the most likely silent failure in the audio
feature: **most ASR strips disfluencies by default**, and a provider that returns clean
fluent prose is a *better* transcriber by the industry's measure and a useless one by ours.
If "um" does not survive, the filler half of the delivery metrics is measuring nothing —
and it would measure nothing quietly, reporting 0.0 per hundred words for a candidate who
said "um" nine times.

Two requirements, and both have to hold:

1. **Word-level timestamps.** Every metric is arithmetic over them. Without them there is
   no pace, no pause, no stall.
2. **Preserved disfluencies.** The opposite of what most providers optimise for.

## Why this needs a real recording

Not TTS. Synthesised "um" is pronounced as a word — clear, full-length, at normal energy —
and any ASR will transcribe it. Real disfluencies are short, low-energy and slurred into
the words around them, which is exactly why models drop them. Passing on synthetic audio
would prove nothing and would create false confidence in the one place we cannot afford it.

Thirty seconds of ordinary speech with natural hesitation is enough. It does not need to be
about the fire service.
"""

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from app.audio.metrics import compute
from app.audio.models import CORE_FILLERS, Transcript, Word

# What we are checking for. Deliberately the *core* set only — if a provider drops these it
# drops everything, and if it keeps them the ambiguous cases barely matter.
LOOKING_FOR = sorted(CORE_FILLERS)


@dataclass
class Finding:
    provider: str
    words: int
    fillers_found: int
    has_word_timestamps: bool
    has_punctuation: bool
    sample: str

    @property
    def usable(self) -> bool:
        return self.has_word_timestamps and self.fillers_found > 0

    def report(self) -> str:
        lines = [
            f"\n=== {self.provider} " + "=" * (60 - len(self.provider)),
            f"  words transcribed   : {self.words}",
            f"  word timestamps     : {'yes' if self.has_word_timestamps else 'NO'}",
            f"  punctuation         : {'yes' if self.has_punctuation else 'no'}",
            f"  filler words kept   : {self.fillers_found}",
            "",
            f"  transcript: {self.sample[:300]}",
            "",
        ]
        if not self.has_word_timestamps:
            lines.append("  UNUSABLE — no word timestamps, so no metric can be computed.")
        elif self.fillers_found == 0:
            lines.append(
                "  UNUSABLE FOR FILLER — not one of "
                + ", ".join(LOOKING_FOR[:6])
                + " survived.\n"
                "  Check the recording actually contains them before blaming the provider;\n"
                "  if it does, this is the silent failure §5 warned about and the filler\n"
                "  metric must be dropped rather than shipped reporting zero."
            )
        else:
            lines.append("  USABLE — timestamps present and disfluencies survived.")
        if not self.has_punctuation:
            lines.append(
                "  Note: without punctuation, a pause between sentences cannot be told from\n"
                "  one mid-sentence. Those are opposite signals (§6), so the metrics will\n"
                "  report them together rather than guess."
            )
        return "\n".join(lines)


def _finding(provider: str, transcript: Transcript) -> Finding:
    normalised = [w.normalised() for w in transcript.words]
    timestamps = any(w.end > w.start for w in transcript.words)
    return Finding(
        provider=provider,
        words=len(transcript.words),
        fillers_found=sum(1 for token in normalised if token in CORE_FILLERS),
        has_word_timestamps=timestamps,
        has_punctuation=transcript.punctuated,
        sample=transcript.text,
    )


def check_deepgram(path: Path) -> Finding | None:
    """Deepgram nova with filler_words=true.

    Chosen as the first candidate on documentation: `filler_words=true` is an explicit,
    documented, no-extra-cost switch, and per-word start/end/confidence come back by
    default rather than as a priced add-on. Documentation is not evidence, which is what
    this script is for.
    """
    key = os.environ.get("DEEPGRAM_API_KEY")
    if not key:
        print("  skipping deepgram — DEEPGRAM_API_KEY not set")
        return None

    import httpx

    params = {
        "model": "nova-2",
        "filler_words": "true",
        "punctuate": "true",
        "smart_format": "false",  # smart_format tidies speech, which is the failure mode
    }
    response = httpx.post(
        "https://api.deepgram.com/v1/listen",
        params=params,
        headers={"Authorization": f"Token {key}"},
        content=path.read_bytes(),
        timeout=300,
    )
    response.raise_for_status()
    payload = response.json()
    alt = payload["results"]["channels"][0]["alternatives"][0]

    words = tuple(
        Word(
            text=w.get("punctuated_word", w["word"]),
            start=float(w["start"]),
            end=float(w["end"]),
            confidence=w.get("confidence"),
        )
        for w in alt.get("words", [])
    )
    transcript = Transcript(
        words=words,
        audio_seconds=float(payload["metadata"].get("duration", 0.0)),
        punctuated=any(w.text.endswith((".", "?", "!")) for w in words),
        provider="deepgram",
    )
    _save(path, transcript, "deepgram")
    return _finding("deepgram (nova-2, filler_words=true)", transcript)


def _save(path: Path, transcript: Transcript, provider: str) -> None:
    """Keep the transcript as a fixture, so the metrics get a real one to be tested against.

    The audio is not kept. §5: transcribe, compute, discard — voice is sensitive in a way
    text is not, and a recording of Grant saying "um" for thirty seconds has no reason to
    live in the repo.
    """
    out = Path("tests/fixtures/transcripts")
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"{path.stem}.{provider}.json"
    target.write_text(
        json.dumps(
            {
                "audio_seconds": transcript.audio_seconds,
                "punctuated": transcript.punctuated,
                "provider": transcript.provider,
                "words": [
                    {"text": w.text, "start": w.start, "end": w.end, "confidence": w.confidence}
                    for w in transcript.words
                ],
            },
            indent=2,
        )
    )
    print(f"  transcript saved to {target} (the audio is not kept)")


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"No such file: {path}")
        return 2

    print(f"checking providers against {path.name}")
    print(f"looking for any of: {', '.join(LOOKING_FOR)}")

    findings = [f for f in (check_deepgram(path),) if f is not None]
    if not findings:
        print(
            "\nNo provider was checked. Set DEEPGRAM_API_KEY (or add another provider "
            "here) and run again."
        )
        return 1

    for finding in findings:
        print(finding.report())

    # Show what the metrics actually make of it. A transcript that passes both checks can
    # still produce nonsense numbers, and this is the cheapest place to notice.
    usable = [f for f in findings if f.usable]
    if usable:
        fixture = sorted(Path("tests/fixtures/transcripts").glob(f"{path.stem}.*.json"))
        if fixture:
            from app.audio.transcriber import _from_json

            metrics = compute(_from_json(fixture[0].read_text()))
            print("\n=== what the metrics make of it " + "=" * 42)
            for metric in metrics.metrics:
                band = f"   [{metric.band}]" if metric.band else ""
                print(f"  {metric.name:<20} {metric.display}{band}")
            for note in metrics.notes:
                print(f"\n  note: {note}")

    return 0 if usable else 1


if __name__ == "__main__":
    raise SystemExit(main())
