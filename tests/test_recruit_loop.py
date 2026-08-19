"""C2 V1 loop: transcript-only ASR parse, persist-after-verify, candidate payload.

No network. No Deepgram account. No Anthropic account.
"""

from datetime import UTC, datetime

from app.api.recruit import C2_SCENARIO_ID, RecruitResult
from app.audio.deepgram import transcript_from_deepgram
from app.config import Settings
from app.critique import rubric as rubric_module
from app.critique.cli import QUESTIONS
from app.critique.critiquer import RecruitPersist, critique_answer
from app.critique.models import DraftCritique
from app.critique.render import candidate_lines
from tests.test_critiquer import FakeClient, _draft, _run


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
    payload = {
        "metadata": {"duration": 2.5},
        "results": {
            "channels": [
                {
                    "alternatives": [
                        {
                            "words": [
                                {
                                    "word": "I",
                                    "punctuated_word": "I",
                                    "start": 0.0,
                                    "end": 0.2,
                                    "confidence": 0.9,
                                },
                                {
                                    "word": "prepared",
                                    "punctuated_word": "prepared.",
                                    "start": 0.3,
                                    "end": 0.8,
                                },
                            ]
                        }
                    ]
                }
            ]
        },
    }
    transcript = transcript_from_deepgram(payload)
    assert transcript.text == "I prepared."
    assert transcript.provider == "deepgram"
    assert transcript.audio_seconds == 2.5
    assert transcript.punctuated is True


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
    assert "internal_score" not in {key for point in args["p_points"] for key in point}
    lines = candidate_lines(outcome.critique)
    joined = "\n".join(lines)
    assert str(outcome.critique.internal_score) not in joined or outcome.critique.internal_score is None
    assert "[internal" not in joined


def test_draft_schema_still_parses() -> None:
    """Guard: the fake draft used above is still a real DraftCritique."""
    DraftCritique.model_validate(_draft())
