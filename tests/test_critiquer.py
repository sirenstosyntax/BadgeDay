"""Critique loop tests.

These never call the API. What is being tested is the control flow around the call: when
it retries, when it stops, and what it reports when the request itself fails. The gate
that decides whether a point survives lives in `tests/test_critique_verify.py`.

The loop mattered enough to cover on its own once a truncated response was found being
reported as a rubric disagreement. See `app/llm_output.py`.
"""

from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import TypeAdapter, ValidationError

from app.config import Settings
from app.critique import rubric as rubric_module
from app.critique.critiquer import critique_answer
from app.critique.models import DraftCritique

QUESTION = "Tell us about a time you worked with someone who wasn't doing their share."

# Long enough that the gate has real spans to resolve against.
TRANSCRIPT = (
    "There was a lad on my shift at the depot, Ryan, who was turning up late fairly "
    "regularly. So I asked him about it. I said, look, is everything alright, you've been "
    "late a fair bit. And he said he was fine, nothing going on. So that was that, really. "
    "I kept an eye on it and covered the first half hour when he wasn't there."
)


@pytest.fixture
def rubric():
    return rubric_module.load("c3")


@pytest.fixture
def settings() -> Settings:
    return Settings(generation_model="claude-sonnet-5", generation_effort="high")


def _point(clause_id: str, **kw) -> dict:
    return {
        "kind": "rubric",
        "source_id": clause_id,
        "answer_quote": kw.get("answer_quote", "So I asked him about it"),
        "improvement": kw.get("improvement", "inventory"),
        "observation": kw.get(
            "observation", "He raised it once and accepted the first answer he was given."
        ),
        # Deliberately phrased to survive the gate's remedy rule: it puts the fork to him
        # without naming a single prescribed step. See `tests/test_critique_verify.py`.
        "ask": kw.get(
            "ask",
            "Is there an occasion where you went back a second time and found out what was "
            "actually going on? If there is not, that absence is itself worth knowing about.",
        ),
    }


def truncation_error(model: type) -> ValidationError:
    """A real parse failure of the shape a cut-off response produces.

    Built by validating genuinely truncated JSON through `TypeAdapter.validate_json` —
    the same call the SDK makes inside `messages.parse` — rather than by hand-rolling an
    error object. The point of the test is that the classification matches what pydantic
    actually raises, so faking the error would test the fake.
    """
    try:
        TypeAdapter(model).validate_json('{"outcome":"scored","internal_score":3,"poi')
    except ValidationError as exc:
        return exc
    raise AssertionError("that JSON should not have validated")


@dataclass
class _Response:
    parsed_output: Any
    stop_reason: str = "end_turn"


class FakeMessages:
    """Returns a queued draft per call, recording what it was asked."""

    def __init__(self, drafts: list[dict | Exception]) -> None:
        self._drafts = list(drafts)
        self.calls: list[dict] = []

    def parse(self, **kwargs: Any) -> _Response:
        self.calls.append(kwargs)
        nxt = self._drafts.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return _Response(parsed_output=DraftCritique.model_validate(nxt))


class FakeClient:
    def __init__(self, drafts: list[dict | Exception]) -> None:
        self.messages = FakeMessages(drafts)


def _run(client, rubric, settings, **kw):
    return critique_answer(
        rubric=rubric,
        question=QUESTION,
        transcript=kw.pop("transcript", TRANSCRIPT),
        client=client,
        settings=settings,
        **kw,
    )


# --- Nothing to critique -----------------------------------------------------


def test_an_empty_transcript_never_reaches_the_api(rubric, settings) -> None:
    client = FakeClient([])
    outcome = _run(client, rubric, settings, transcript="   ")
    assert outcome.failed
    assert outcome.failure
    assert client.messages.calls == []


# --- The happy path ----------------------------------------------------------


def test_a_clean_critique_stops_after_one_attempt(rubric, settings) -> None:
    draft = {
        "outcome": "scored",
        "internal_score": 3,
        "route": "n/a",
        "points": [_point("c3.anchor.3"), _point("c3.note.2")],
    }
    outcome = _run(FakeClient([draft]), rubric, settings)
    assert outcome.attempts == 1
    assert not outcome.failed
    assert outcome.failure is None
    assert len(outcome.critique.points) == 2


# --- Truncation --------------------------------------------------------------
#
# The failure that prompted this file. A response cut off mid-JSON raises from inside
# `messages.parse`, so the `stop_reason` check after it never runs — the loop used to see
# an opaque pydantic error, treat it as a bad request, and give up on the first attempt.


def test_a_truncated_response_is_retried_rather_than_abandoned(rubric, settings) -> None:
    draft = {
        "outcome": "scored",
        "internal_score": 3,
        "route": "n/a",
        "points": [_point("c3.anchor.3"), _point("c3.note.2")],
    }
    client = FakeClient([truncation_error(DraftCritique), draft])
    outcome = _run(client, rubric, settings)

    assert outcome.attempts == 2
    assert not outcome.failed
    assert len(client.messages.calls) == 2


def test_a_retried_truncation_does_not_leave_a_failure_behind(rubric, settings) -> None:
    """A critique that came back sound on the second ask is a success, not a warning."""
    draft = {
        "outcome": "scored",
        "internal_score": 3,
        "route": "n/a",
        "points": [_point("c3.anchor.3"), _point("c3.note.2")],
    }
    outcome = _run(FakeClient([truncation_error(DraftCritique), draft]), rubric, settings)
    assert outcome.failure is None


def test_the_retry_after_a_truncation_asks_again_unchanged(rubric, settings) -> None:
    """There is no draft to feed back — the rejection path would have nothing to quote."""
    draft = {
        "outcome": "scored",
        "internal_score": 3,
        "route": "n/a",
        "points": [_point("c3.anchor.3"), _point("c3.note.2")],
    }
    client = FakeClient([truncation_error(DraftCritique), draft])
    _run(client, rubric, settings)

    first, second = client.messages.calls
    assert second["messages"] == first["messages"]


def test_truncation_on_every_attempt_is_reported_as_truncation(rubric, settings) -> None:
    """Not as a schema problem — the distinction is what sends someone to the right place."""
    client = FakeClient([truncation_error(DraftCritique)] * 2)
    outcome = _run(client, rubric, settings)

    assert outcome.failed
    assert "TruncatedOutput" in outcome.failure
    assert "truncated" in outcome.failure
    assert outcome.attempts == 2


def test_a_schema_violation_is_not_relabelled_as_truncation(rubric, settings) -> None:
    """Complete JSON of the wrong shape needs the prompt changed, so it must read that way."""
    try:
        DraftCritique.model_validate_json('{"outcome":"scored","internal_score":99}')
    except ValidationError as exc:
        shape_error = exc
    else:
        raise AssertionError("a score of 99 should not have validated")

    outcome = _run(FakeClient([shape_error]), rubric, settings)
    assert outcome.failed
    assert "TruncatedOutput" not in outcome.failure
    # Given up on immediately: asking again produces the same wrong shape.
    assert outcome.attempts == 1
