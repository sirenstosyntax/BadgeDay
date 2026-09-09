"""C2 V1 loop: transcript-only ASR parse, persist-after-verify, candidate payload.

Also pins ship-gate #2: Deepgram word timestamps become delivery metrics on the
live `/recruit/attempts` path and reach `critique_answer`. Without that wiring
the prompt falls back to "no delivery metrics were computed".

No network. No Deepgram account. No Anthropic account.
"""

from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import CurrentUser, current_user, get_settings
from app.api.recruit import C2_SCENARIO_ID, RecruitResult, metrics_for_critique, router
from app.audio.deepgram import DeepgramTranscriber, transcript_from_deepgram
from app.audio.metrics import compute
from app.audio.transcriber import FixtureTranscriber, get_transcriber
from app.config import Settings
from app.critique import rubric as rubric_module
from app.critique.cli import QUESTIONS
from app.critique.critiquer import CritiqueOutcome, RecruitPersist, critique_answer
from app.critique.models import Critique, DraftCritique, Point
from app.critique.prompt import build_user_message
from app.critique.render import candidate_lines
from tests.test_critiquer import FakeClient, _draft, _run

USER_ID = "55555555-5555-5555-5555-555555555555"

# Word timings Deepgram already returns. Opening beat + a filler + a mid-answer
# gap so `compute` has more than a pace figure to report.
DEEPGRAM_PAYLOAD = {
    "metadata": {"duration": 12.0},
    "results": {
        "channels": [
            {
                "alternatives": [
                    {
                        "words": [
                            {
                                "word": "um",
                                "punctuated_word": "Um",
                                "start": 1.5,
                                "end": 1.7,
                                "confidence": 0.8,
                            },
                            {
                                "word": "I",
                                "punctuated_word": "I",
                                "start": 1.8,
                                "end": 1.95,
                            },
                            {
                                "word": "prepared",
                                "punctuated_word": "prepared",
                                "start": 2.0,
                                "end": 2.4,
                            },
                            {
                                "word": "by",
                                "punctuated_word": "by",
                                "start": 2.45,
                                "end": 2.6,
                            },
                            {
                                "word": "volunteering.",
                                "punctuated_word": "volunteering.",
                                "start": 2.65,
                                "end": 3.3,
                            },
                            {
                                "word": "I",
                                "punctuated_word": "I",
                                "start": 6.0,
                                "end": 6.15,
                            },
                            {
                                "word": "got",
                                "punctuated_word": "got",
                                "start": 6.2,
                                "end": 6.35,
                            },
                            {
                                "word": "my",
                                "punctuated_word": "my",
                                "start": 6.4,
                                "end": 6.5,
                            },
                            {
                                "word": "EMT.",
                                "punctuated_word": "EMT.",
                                "start": 6.55,
                                "end": 7.0,
                            },
                        ]
                    }
                ]
            }
        ]
    },
}


def test_c2_question_is_the_cli_prompt() -> None:
    assert C2_SCENARIO_ID == "c2"
    assert QUESTIONS["c2"] == (
        "Why do you want to be a firefighter with this department, and what have you "
        "done to prepare?"
    )


def test_recruit_result_has_no_score_field() -> None:
    assert "internal_score" not in RecruitResult.model_fields
    assert "score" not in RecruitResult.model_fields
    assert "lines" in RecruitResult.model_fields
    assert "attempt_id" in RecruitResult.model_fields


def test_deepgram_payload_becomes_transcript_text() -> None:
    transcript = transcript_from_deepgram(DEEPGRAM_PAYLOAD)
    assert "volunteering." in transcript.text
    assert "Um" in transcript.text
    assert transcript.provider == "deepgram"
    assert transcript.audio_seconds == 12.0
    assert transcript.punctuated is True
    assert transcript.words[0].start == 1.5
    assert transcript.words[0].end == 1.7


def test_get_transcriber_uses_fixture_when_unconfigured() -> None:
    settings = Settings(deepgram_api_key="")
    transcriber = get_transcriber(settings)
    assert isinstance(transcriber, FixtureTranscriber)
    path = Path("answer.webm")
    transcript = transcriber.transcribe(path)
    assert "volunteering" in transcript.text
    assert transcript.provider == "fixture"


def test_get_transcriber_uses_deepgram_when_keyed() -> None:
    settings = Settings(deepgram_api_key="dg-test")
    transcriber = get_transcriber(settings)
    assert isinstance(transcriber, DeepgramTranscriber)


def test_persist_is_not_called_unless_asked(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    class FakeRpc:
        def rpc(self, name, args):
            calls.append((name, args))
            return self

        def execute(self):
            return type("R", (), {"data": "attempt-id"})()

    monkeypatch.setattr("app.critique.critiquer.service_client", lambda _settings: FakeRpc())
    rubric = rubric_module.load("c3")
    settings = Settings(generation_model="claude-sonnet-5", generation_effort="high")
    outcome = _run(FakeClient([_draft()]), rubric, settings)
    assert calls == []
    assert outcome.attempt_id is None
    assert outcome.failure is None


def test_persist_after_verify_stores_points_without_score_in_points(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    class FakeRpc:
        def rpc(self, name, args):
            calls.append((name, args))
            return self

        def execute(self):
            return type("R", (), {"data": "attempt-id"})()

    monkeypatch.setattr("app.critique.critiquer.service_client", lambda _settings: FakeRpc())
    rubric = rubric_module.load("c3")
    settings = Settings(generation_model="claude-sonnet-5", generation_effort="high")
    started = datetime(2026, 8, 18, 18, 0, tzinfo=UTC)
    outcome = critique_answer(
        rubric=rubric,
        question=QUESTIONS["c2"],
        transcript=(
            "There was a lad on my shift at the depot, Ryan, who was turning up late fairly "
            "regularly. So I asked him about it. I said, look, is everything alright, you've been "
            "late a fair bit. And he said he was fine, nothing going on. So that was that, really. "
            "I kept an eye on it and covered the first half hour when he wasn't there."
        ),
        client=FakeClient([_draft()]),
        settings=settings,
        persist=RecruitPersist(user_id="user-1", scenario_id="c2", started_at=started),
    )
    assert outcome.attempt_id == "attempt-id"
    assert outcome.failure is None
    assert calls and calls[0][0] == "persist_recruit_completed_attempt"
    args = calls[0][1]
    assert args["p_scenario_id"] == "c2"
    assert args["p_question_text"] == QUESTIONS["c2"]
    assert args["p_audio_retained"] is False
    for point in args["p_points"]:
        assert set(point) <= {"improvement", "observation", "ask", "answer_quote"}
    stored_keys = {key for point in args["p_points"] for key in point}
    assert "internal_score" not in stored_keys
    lines = candidate_lines(outcome.critique)
    joined = "\n".join(lines)
    score = outcome.critique.internal_score
    assert score is None or str(score) not in joined
    assert "[internal" not in joined
    assert "WHAT YOU DID WELL" in joined or "WHAT YOU COULD WORK ON" in joined


def test_draft_schema_still_parses() -> None:
    """Guard: the fake draft used above is still a real DraftCritique."""
    DraftCritique.model_validate(_draft())


def test_recruit_ui_has_no_rerecord_after_the_first_take() -> None:
    """Grant 2026-09-09: no preview, no re-record. The post-take control is gone."""
    source = Path(__file__).resolve().parents[1].joinpath("web/src/ui/Recruit.tsx").read_text()
    assert "Record again" not in source
    assert "phase !== 'ready'" in source
    _before, sep, rest = source.partition("{phase === 'recorded' && (")
    assert sep
    recorded_block, end, _tail = rest.partition("{phase === 'submitting'")
    assert end
    assert "Submit" in recorded_block
    assert "startRecording" not in recorded_block
    assert "Record answer" in source


# --- Ship gate #2: delivery metrics on the live attempt → critique path ------


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
                    ask="Is there a second step you have taken? If not, that absence is worth knowing.",
                )
            ],
        ),
        attempt_id="attempt-1",
    )


def _recruit_client(settings: Settings) -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[current_user] = lambda: CurrentUser(
        id=USER_ID, email="c@example.com", access_token="t"
    )
    app.dependency_overrides[get_settings] = lambda: settings
    return TestClient(app)


def test_deepgram_word_timestamps_become_critique_metrics() -> None:
    """The adapter the live path uses — not metrics.py in isolation.

    A Deepgram listen body with word start/end must produce the same named
    figures `compute` already tested, shaped as the Metric type critique_answer
    accepts. An empty dict here is the production fallback.
    """
    transcript = transcript_from_deepgram(DEEPGRAM_PAYLOAD)
    expected = compute(transcript)
    got = metrics_for_critique(transcript)

    assert got, "live path must not hand critique_answer an empty metrics dict"
    assert set(got) == {metric.name for metric in expected.metrics}
    for metric in expected.metrics:
        mapped = got[metric.name]
        assert mapped.name == metric.name
        assert mapped.value == metric.value
        assert mapped.display == metric.display
        assert mapped.band == metric.band

    assert "pace_wpm" in got
    assert "filler_per_100" in got
    assert "time_to_first_word" in got
    assert got["time_to_first_word"].value == 1.5
    assert got["filler_per_100"].value > 0


def test_computed_metrics_do_not_trigger_the_empty_fallback() -> None:
    """What the model would see if submit_attempt passed these metrics through."""
    transcript = transcript_from_deepgram(DEEPGRAM_PAYLOAD)
    message = build_user_message(
        rubric_module.load("c2"),
        QUESTIONS["c2"],
        transcript.text,
        metrics_for_critique(transcript),
    )
    assert "Computed delivery metrics, citable by name:" in message
    assert "pace_wpm" in message
    assert "No delivery metrics were computed" not in message


def test_critique_answer_receives_live_metrics_in_the_user_message() -> None:
    """critique_answer itself, the way the live path calls it — not a prompt unit test."""
    transcript = transcript_from_deepgram(DEEPGRAM_PAYLOAD)
    client = FakeClient([_draft()])
    settings = Settings(generation_model="claude-sonnet-5", generation_effort="high")
    outcome = critique_answer(
        rubric=rubric_module.load("c3"),
        question=QUESTIONS["c2"],
        transcript=transcript.text,
        client=client,
        settings=settings,
        metrics=metrics_for_critique(transcript),
        max_attempts=1,
    )
    content = client.messages.calls[0]["messages"][0]["content"]
    assert "Computed delivery metrics, citable by name:" in content
    assert "No delivery metrics were computed" not in content
    assert "pace_wpm" in content
    assert "filler_per_100" in content


def test_submit_attempt_passes_computed_metrics_into_critique_answer(
    monkeypatch,
) -> None:
    """The HTTP handler is the ship-gate item. Metrics must leave this function."""
    captured: dict = {}
    transcript = transcript_from_deepgram(DEEPGRAM_PAYLOAD)

    class FakeTranscriber:
        def __init__(self, settings: Settings) -> None:
            self.settings = settings

        def transcribe(self, path: Path):
            assert path.read_bytes() == b"fake-audio"
            return transcript

    def fake_critique_answer(**kwargs):
        captured.update(kwargs)
        return _ok_outcome()

    monkeypatch.setattr("app.api.recruit.DeepgramTranscriber", FakeTranscriber)
    monkeypatch.setattr("app.api.recruit.critique_answer", fake_critique_answer)

    settings = Settings(
        deepgram_api_key="dg-test",
        anthropic_api_key="sk-test",
        generation_model="claude-sonnet-5",
        generation_effort="high",
    )
    response = _recruit_client(settings).post(
        "/recruit/attempts",
        files={"audio": ("answer.webm", b"fake-audio", "audio/webm")},
    )
    assert response.status_code == 201, response.text
    assert captured["transcript"] == transcript.text
    assert captured["metrics"], "submit_attempt omitted metrics — critiques get the fallback"
    expected = metrics_for_critique(transcript)
    assert set(captured["metrics"]) == set(expected)
    for name, metric in expected.items():
        got = captured["metrics"][name]
        assert got.name == metric.name
        assert got.value == metric.value
        assert got.display == metric.display
        assert got.band == metric.band
    assert captured["persist"] is not None
    assert captured["persist"].user_id == USER_ID
    assert captured["persist"].audio_retained is False
