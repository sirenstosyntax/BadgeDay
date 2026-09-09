"""Deepgram implementation of the Transcriber seam.

Returns a `Transcript` with word-level timestamps. Delivery metrics are computed
from those words on the live `/recruit/attempts` path, not here — this file stays
a transcriber. The listen call already exists as a configured paid API
(`DEEPGRAM_API_KEY`); this file does not add a package.

The request matches `scripts/asr_check.py`: nova-2, filler_words on, smart_format
off. smart_format tidies speech, which is the failure mode for filler metrics.
"""

from pathlib import Path

import httpx

from app.audio.models import Transcript, Word
from app.config import Settings

LISTEN_URL = "https://api.deepgram.com/v1/listen"


def transcript_from_deepgram(payload: dict) -> Transcript:
    """Turn a Deepgram listen body into a Transcript. No network."""
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
    return Transcript(
        words=words,
        audio_seconds=float(payload.get("metadata", {}).get("duration", 0.0)),
        punctuated=any(word.text.endswith((".", "?", "!")) for word in words),
        provider="deepgram",
    )


class DeepgramTranscriber:
    """One listen call. Raises if the key is missing or Deepgram refuses the audio."""

    def __init__(self, settings: Settings) -> None:
        self._key = settings.deepgram_api_key
        self._model = settings.deepgram_model

    def transcribe(self, path: Path) -> Transcript:
        if not self._key:
            raise RuntimeError("DEEPGRAM_API_KEY is not set")
        response = httpx.post(
            LISTEN_URL,
            params={
                "model": self._model,
                "filler_words": "true",
                "punctuate": "true",
                "smart_format": "false",
            },
            headers={"Authorization": f"Token {self._key}"},
            content=path.read_bytes(),
            timeout=300,
        )
        response.raise_for_status()
        return transcript_from_deepgram(response.json())
