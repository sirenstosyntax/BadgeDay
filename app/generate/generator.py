"""Question generation against the Anthropic API.

The loop is: ask, verify, and if the batch came back short, tell the model exactly what
was rejected and ask again. Attempts are capped — the brief's instruction is that low
confidence means fewer questions, so a section that will not yield good questions is
allowed to yield few, or none.

Rejections are not errors. A section that produces two verified questions out of four
requested has done its job.
"""

import logging
from dataclasses import dataclass, field

from anthropic import Anthropic
from pydantic import ValidationError

from app.config import Settings
from app.generate.models import DraftBatch, Question
from app.llm_output import TruncatedOutput, is_truncated_json
from app.generate.prompt import SYSTEM_PROMPT, build_retry_message, build_user_message
from app.generate.verify import Rejection, is_generatable, verify_batch
from app.ingest.models import Chunk

logger = logging.getLogger(__name__)

MAX_TOKENS = 16_000
DEFAULT_TARGET_COUNT = 4
DEFAULT_MAX_ATTEMPTS = 2


@dataclass
class GenerationOutcome:
    """What one section produced, including what it failed to produce and why."""

    chunk_id: str
    questions: list[Question] = field(default_factory=list)
    rejections: list[Rejection] = field(default_factory=list)
    attempts: int = 0
    skipped_reason: str | None = None

    @property
    def skipped(self) -> bool:
        return self.skipped_reason is not None


def _request_drafts(
    client: Anthropic,
    settings: Settings,
    messages: list[dict],
) -> DraftBatch:
    """Ask for a batch, constrained to the DraftBatch schema.

    `messages.parse` passes the pydantic model through the SDK's schema transform, which
    strips the constraints structured outputs does not accept and re-validates them
    client-side. Hand-building the schema skips that transform and gets rejected.
    """
    try:
        response = client.messages.parse(
            model=settings.generation_model,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": settings.generation_effort},
            output_format=DraftBatch,
        )
    except ValidationError as exc:
        # Truncation surfaces here rather than on `stop_reason` below — the SDK validates
        # the body inside the call. See `app/llm_output.py` for why the two are worth
        # keeping apart. A batch is likelier to hit this than a critique: four questions
        # of JSON is more output than one critique, and the ceiling is the same.
        if is_truncated_json(exc):
            raise TruncatedOutput("Generation hit max_tokens; output truncated.") from exc
        raise
    if response.stop_reason == "max_tokens":  # complete JSON that still ran out of room
        raise TruncatedOutput("Generation hit max_tokens; output truncated.")
    if response.parsed_output is None:
        raise ValueError(
            f"Model returned no parseable output (stop_reason={response.stop_reason})."
        )
    return response.parsed_output


def generate_for_chunk(
    chunk: Chunk,
    client: Anthropic,
    settings: Settings,
    target_count: int = DEFAULT_TARGET_COUNT,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> GenerationOutcome:
    """Generate verified questions for one section."""
    outcome = GenerationOutcome(chunk_id=chunk.chunk_id)

    if not is_generatable(chunk):
        outcome.skipped_reason = "no substantive content to question"
        return outcome

    messages: list[dict] = [{"role": "user", "content": build_user_message(chunk, target_count)}]

    for attempt in range(1, max_attempts + 1):
        outcome.attempts = attempt
        try:
            batch = _request_drafts(client, settings, messages)
        except TruncatedOutput:
            # Worth repeating unchanged: the request was sound and the model ran out of
            # room mid-JSON, and adaptive thinking means the next attempt is not the same
            # length. Silently losing a section's questions to this is exactly the quiet
            # shortfall the generator is otherwise careful to report.
            logger.warning(
                "Generation truncated for chunk %s on attempt %d of %d",
                chunk.chunk_id,
                attempt,
                max_attempts,
            )
            if attempt == max_attempts:
                break
            continue
        except Exception:
            logger.exception("Generation request failed for chunk %s", chunk.chunk_id)
            break

        questions, rejections = verify_batch(batch.questions, chunk)
        outcome.questions.extend(questions)
        outcome.rejections.extend(rejections)

        if len(outcome.questions) >= target_count or not rejections:
            break
        if attempt == max_attempts:
            break

        # Carry the failed attempt and the specific reasons into the next request.
        messages.append({"role": "assistant", "content": batch.model_dump_json()})
        messages.append(
            {"role": "user", "content": build_retry_message([r.detail for r in rejections])}
        )

    logger.info(
        "chunk %s: %d verified, %d rejected, %d attempt(s)",
        chunk.chunk_id,
        len(outcome.questions),
        len(outcome.rejections),
        outcome.attempts,
    )
    return outcome


def generate_for_document(
    chunks: list[Chunk],
    client: Anthropic,
    settings: Settings,
    target_count: int = DEFAULT_TARGET_COUNT,
) -> list[GenerationOutcome]:
    """Generate across a document's chunks, in reading order."""
    return [
        generate_for_chunk(chunk, client, settings, target_count=target_count) for chunk in chunks
    ]
