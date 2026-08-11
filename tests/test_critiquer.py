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
from app.llm_output import is_truncated_json, is_unenforced_constraint

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


def _draft(**kw) -> dict:
    """A draft that survives the gate, outcome anchor included."""
    return {
        "outcome": kw.get("outcome", "scored"),
        "deciding_clause_id": kw.get("deciding_clause_id", "c3.anchor.3"),
        "determination": kw.get(
            "determination", "He opened the door and did not walk through it."
        ),
        "internal_score": kw.get("internal_score", 3),
        "route": kw.get("route", "n/a"),
        "points": kw.get("points", [_point("c3.anchor.3"), _point("c3.note.2")]),
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
    draft = _draft()
    outcome = _run(FakeClient([draft]), rubric, settings)
    assert outcome.attempts == 1
    assert not outcome.failed
    assert outcome.failure is None
    assert len(outcome.critique.points) == 2


# --- The outcome's own anchor ------------------------------------------------
#
# The score was the one judgment in the pipeline anchored to nothing, and the one that
# moved: 80 runs of zero variance on the scorer path against a three-anchor swing here.
# See `recruit_design_decisions.md` §7.


def test_the_deciding_clause_is_resolved_onto_the_critique(rubric, settings) -> None:
    outcome = _run(FakeClient([_draft(deciding_clause_id="c3.anchor.4B")]), rubric, settings)
    assert outcome.critique.deciding_clause is not None
    assert outcome.critique.deciding_clause.clause_id == "c3.anchor.4B"
    assert outcome.critique.determination


def test_an_outcome_anchored_to_a_clause_that_does_not_exist_is_rejected(
    rubric, settings
) -> None:
    """A score citing an invented clause is a number with nothing behind it."""
    client = FakeClient([_draft(deciding_clause_id="c3.anchor.99")] * 2)
    outcome = _run(client, rubric, settings)
    assert any(r.code == "deciding_clause_not_in_rubric" for r in outcome.rejections)


def test_an_outcome_anchored_to_another_criterion_is_rejected(rubric, settings) -> None:
    """The plausible failure: a real clause ID from the wrong rubric."""
    client = FakeClient([_draft(deciding_clause_id="c2.anchor.3")] * 2)
    outcome = _run(client, rubric, settings)
    assert any(r.code == "deciding_clause_not_in_rubric" for r in outcome.rejections)


def test_a_rejected_outcome_anchor_is_told_to_the_model_on_retry(rubric, settings) -> None:
    """The retry loop is fed the rejection text, so it has to name the clause that failed."""
    client = FakeClient([_draft(deciding_clause_id="c3.anchor.99"), _draft()])
    _run(client, rubric, settings)

    retry = client.messages.calls[1]["messages"][-1]["content"]
    assert "c3.anchor.99" in retry


# --- Truncation --------------------------------------------------------------
#
# The failure that prompted this file. A response cut off mid-JSON raises from inside
# `messages.parse`, so the `stop_reason` check after it never runs — the loop used to see
# an opaque pydantic error, treat it as a bad request, and give up on the first attempt.


def test_a_truncated_response_is_retried_rather_than_abandoned(rubric, settings) -> None:
    draft = _draft()
    client = FakeClient([truncation_error(DraftCritique), draft])
    outcome = _run(client, rubric, settings)

    assert outcome.attempts == 2
    assert not outcome.failed
    assert len(client.messages.calls) == 2


def test_a_retried_truncation_does_not_leave_a_failure_behind(rubric, settings) -> None:
    """A critique that came back sound on the second ask is a success, not a warning."""
    draft = _draft()
    outcome = _run(FakeClient([truncation_error(DraftCritique), draft]), rubric, settings)
    assert outcome.failure is None


def test_the_retry_after_a_truncation_asks_again_unchanged(rubric, settings) -> None:
    """There is no draft to feed back — the rejection path would have nothing to quote."""
    draft = _draft()
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



# --- The third failure category: constraints stripped before the schema is sent ----


def validation_error_for(body: str, model: type = DraftCritique) -> ValidationError:
    """Return the error `body` raises, rather than binding it in an `except` clause.

    `except ValidationError as exc` unbinds `exc` at the end of the block, so an error that
    needs to outlive the block has to be returned from a function. Both helpers below go
    through here for that reason.
    """
    try:
        TypeAdapter(model).validate_json(body)
    except ValidationError as exc:
        return exc
    raise AssertionError(f"that JSON should not have validated: {body[:60]}...")


def unenforced_constraint_error(model: type) -> ValidationError:
    """The parse failure an empty required field produces, built the same way as truncation.

    Real JSON through the real validator rather than a hand-built error object, for the
    reason `truncation_error` gives: the test is about matching what pydantic actually
    raises, so faking it would test the fake.

    The JSON here is complete and correctly shaped — every field present, every type right,
    two of them empty. That is exactly what came back on the 2026-08-10 set re-run, because
    `messages.parse` strips `min_length` before sending the schema and the model was never
    told the fields could not be blank.
    """
    body = (
        '{"outcome":"scored","deciding_clause_id":"c3.anchor.3",'
        '"determination":"He asked once and let it go.","internal_score":3,"route":"n/a",'
        '"points":[{"kind":"rubric","source_id":"c3.anchor.3","improvement":"inventory",'
        '"observation":"He raised it once.","ask":"Was there a second time?"},'
        '{"kind":"rubric","source_id":"","improvement":"inventory","observation":"","ask":""}]}'
    )
    return validation_error_for(body, model)


def test_the_empty_field_error_is_the_shape_we_think_it_is(rubric, settings) -> None:
    """Guard on the premise of the two tests below.

    If pydantic ever reports an empty `min_length=1` string as something other than
    `string_too_short`, the classification silently stops matching and an empty field goes
    back to being reported instead of retried. Cheap to pin, and it is the assumption
    everything else here rests on.
    """
    exc = unenforced_constraint_error(DraftCritique)
    types = {error["type"] for error in exc.errors()}
    assert types == {"string_too_short"}, types
    assert not is_truncated_json(exc), "an empty field is not a truncation"
    assert is_unenforced_constraint(exc)


def test_an_empty_required_field_is_retried_rather_than_reported(rubric, settings) -> None:
    """Found on the 2026-08-10 set re-run, where it cost answer H outright.

    The response was legal under the schema the API was actually sent, so the model was not
    breaking a rule it had been shown — which is what makes asking again worth a call, where
    a genuine shape violation is not.
    """
    client = FakeClient([unenforced_constraint_error(DraftCritique), _draft()])
    outcome = _run(client, rubric, settings)

    assert outcome.attempts == 2, "an empty field was reported instead of retried"
    assert not outcome.failed
    # Nothing left behind on the outcome: the attempt that succeeded produced a sound
    # critique, and reporting a failure beside it would be false.
    assert outcome.failure is None


def test_the_retry_after_an_empty_field_asks_again_unchanged(rubric, settings) -> None:
    """There is no usable draft to feed back, so the gate's retry message must not appear.

    Same reasoning as the truncation retry: the rejection was ours, not the model's, and
    telling it which points were rejected would be describing a critique it never produced.
    """
    client = FakeClient([unenforced_constraint_error(DraftCritique), _draft()])
    _run(client, rubric, settings)

    first, second = client.messages.calls
    assert first["messages"] == second["messages"]


def test_an_empty_field_on_every_attempt_is_reported_as_its_own_failure(
    rubric, settings
) -> None:
    """It must not be reported as a truncation — the follow-ups are different.

    A truncation says give it more room. This says the prompt should state the constraint the
    schema cannot carry across the wire.
    """
    error = unenforced_constraint_error(DraftCritique)
    outcome = _run(FakeClient([error, error]), rubric, settings)

    assert outcome.failed
    assert "UnenforcedConstraint" in (outcome.failure or "")
    assert "Truncated" not in (outcome.failure or "")


def test_a_shape_violation_mixed_with_an_empty_field_is_still_not_retried(
    rubric, settings
) -> None:
    """The `all` in `is_unenforced_constraint` is what this pins.

    A missing field alongside an empty one is a real schema defect that happens to contain an
    empty string. Retrying it spends a call to hide a bug, which is the distinction
    `app/llm_output.py` exists to keep.
    """
    mixed = validation_error_for(
        # Empty point fields *and* a missing deciding_clause_id.
        '{"outcome":"scored","determination":"No deciding clause at all.",'
        '"internal_score":3,"route":"n/a",'
        '"points":[{"kind":"rubric","source_id":"","improvement":"inventory",'
        '"observation":"","ask":""}]}'
    )
    assert not is_unenforced_constraint(mixed), "a missing field is a real schema violation"

    outcome = _run(FakeClient([mixed, _draft()]), rubric, settings)
    assert outcome.attempts == 1, "a shape violation was retried"
    assert outcome.failed
