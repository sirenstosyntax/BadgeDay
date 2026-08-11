"""Telling a cut-off model response apart from a wrong one.

Both the generator and the critiquer ask for schema-constrained output through
`client.messages.parse`, and both used to guard truncation like this:

    response = client.messages.parse(...)
    if response.stop_reason == "max_tokens":
        raise ValueError("... output truncated.")

That guard could never fire. `messages.parse` validates the body *while constructing the
response* — `parse_response` → `parse_text` → `TypeAdapter.validate_json` — so a reply cut
off mid-JSON raises `ValidationError` from inside the SDK call and the next line never
runs. The caller got a 200-line pydantic traceback ending in `EOF while parsing a string
at line 1 column 12519` instead of the sentence someone had already written for it.

Worth being precise about why that matters rather than treating it as tidiness. The two
failures need opposite responses:

- **Truncated.** The model was still writing. Nothing is wrong with the prompt, the
  schema, or the rubric. Asking again, or asking for less, works.
- **Schema violation.** The model returned complete JSON of the wrong shape. Asking again
  changes nothing; the schema or the prompt has to.

Collapsed together they read as the second, which is the expensive misdiagnosis: it sends
you looking for a bug in the prompt that is not there. It cost exactly that once already —
a transient truncation on one answer in the Criterion 3 calibration run was reported as
the anchors disagreeing with the SME, and three clean re-runs of the same answer put it
back in agreement. A false divergence in a calibration report is worse than a crash,
because the whole point of the exercise is to trust the divergences.

Pydantic distinguishes them itself: a body that stops mid-JSON fails with `json_invalid`
before any field is looked at, where a shape mismatch reports per-field error types
(`missing`, `string_type`, and so on). That flag is the whole signal.

## A third category, found on 2026-08-10

Those two are not exhaustive, and the gap cost an answer in the Criterion 3 set re-run:

    points.1.source_id  String should have at least 1 character
    points.1.observation  String should have at least 1 character

That is complete, well-formed JSON of the right *shape* — every field present, every type
correct — with two of them empty. It was filed as a schema violation and not retried, on the
reasoning above that asking again changes nothing.

**But the model was never told those fields could not be empty.** `messages.parse` strips the
constraints structured outputs does not accept — `min_length`, numeric bounds, array
lengths — from the schema it sends, and re-validates them client-side afterwards. So the API
enforced a schema in which `""` is perfectly legal, the model returned something legal under
it, and the rejection happened on our side of the wire against a rule the model never saw.

That is neither of the original categories. It is not truncation, and it is not the model
returning the wrong shape — it is a constraint that exists only in our validator. Asking
again *does* help, because there was no rule being violated to violate again, and the
emptiness is as stochastic as any other token choice.

Kept as a third predicate rather than folded into truncation because the two want different
responses beyond the retry: a truncation says give it more room, and this says the prompt
should state the constraint the schema cannot carry.
"""

from pydantic import ValidationError

# Pydantic error types for constraints `messages.parse` strips before sending the schema.
# The model is never shown these, so violating one is not a shape error on its part.
#
# Deliberately a closed list of the constraints this codebase actually uses. A type that is
# not here falls through to being treated as a genuine schema violation, which is the safe
# direction: a wrongly-retried request costs one call, a wrongly-retried *schema* bug hides
# a real defect behind a retry loop.
_UNENFORCED_CONSTRAINTS = frozenset(
    {
        "string_too_short",
        "string_too_long",
        "too_short",
        "too_long",
        "greater_than",
        "greater_than_equal",
        "less_than",
        "less_than_equal",
        "multiple_of",
    }
)


class TruncatedOutput(Exception):
    """The model was still writing when it ran out of room.

    Its own type rather than a `ValueError` because it is the one model failure a caller
    can sensibly retry unchanged: the request was fine and got cut off. A caller that does
    not care can still catch `Exception` and report it like any other.
    """


class UnenforcedConstraint(Exception):
    """Legal output under the schema the API was sent, rejected by our own validator.

    The second retryable failure. Distinct from `TruncatedOutput` because the follow-up
    differs: a truncation wants more room, and this wants the prompt to state a rule the
    schema cannot carry across the wire.
    """


def is_truncated_json(exc: ValidationError) -> bool:
    """True when parsing failed because the body stopped mid-JSON, not because it was wrong.

    Conservative on purpose: anything that is not clearly a truncation is re-raised as
    itself, so a genuine schema violation is never quietly relabelled as "try again".
    """
    return any(error.get("type") == "json_invalid" for error in exc.errors())


def is_unenforced_constraint(exc: ValidationError) -> bool:
    """True when *every* failure is a constraint the API was never asked to enforce.

    `all` rather than `any`, and that is the whole care in this function. A response with one
    empty string and one missing field is a genuine schema violation that happens to also
    have an empty string in it; retrying it would paper over the real defect. Only a response
    whose every complaint is an unenforced constraint is worth asking again for.

    Empty on purpose returns False — a `ValidationError` with no errors is not a category we
    understand, and the safe reading of "we don't know" is "do not retry".
    """
    errors = exc.errors()
    return bool(errors) and all(
        error.get("type") in _UNENFORCED_CONSTRAINTS for error in errors
    )
