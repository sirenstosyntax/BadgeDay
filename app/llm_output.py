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
"""

from pydantic import ValidationError


class TruncatedOutput(Exception):
    """The model was still writing when it ran out of room.

    Its own type rather than a `ValueError` because it is the one model failure a caller
    can sensibly retry unchanged: the request was fine and got cut off. A caller that does
    not care can still catch `Exception` and report it like any other.
    """


def is_truncated_json(exc: ValidationError) -> bool:
    """True when parsing failed because the body stopped mid-JSON, not because it was wrong.

    Conservative on purpose: anything that is not clearly a truncation is re-raised as
    itself, so a genuine schema violation is never quietly relabelled as "try again".
    """
    return any(error.get("type") == "json_invalid" for error in exc.errors())
