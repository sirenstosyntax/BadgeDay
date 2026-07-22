"""Generator loop tests.

These never call the API. What is being tested is the control flow around the call:
when it retries, when it stops, what it does with a section that should not be
questioned at all, and whether a failed request loses the questions already verified.
"""

from dataclasses import dataclass
from typing import Any

import pytest

from app.config import Settings
from app.generate.generator import generate_for_chunk, generate_for_document
from app.generate.models import DraftBatch
from app.ingest.models import Chunk

SOURCE = (
    "304.2.1 Interior Operations\n"
    "A minimum of two members shall enter the hazard area together and shall remain in "
    "voice or visual contact at all times.\n"
    "A charged hoseline shall be in place before the interior attack team advances past "
    "the entry point."
)


@pytest.fixture
def chunk() -> Chunk:
    return Chunk(
        chunk_id="chunk-1",
        document_id="doc-1",
        ordinal=3,
        kind="outline",
        section_number="304.2.1",
        section_title="Interior Operations",
        page_start=1,
        page_end=2,
        text=SOURCE,
    )


@pytest.fixture
def settings() -> Settings:
    return Settings(generation_model="claude-sonnet-5", generation_effort="high")


def _draft(quote: str = "a minimum of two members shall enter the hazard area", **kw) -> dict:
    return {
        "type": "multiple_choice",
        "stem": kw.get("stem", "How many members must enter a hazard area together?"),
        "options": ["One", "Two", "Three", "Four"],
        "correct_index": 1,
        "source_quote": quote,
        "explanation": "The guideline sets a two-member minimum.",
    }


@dataclass
class _Response:
    parsed_output: Any
    stop_reason: str = "end_turn"


class FakeMessages:
    """Returns a queued batch per call, recording what it was asked."""

    def __init__(self, batches: list[list[dict] | Exception]) -> None:
        self._batches = list(batches)
        self.calls: list[dict] = []

    def parse(self, **kwargs: Any) -> _Response:
        self.calls.append(kwargs)
        nxt = self._batches.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return _Response(parsed_output=DraftBatch.model_validate({"questions": nxt}))


class FakeClient:
    def __init__(self, batches: list[list[dict] | Exception]) -> None:
        self.messages = FakeMessages(batches)


# --- Skipping ----------------------------------------------------------------


def test_container_heading_is_skipped_without_calling_the_api(settings) -> None:
    """No request should be spent on a section with nothing to ask about."""
    chunk = Chunk(
        chunk_id="c",
        document_id="d",
        ordinal=5,
        kind="outline",
        section_number="304.3",
        section_title="Responsibilities",
        page_start=2,
        page_end=2,
        text="304.3 Responsibilities",
    )
    client = FakeClient([])
    outcome = generate_for_chunk(chunk, client, settings)
    assert outcome.skipped
    assert outcome.skipped_reason
    assert client.messages.calls == []
    assert outcome.questions == []


# --- The happy path ----------------------------------------------------------


def test_clean_batch_stops_after_one_attempt(chunk, settings) -> None:
    client = FakeClient([[_draft(), _draft(stem="What minimum crew size applies to entry?")]])
    outcome = generate_for_chunk(chunk, client, settings, target_count=2)
    assert outcome.attempts == 1
    assert len(outcome.questions) == 2
    assert outcome.rejections == []


def test_configured_model_and_effort_are_used(chunk, settings) -> None:
    client = FakeClient([[_draft()]])
    generate_for_chunk(chunk, client, settings, target_count=1)
    call = client.messages.calls[0]
    assert call["model"] == "claude-sonnet-5"
    assert call["output_config"]["effort"] == "high"
    assert call["output_format"] is DraftBatch


# --- Retry -------------------------------------------------------------------


def test_rejected_batch_triggers_a_retry_carrying_the_reasons(chunk, settings) -> None:
    """A bare retry reproduces the same fault — the model must be told what was wrong."""
    client = FakeClient([[_draft(quote="text that is nowhere in the section")], [_draft()]])
    outcome = generate_for_chunk(chunk, client, settings, target_count=1)

    assert outcome.attempts == 2
    assert len(outcome.questions) == 1
    assert [r.code for r in outcome.rejections] == ["quote_not_in_source"]

    retry_messages = client.messages.calls[1]["messages"]
    assert retry_messages[-1]["role"] == "user"
    assert "does not appear in the cited section" in retry_messages[-1]["content"]


def test_retry_stops_at_max_attempts(chunk, settings) -> None:
    """A section that will not yield good questions is allowed to yield none."""
    bad = [_draft(quote="not in the section at all")]
    client = FakeClient([bad, bad, bad])
    outcome = generate_for_chunk(chunk, client, settings, target_count=3, max_attempts=2)
    assert outcome.attempts == 2
    assert len(client.messages.calls) == 2
    assert outcome.questions == []
    assert len(outcome.rejections) == 2


def test_partial_success_is_kept_rather_than_discarded(chunk, settings) -> None:
    """Fewer questions is the prescribed outcome, not zero."""
    client = FakeClient([[_draft(), _draft(quote="invented")], [_draft(quote="also invented")]])
    outcome = generate_for_chunk(chunk, client, settings, target_count=4, max_attempts=2)
    assert len(outcome.questions) == 1
    assert len(outcome.rejections) == 2


# --- Failure -----------------------------------------------------------------


def test_api_failure_keeps_questions_already_verified(chunk, settings) -> None:
    client = FakeClient([[_draft(), _draft(quote="invented")], RuntimeError("network down")])
    outcome = generate_for_chunk(chunk, client, settings, target_count=4, max_attempts=2)
    assert len(outcome.questions) == 1


def test_api_failure_on_first_attempt_is_not_raised(chunk, settings) -> None:
    """One bad section must not abort a whole document's ingestion."""
    client = FakeClient([RuntimeError("network down")])
    outcome = generate_for_chunk(chunk, client, settings)
    assert outcome.questions == []
    assert not outcome.skipped


# --- Document level ----------------------------------------------------------


def test_document_generation_covers_every_chunk_in_order(chunk, settings) -> None:
    second = chunk.model_copy(update={"chunk_id": "chunk-2", "ordinal": 4})
    client = FakeClient([[_draft()], [_draft()]])
    outcomes = generate_for_document([chunk, second], client, settings, target_count=1)
    assert [o.chunk_id for o in outcomes] == ["chunk-1", "chunk-2"]
