"""Every Deepgram listen call opts out of model improvement.

Deepgram's pre-recorded API defaults mip_opt_out to false. The worker and
scripts/asr_check.py both have to send the string "true" — httpx would
otherwise stringify a bool as "True", which is not the documented query value.
"""

import importlib.util
from pathlib import Path

import httpx
import pytest

from app.audio.deepgram import LISTEN_URL, DeepgramTranscriber, listen_params
from app.config import Settings
from tests.test_recruit_loop import DEEPGRAM_PAYLOAD

ROOT = Path(__file__).resolve().parents[1]


class _Response:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return DEEPGRAM_PAYLOAD


def test_listen_params_opt_out_for_any_model() -> None:
    params = listen_params("nova-3")
    assert params == {
        "model": "nova-3",
        "filler_words": "true",
        "punctuate": "true",
        "smart_format": "false",
        "mip_opt_out": "true",
    }


def test_transcriber_sends_mip_opt_out(monkeypatch, tmp_path: Path) -> None:
    captured: dict = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs["params"]
        captured["headers"] = kwargs["headers"]
        return _Response()

    monkeypatch.setattr("app.audio.deepgram.httpx.post", fake_post)
    audio = tmp_path / "answer.webm"
    audio.write_bytes(b"not-a-real-recording")

    transcript = DeepgramTranscriber(
        Settings(deepgram_api_key="dg-test", deepgram_model="nova-2")
    ).transcribe(audio)

    assert captured["url"] == LISTEN_URL
    assert captured["params"] == listen_params("nova-2")
    assert captured["params"]["mip_opt_out"] == "true"
    assert captured["headers"]["Authorization"] == "Token dg-test"
    assert transcript.provider == "deepgram"


def test_missing_key_does_not_call_deepgram(monkeypatch, tmp_path: Path) -> None:
    def boom(*_args, **_kwargs):
        raise AssertionError("listen was called without a key")

    monkeypatch.setattr("app.audio.deepgram.httpx.post", boom)
    with pytest.raises(RuntimeError, match="DEEPGRAM_API_KEY"):
        DeepgramTranscriber(Settings(deepgram_api_key="")).transcribe(tmp_path / "a.webm")


def _load_asr_check():
    spec = importlib.util.spec_from_file_location("asr_check", ROOT / "scripts" / "asr_check.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_asr_check_sends_the_same_opt_out(monkeypatch, tmp_path: Path) -> None:
    module = _load_asr_check()
    captured: dict = {}

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs["params"]
        return _Response()

    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: Settings(deepgram_api_key="dg-test", deepgram_model="nova-2"),
    )
    monkeypatch.setattr(module, "_save", lambda *_args, **_kwargs: None)
    audio = tmp_path / "sample.m4a"
    audio.write_bytes(b"not-a-real-recording")

    finding = module.check_deepgram(audio)

    assert finding is not None
    assert captured["url"] == LISTEN_URL
    assert captured["params"] == listen_params("nova-2")
    assert captured["params"]["mip_opt_out"] == "true"


def test_privacy_page_states_the_opt_out_request() -> None:
    flat = " ".join((ROOT / "web/public/privacy.html").read_text().split())
    assert "October 22, 2026" in flat
    assert "sets Deepgram's mip_opt_out parameter to true" in flat
    assert (
        "asks Deepgram not to retain the audio or the transcript for model improvement" in flat
    )
    # The page may only claim the request the code sends.
    assert "Deepgram does not retain" not in flat
    assert "Deepgram never retains" not in flat
