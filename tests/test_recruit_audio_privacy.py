"""Deepgram opt-out, delete-failure alert, and the recruit-audio age check.

No network. The listen call is captured. Storage is a fake bucket.
"""

import importlib.util
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.audio.deepgram import LISTEN_URL, DeepgramTranscriber, listen_params
from app.config import Settings
from app.storage.recruit import (
    RECRUIT_AUDIO_DELETE_FAILED,
    RECRUIT_AUDIO_RETAINED_AFTER_SCORING_FAILURE,
    RecruitAudioDeleteError,
    delete_audio,
    discard_audio,
)
from app.storage.recruit_audio_retention import (
    RECRUIT_AUDIO_OLDER_THAN_ONE_DAY,
    StoredAudio,
    enforce_recruit_audio_retention,
    stale_audio_names,
)
from app.worker.pipeline import EmptyRecruitAudio
from app.worker.runner import _sweep_audio_retention, run_one
from tests.test_recruit_loop import DEEPGRAM_PAYLOAD

ROOT = Path(__file__).resolve().parents[1]
ATT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
NOW = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)


def test_listen_params_opt_out_of_model_improvement() -> None:
    params = listen_params("nova-2")
    assert params["mip_opt_out"] == "true"
    assert params["model"] == "nova-2"
    assert params["filler_words"] == "true"
    assert params["smart_format"] == "false"
    assert params["punctuate"] == "true"


def test_transcribe_sends_the_opt_out(monkeypatch, tmp_path: Path) -> None:
    captured: dict = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return DEEPGRAM_PAYLOAD

    def post(url, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs["params"]
        return Response()

    monkeypatch.setattr("app.audio.deepgram.httpx.post", post)
    audio = tmp_path / "answer.webm"
    audio.write_bytes(b"not-really-audio")
    transcript = DeepgramTranscriber(
        Settings(deepgram_api_key="dg-test", deepgram_model="nova-2")
    ).transcribe(audio)
    assert captured["url"] == LISTEN_URL
    assert captured["params"] == listen_params("nova-2")
    assert transcript.provider == "deepgram"


def test_asr_check_uses_the_shared_listen_params() -> None:
    source = (ROOT / "scripts" / "asr_check.py").read_text()
    assert "listen_params(" in source
    assert "mip_opt_out" not in source


def test_delete_failure_raises_the_error_metric(caplog: pytest.LogCaptureFixture) -> None:
    class Broken:
        def remove(self, paths):
            raise RuntimeError(f"storage down {paths}")

    class Storage:
        def from_(self, bucket):
            assert bucket == "recruit-audio"
            return Broken()

    db = SimpleNamespace(storage=Storage())
    with caplog.at_level(logging.ERROR), pytest.raises(RecruitAudioDeleteError) as raised:
        delete_audio(db, "user/attempt/answer.webm")
    assert raised.value.path == "user/attempt/answer.webm"
    assert RECRUIT_AUDIO_DELETE_FAILED in caplog.text
    assert "user/attempt/answer.webm" in caplog.text


def test_scoring_failure_delete_is_an_alert_and_the_job_still_finishes(
    monkeypatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The candidate is already marked failed. The alert must still fire."""
    from tests.test_worker import SETTINGS, _claimable

    def empty(*_args):
        raise EmptyRecruitAudio(ATT, "There was not enough in that recording.")

    def boom(_db, path):
        raise RecruitAudioDeleteError(path or "missing")

    db = _claimable(kind="recruit_critique", document_id=None, attempt_id=ATT)
    monkeypatch.setattr("app.worker.runner.HANDLERS", {"recruit_critique": empty})
    monkeypatch.setattr(
        "app.worker.runner.get_attempt",
        lambda *_: SimpleNamespace(audio_storage_path="user/attempt/a.webm", board_id=None),
    )
    monkeypatch.setattr("app.storage.recruit.delete_audio", boom)
    with caplog.at_level(logging.ERROR):
        assert run_one(db, SETTINGS, "w1") is True
    assert RECRUIT_AUDIO_RETAINED_AFTER_SCORING_FAILURE in caplog.text
    assert "user/attempt/a.webm" in caplog.text
    assert db.updates("jobs")[0]["status"] == "succeeded"
    assert db.updates("recruit_attempts")[0]["status"] == "critique_failed"


def test_discard_audio_names_the_attempt(caplog: pytest.LogCaptureFixture, monkeypatch) -> None:
    def boom(*_args):
        raise RecruitAudioDeleteError("p")

    monkeypatch.setattr("app.storage.recruit.delete_audio", boom)
    with caplog.at_level(logging.ERROR):
        discard_audio(
            object(),
            "p",
            attempt_id=ATT,
            metric=RECRUIT_AUDIO_RETAINED_AFTER_SCORING_FAILURE,
        )
    assert f"{RECRUIT_AUDIO_RETAINED_AFTER_SCORING_FAILURE} attempt={ATT} path=p" in caplog.text


def test_a_day_old_file_is_kept_and_an_older_one_is_not() -> None:
    objects = [
        StoredAudio("fresh.webm", NOW - timedelta(hours=23, minutes=59)),
        StoredAudio("exact.webm", NOW - timedelta(days=1)),
        StoredAudio("stale.webm", NOW - timedelta(days=1, seconds=1)),
    ]
    assert stale_audio_names(objects, now=NOW) == ["stale.webm"]


def test_retention_check_logs_when_a_file_is_too_old(caplog: pytest.LogCaptureFixture) -> None:
    old = NOW - timedelta(days=2)

    class Page:
        def __init__(self) -> None:
            self.objects = []
            self.folders = [SimpleNamespace(key="user", name="user")]
            self.hasNext = False
            self.nextCursor = None

    class FilePage:
        def __init__(self) -> None:
            self.objects = [
                SimpleNamespace(key="user/attempt/a.webm", name="a.webm", created_at=old)
            ]
            self.folders = []
            self.hasNext = False
            self.nextCursor = None

    class Bucket:
        def list_v2(self, options):
            if options["prefix"] == "":
                return Page()
            assert options["prefix"] == "user"
            return FilePage()

    class Storage:
        def from_(self, bucket):
            assert bucket == "recruit-audio"
            return Bucket()

    db = SimpleNamespace(storage=Storage())
    with caplog.at_level(logging.ERROR):
        stale = enforce_recruit_audio_retention(db, now=NOW)
    assert stale == ["user/attempt/a.webm"]
    assert RECRUIT_AUDIO_OLDER_THAN_ONE_DAY in caplog.text
    assert "count=1" in caplog.text


def test_retention_sweep_waits_a_month_after_a_clean_check() -> None:
    calls = {"n": 0}

    class Page:
        objects: list = []
        folders: list = []
        hasNext = False
        nextCursor = None

    class Bucket:
        def list_v2(self, _options):
            calls["n"] += 1
            return Page()

    db = SimpleNamespace(storage=SimpleNamespace(from_=lambda _name: Bucket()))
    first = _sweep_audio_retention(db, None, 100.0)
    assert calls["n"] == 1
    assert first == 100.0
    again = _sweep_audio_retention(db, first, first + 60)
    assert again == first
    assert calls["n"] == 1


def test_retention_script_fails_closed_without_credentials(monkeypatch) -> None:
    spec = importlib.util.spec_from_file_location(
        "recruit_audio_retention_check",
        ROOT / "scripts" / "recruit_audio_retention_check.py",
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(
        module,
        "get_settings",
        lambda: Settings(supabase_url="", supabase_service_role_key=""),
    )
    assert module.main() == 2


def test_privacy_page_states_what_deepgram_retains() -> None:
    text = (ROOT / "web" / "public" / "privacy.html").read_text()
    assert "Model Improvement Program" in text
    assert "90 days" in text
    assert "usage logs" in text
    assert "does not include the audio" in text or "do not include the audio" in text
    assert "We do not keep the recording." in text
    assert "do not store the recording after transcription." in text
