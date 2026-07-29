"""Critique generation against the Anthropic API.

The loop mirrors `app/generate/generator.py`: ask, verify, and if points were rejected,
tell the model exactly which and ask again. Attempts are capped.

Where this differs from generation is what a shortfall means. Generation is allowed to
return fewer questions — the brief's instruction is that low retrieval confidence yields
fewer questions rather than ungrounded ones. A critique with no surviving points is not a
thin critique, it is a failure: the candidate is waiting on feedback and there is none. So
a run that ends with nothing is surfaced as such rather than returned quietly.
"""

import logging
from dataclasses import dataclass, field

from anthropic import Anthropic
from pydantic import ValidationError

from app.config import Settings
from app.critique.models import Critique, DraftCritique, Metric
from app.llm_output import TruncatedOutput, is_truncated_json
from app.critique.prompt import SYSTEM_PROMPT, build_retry_message, build_user_message
from app.critique.rubric import Rubric
from app.critique.verify import Rejection, verify_critique

logger = logging.getLogger(__name__)

MAX_TOKENS = 16_000
DEFAULT_MAX_ATTEMPTS = 2
MIN_POINTS = 2


@dataclass
class CritiqueOutcome:
    """What one answer produced, including what it failed to produce and why."""

    critique: Critique | None = None
    rejections: list[Rejection] = field(default_factory=list)
    attempts: int = 0
    failure: str | None = None

    @property
    def failed(self) -> bool:
        return self.critique is None or not self.critique.points


def _request_draft(client: Anthropic, settings: Settings, messages: list[dict]) -> DraftCritique:
    """Ask for a critique, constrained to the DraftCritique schema.

    `messages.parse` passes the pydantic model through the SDK's schema transform, which
    strips the constraints structured outputs does not accept and re-validates them
    client-side. Hand-building the schema skips that transform and gets rejected.
    """
    try:
        response = client.messages.parse(
            model=settings.generation_model,
            max_tokens=MAX_TOKENS,
            system=[
                {"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}
            ],
            messages=messages,
            thinking={"type": "adaptive"},
            output_config={"effort": settings.generation_effort},
            output_format=DraftCritique,
        )
    except ValidationError as exc:
        # Truncation surfaces here rather than on `stop_reason` below — the SDK validates
        # the body inside the call. See `app/llm_output.py` for why the two are worth
        # keeping apart.
        if is_truncated_json(exc):
            raise TruncatedOutput("Critique hit max_tokens; output truncated.") from exc
        raise
    if response.stop_reason == "max_tokens":  # complete JSON that still ran out of room
        raise TruncatedOutput("Critique hit max_tokens; output truncated.")
    if response.parsed_output is None:
        raise ValueError(
            f"Model returned no parseable output (stop_reason={response.stop_reason})."
        )
    return response.parsed_output


def critique_answer(
    rubric: Rubric,
    question: str,
    transcript: str,
    client: Anthropic,
    settings: Settings,
    metrics: dict[str, Metric] | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> CritiqueOutcome:
    """Produce a verified critique of one answer against one criterion."""
    metrics = metrics or {}
    outcome = CritiqueOutcome()

    if not transcript.strip():
        outcome.failure = "empty transcript: there is no answer to critique"
        return outcome

    messages: list[dict] = [
        {"role": "user", "content": build_user_message(rubric, question, transcript, metrics)}
    ]

    for attempt in range(1, max_attempts + 1):
        outcome.attempts = attempt
        try:
            draft = _request_draft(client, settings, messages)
        except TruncatedOutput as exc:
            # The one failure worth repeating the request for. Nothing is wrong with the
            # prompt — the model was mid-sentence — and adaptive thinking means the next
            # attempt is not the same length as this one. There is no draft to feed back,
            # so the messages stay as they are and the ask is simply made again.
            logger.warning("Critique truncated on attempt %d of %d", attempt, max_attempts)
            if attempt == max_attempts:
                outcome.failure = f"{type(exc).__name__}: {exc}"
                break
            # Deliberately not recorded on the outcome yet: an attempt that goes on to
            # succeed produced a sound critique, and reporting a failure beside it would
            # be false. The log line above is where a truncation that got retried lives.
            continue
        except Exception as exc:  # noqa: BLE001 - surfaced on the outcome, not raised
            logger.exception("Critique request failed on attempt %d", attempt)
            outcome.failure = f"{type(exc).__name__}: {exc}"
            break

        critique, rejections = verify_critique(draft, rubric, transcript, metrics)
        outcome.critique = critique
        outcome.rejections.extend(rejections)

        # A not-scored outcome legitimately carries few points: there is no anchor to
        # apply, and the honest report is short.
        enough = len(critique.points) >= (MIN_POINTS if critique.scored else 1)
        if enough and not rejections:
            break
        if attempt == max_attempts:
            break

        messages.append({"role": "assistant", "content": draft.model_dump_json()})
        messages.append(
            {"role": "user", "content": build_retry_message([r.detail for r in rejections])}
        )

    if outcome.critique is not None and not outcome.critique.points and not outcome.failure:
        outcome.failure = "every point was rejected by the verification gate"

    logger.info(
        "%s: %d point(s) verified, %d rejected, %d attempt(s)",
        rubric.criterion_id,
        len(outcome.critique.points) if outcome.critique else 0,
        len(outcome.rejections),
        outcome.attempts,
    )
    return outcome
