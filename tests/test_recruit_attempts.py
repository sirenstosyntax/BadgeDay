"""Ship gate #3 + #4: enqueue, poll, cap, free-first, entitlements gate.

No network. The HTTP handler must return 202 without calling Deepgram or
Anthropic. The worker is where metrics still have to reach critique_answer
(ship gate #2, moved off the request).
"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import CurrentUser, current_user, get_settings, user_db
from app.api.recruit import C2_SCENARIO_ID, metrics_for_critique, router
from app.audio.deepgram import transcript_from_deepgram
from app.config import Settings
from app.critique.cli import QUESTIONS
from app.critique.critiquer import CritiqueOutcome, RecruitPersist
from app.critique.models import Critique, Point
from app.storage.recruit import RecruitAttemptRecord
from app.worker.jobs import Job, enqueue
from app.worker.pipeline import EmptyRecruitAudio, run_recruit_critique
from tests.test_recruit_loop import DEEPGRAM_PAYLOAD, USER_ID
from tests.test_worker import FakeDb

ATTEMPT = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def _settings(**overrides) -> Settings:
    values = {
        "deepgram_api_key": "dg-test",
        "anthropic_api_key": "sk-test",
        "generation_model": "claude-sonnet-5",
        "generation_effort": "high",
        "recruit_free_sessions": 1,
        "recruit_daily_attempt_limit": 10,
    }
    values.update(overrides)
    return Settings(**values)


def _record(**overrides) -> RecruitAttemptRecord:
    values = {
        "id": ATTEMPT,
        "user_id": USER_ID,
        "scenario_id": C2_SCENARIO_ID,
        "question_text": QUESTIONS[C2_SCENARIO_ID],
        "started_at": datetime(2026, 9, 9, 18, 0, tzinfo=UTC),
        "status": "queued",
    }
    values.update(overrides)
    return RecruitAttemptRecord(**values)


def _client(settings: Settings, monkeypatch, *, authed: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    if authed:
        app.dependency_overrides[current_user] = lambda: CurrentUser(
            id=USER_ID, email="c@example.com", access_token="t"
        )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[user_db] = lambda: object()
    return TestClient(app)


def _ok_outcome() -> CritiqueOutcome:
    return CritiqueOutcome(
        critique=Critique(
            criterion_id="c2",
            criterion_name="Motivation",
            outcome="scored",
            determination="He named one thing he has done.",
            internal_score=3,
            route="n/a",
            points=[
                Point(
                    kind="rubric",
                    improvement="inventory",
                    observation="You named one thing you have done.",
                    ask="Is there a second step you have taken?",
                )
            ],
        ),
        attempt_id=ATTEMPT,
    )


# --- Enqueue -----------------------------------------------------------------


def test_submit_returns_202_and_does_not_critique(monkeypatch) -> None:
    captured: dict = {}

    def fake_create(db, user_id, **kwargs):
        captured["user_id"] = user_id
        captured["data"] = kwargs["data"]
        return _record()

    monkeypatch.setattr("app.api.recruit.count_attempts", lambda *a, **k: 0)
    monkeypatch.setattr("app.recruit.gate.recruit_entitled", lambda *a: False)
    monkeypatch.setattr("app.api.recruit.create_queued_attempt", fake_create)

    response = _client(_settings(), monkeypatch).post(
        "/recruit/attempts",
        files={"audio": ("answer.webm", b"fake-audio", "audio/webm")},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["attempt_id"] == ATTEMPT
    assert body["status"] == "queued"
    assert body["lines"] == []
    assert "score" not in body
    assert captured["user_id"] == USER_ID
    assert captured["data"] == b"fake-audio"


def test_enqueue_inserts_a_recruit_critique_job() -> None:
    db = FakeDb()
    enqueue(db, "recruit_critique", attempt_id=ATTEMPT)
    inserts = [entry for entry in db.log if entry[0] == "insert" and entry[1] == "jobs"]
    assert inserts
    row = inserts[0][2]
    assert row["kind"] == "recruit_critique"
    assert row["attempt_id"] == ATTEMPT
    assert "document_id" not in row


def test_submit_without_transcription_is_503(monkeypatch) -> None:
    response = _client(_settings(deepgram_api_key=""), monkeypatch).post(
        "/recruit/attempts",
        files={"audio": ("answer.webm", b"x", "audio/webm")},
    )
    assert response.status_code == 503


def test_unauthenticated_submit_is_401(monkeypatch) -> None:
    response = _client(_settings(), monkeypatch, authed=False).post(
        "/recruit/attempts",
        files={"audio": ("answer.webm", b"fake-audio", "audio/webm")},
    )
    assert response.status_code == 401


def test_empty_recruit_price_ids_are_placeholders() -> None:
    settings = Settings()
    assert settings.stripe_price_id_recruit_monthly == ""
    assert settings.stripe_price_id_recruit_intensive_90day == ""
    assert settings.stripe_price_id_recruit_6month == ""
    assert settings.stripe_price_id_recruit_annual == ""
    assert settings.play_product_id_recruit_monthly == ""
    assert settings.play_product_id_recruit_intensive_90day == ""
    assert settings.play_product_id_recruit_6month == ""
    assert settings.appstore_product_id_recruit_monthly == ""
    assert settings.appstore_product_id_recruit_intensive_90day == ""
    assert settings.appstore_product_id_recruit_6month == ""
    assert settings.appstore_product_id_recruit_annual == ""


# --- Cap and free-first ------------------------------------------------------


def test_daily_cap_is_429(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.recruit.count_attempts",
        lambda db, started_on_or_after=None: 10,
    )
    monkeypatch.setattr("app.recruit.gate.recruit_entitled", lambda *a: False)

    response = _client(_settings(), monkeypatch).post(
        "/recruit/attempts",
        files={"audio": ("answer.webm", b"x", "audio/webm")},
    )
    assert response.status_code == 429
    assert "today's limit of 10" in response.json()["detail"]


def test_used_free_session_without_entitlement_is_402(monkeypatch) -> None:
    def counts(db, started_on_or_after=None):
        return 1 if started_on_or_after else 1

    monkeypatch.setattr("app.api.recruit.count_attempts", counts)
    monkeypatch.setattr("app.recruit.gate.recruit_entitled", lambda *a: False)

    response = _client(_settings(), monkeypatch).post(
        "/recruit/attempts",
        files={"audio": ("answer.webm", b"x", "audio/webm")},
    )
    assert response.status_code == 402
    assert "Recruit plan" in response.json()["detail"]


def test_recruit_entitlement_is_has_recruit_access_not_has_access() -> None:
    calls: list[tuple[str, dict]] = []

    class FakeRpc:
        def rpc(self, name, args):
            calls.append((name, args))
            return self

        def execute(self):
            return type("R", (), {"data": False})()

    from app.recruit.gate import recruit_entitled

    assert recruit_entitled(FakeRpc(), USER_ID) is False
    assert calls == [("has_recruit_access", {"candidate": USER_ID})]


def test_a_recruit_entitlement_row_lets_the_second_attempt_through(monkeypatch) -> None:
    """The free session is used; the entitlements table is what opens the next one."""
    created: list[str] = []

    def fake_create(db, user_id, **kwargs):
        created.append(user_id)
        return _record()

    def counts(db, started_on_or_after=None):
        return 1

    monkeypatch.setattr("app.api.recruit.count_attempts", counts)
    monkeypatch.setattr("app.recruit.gate.recruit_entitled", lambda *a: True)
    monkeypatch.setattr("app.api.recruit.create_queued_attempt", fake_create)

    response = _client(_settings(), monkeypatch).post(
        "/recruit/attempts",
        files={"audio": ("answer.webm", b"x", "audio/webm")},
    )
    assert response.status_code == 202
    assert created == [USER_ID]


# --- Poll --------------------------------------------------------------------


def test_poll_queued_attempt(monkeypatch) -> None:
    monkeypatch.setattr("app.api.recruit.get_attempt", lambda db, _id: _record())
    response = _client(_settings(), monkeypatch).get(f"/recruit/attempts/{ATTEMPT}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "queued"
    assert body["lines"] == []
    assert body["attempt_id"] == ATTEMPT
    assert "internal_score" not in body
    assert "score" not in body


def test_poll_completed_attempt_returns_lines(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.recruit.get_attempt",
        lambda db, _id: _record(
            status="completed",
            candidate_lines=["WHAT YOU DID WELL", "You named one thing you have done."],
        ),
    )
    response = _client(_settings(), monkeypatch).get(f"/recruit/attempts/{ATTEMPT}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert "WHAT YOU DID WELL" in body["lines"]
    assert body["failed"] is False


def test_poll_failed_attempt(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.api.recruit.get_attempt",
        lambda db, _id: _record(
            status="critique_failed",
            error="The critique could not be finished.",
        ),
    )
    response = _client(_settings(), monkeypatch).get(f"/recruit/attempts/{ATTEMPT}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "critique_failed"
    assert body["failed"] is True
    assert "could not be finished" in body["failure"]
    assert body["lines"] == []


def test_poll_unknown_attempt_is_404(monkeypatch) -> None:
    monkeypatch.setattr("app.api.recruit.get_attempt", lambda db, _id: None)
    response = _client(_settings(), monkeypatch).get(f"/recruit/attempts/{uuid4()}")
    assert response.status_code == 404


# --- Worker still passes delivery metrics (ship gate #2) ---------------------


def test_worker_passes_computed_metrics_into_critique_answer(monkeypatch) -> None:
    captured: dict = {}
    transcript = transcript_from_deepgram(DEEPGRAM_PAYLOAD)
    audio_path = f"{USER_ID}/{ATTEMPT}/answer.webm"

    class FakeTranscriber:
        def __init__(self, settings: Settings) -> None:
            self.settings = settings

        def transcribe(self, path: Path):
            assert path.read_bytes() == b"fake-audio"
            return transcript

    def fake_critique_answer(**kwargs):
        captured.update(kwargs)
        return _ok_outcome()

    monkeypatch.setattr("app.worker.pipeline.DeepgramTranscriber", FakeTranscriber)
    monkeypatch.setattr("app.worker.pipeline.critique_answer", fake_critique_answer)
    monkeypatch.setattr(
        "app.worker.pipeline.get_attempt",
        lambda db, _id: _record(status="queued", audio_storage_path=audio_path),
    )
    monkeypatch.setattr("app.worker.pipeline.mark_running", lambda *a: None)
    monkeypatch.setattr("app.worker.pipeline.download_audio", lambda db, path: b"fake-audio")
    monkeypatch.setattr("app.worker.pipeline.delete_audio", lambda db, path: None)

    job = Job(
        id="job-r",
        kind="recruit_critique",
        attempt_id=ATTEMPT,
        status="running",
        attempts=1,
        max_attempts=3,
    )
    run_recruit_critique(object(), _settings(), job)

    assert captured["transcript"] == transcript.text
    assert captured["metrics"], "worker omitted metrics — critiques get the fallback"
    expected = metrics_for_critique(transcript)
    assert set(captured["metrics"]) == set(expected)
    persist = captured["persist"]
    assert isinstance(persist, RecruitPersist)
    assert persist.attempt_id == ATTEMPT
    assert persist.user_id == USER_ID
    assert persist.audio_retained is False


def test_worker_empty_transcript_is_terminal(monkeypatch) -> None:
    from app.audio.models import Transcript

    class FakeTranscriber:
        def __init__(self, settings: Settings) -> None:
            pass

        def transcribe(self, path: Path):
            return Transcript(words=(), audio_seconds=0.0, punctuated=False, provider="deepgram")

    monkeypatch.setattr("app.worker.pipeline.DeepgramTranscriber", FakeTranscriber)
    monkeypatch.setattr(
        "app.worker.pipeline.get_attempt",
        lambda db, _id: _record(
            status="queued", audio_storage_path=f"{USER_ID}/{ATTEMPT}/a.webm"
        ),
    )
    monkeypatch.setattr("app.worker.pipeline.mark_running", lambda *a: None)
    monkeypatch.setattr("app.worker.pipeline.download_audio", lambda db, path: b"xxxx")

    job = Job(
        id="job-r",
        kind="recruit_critique",
        attempt_id=ATTEMPT,
        status="running",
        attempts=1,
        max_attempts=3,
    )
    try:
        run_recruit_critique(object(), _settings(), job)
        raise AssertionError("expected EmptyRecruitAudio")
    except EmptyRecruitAudio as exc:
        assert exc.attempt_id == ATTEMPT
        assert "transcript" in exc.detail
