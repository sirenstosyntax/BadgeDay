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
from app.critique.prompt import SYSTEM_PROMPT, build_retry_message, build_user_message
from app.critique.rubric import Rubric
from app.critique.verify import Rejection, verify_critique
from app.llm_output import (
    TruncatedOutput,
    UnenforcedConstraint,
    is_truncated_json,
    is_unenforced_constraint,
)

logger = logging.getLogger(__name__)

# Raised from 16k on 2026-08-10. `max_tokens` caps thinking *plus* the JSON body, and at
# effort `high` with adaptive thinking the reasoning is the larger half — two of eleven
# answers in the set re-run stopped mid-JSON, one of them on both attempts, so a third of the
# failures in that run were a budget we set rather than anything the model did wrong.
#
# Non-streaming is what forces a ceiling here at all: the SDK refuses a non-streaming request
# it estimates will outrun its own timeout, so the request now carries an explicit one. If
# truncation recurs at this budget the answer is to stream the call rather than to keep
# raising the number — but streaming loses `parsed_output`, so it is a real change and not
# worth making before it is needed.
MAX_TOKENS = 32_000
REQUEST_TIMEOUT_SECONDS = 600.0
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
            # Per-request rather than via `with_options`: the raised MAX_TOKENS is close to
            # where the SDK starts refusing non-streaming calls on its own timeout estimate,
            # and a request option keeps that concern next to the number that causes it.
            timeout=REQUEST_TIMEOUT_SECONDS,
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
        # A constraint the API was never asked to enforce — `min_length` and friends are
        # stripped from the schema before it is sent, so an empty field is legal output
        # rejected by our own validator. Retryable for the same reason truncation is: the
        # model was not breaking a rule it had been given.
        if is_unenforced_constraint(exc):
            raise UnenforcedConstraint(
                f"Critique returned a field our validator requires and the schema does not: "
                f"{'; '.join(e['loc'][-1] if e['loc'] else '?' for e in exc.errors())}"
            ) from exc
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
        except (TruncatedOutput, UnenforcedConstraint) as exc:
            # The two failures worth repeating the request for, for the same reason: nothing
            # is wrong with the prompt or the schema. A truncation was mid-sentence; an
            # unenforced constraint returned output that was legal under the schema the API
            # actually saw. Adaptive thinking means the next attempt is not the same length
            # or the same shape as this one. There is no usable draft to feed back, so the
            # messages stay as they are and the ask is simply made again.
            logger.warning(
                "Critique %s on attempt %d of %d: %s",
                "truncated" if isinstance(exc, TruncatedOutput) else "hit a stripped constraint",
                attempt,
                max_attempts,
                exc,
            )
            if attempt == max_attempts:
                outcome.failure = f"{type(exc).__name__}: {exc}"
                break
            # Deliberately not recorded on the outcome yet: an attempt that goes on to
            # succeed produced a sound critique, and reporting a failure beside it would
            # be false. The log line above is where a retried failure lives.
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
