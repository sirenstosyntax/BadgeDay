"""Critique models.

Same shape as `app/generate/models.py`, and for the same reason: what the model emits is
untrusted, and what BadgeDay shows a candidate has passed a gate.

- **Drafts** are model output. A draft point carries the `clause_id` it claims to come
  from and, where it asserts something the candidate said, the span of the transcript it
  is about.
- **Points** are verified. A verified point's clause has been resolved against the rubric
  that was actually loaded, so it cannot reference a criterion that does not exist.

The parallel to Promote is exact. There, `source_quote` proves a question is supported by
the section it cites. Here, `answer_quote` proves a point is about something the candidate
actually said rather than something the model supplied on his behalf — which is the
failure this product cannot ship, because bad Recruit feedback is confident career advice
to someone who cannot check it.

Unlike `source_quote`, `answer_quote` is kept. It is the candidate's own words, so there
is no copyright reason to discard it, and showing a candidate the sentence a point is
about is the difference between feedback he can act on and feedback he has to take on
trust.

**The score is internal.** It exists to structure the critique and is deliberately not
part of what gets rendered. See `recruit_design_decisions.md` §1.
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.critique.rubric import Clause

PointKind = Literal["rubric", "measurement"]


class Metric(BaseModel):
    """A deterministic measurement of delivery, computed in our own code.

    Not yet produced by anything — audio capture is build-order step 5. The seam exists
    now because the verification gate has to treat measurement-anchored points as a
    distinct class from the start, and retrofitting a second class of citable evidence
    into a gate is harder than leaving room for it.
    """

    name: str = Field(min_length=1, description="Stable identifier, e.g. 'filler_rate_per_100'.")
    value: float
    display: str = Field(min_length=1, description="How the value is written for a human.")
    band: str | None = Field(
        default=None,
        description=(
            "Where the value sits relative to a typical range. Bands, not minima — pace, "
            "length and pause frequency all have optimal ranges, and any display implying "
            "lower-is-better trains stilted delivery."
        ),
    )


# --- Drafts: untrusted model output ------------------------------------------


class DraftPoint(BaseModel):
    kind: PointKind = Field(
        description=(
            "'rubric' when the point applies a rubric clause; 'measurement' when it "
            "reports a computed metric."
        )
    )
    source_id: str = Field(
        min_length=1,
        description=(
            "The clause_id this point comes from (rubric points), or the metric name "
            "(measurement points). Must be one that was supplied."
        ),
    )
    answer_quote: str | None = Field(
        default=None,
        description=(
            "The span of the candidate's answer this point is about, copied exactly. "
            "Required whenever the point asserts something the candidate said. Omit only "
            "when the point is about something absent from the answer entirely."
        ),
    )
    observation: str = Field(
        min_length=1,
        description=(
            "What the answer did or did not do, in behavioural terms. May state how it is "
            "likely to read to a panel. Must not attribute an internal state, and must not "
            "supply language for the candidate to use."
        ),
    )
    ask: str | None = Field(
        default=None,
        description=(
            "A question putting the gap back to the candidate, so he supplies his own "
            "material. Never a suggested answer."
        ),
    )


class DraftCritique(BaseModel):
    """The top-level shape the model is constrained to emit."""

    assessable: bool = Field(
        description=(
            "False when the candidate's history does not contain the material this "
            "criterion asks about. Not a low score — the absence of a measurement."
        )
    )
    internal_score: int = Field(
        ge=0, le=5, description="The anchor the answer lands on, or 0 when not assessable."
    )
    route: Literal["4A", "4B", "n/a"] = "n/a"
    points: list[DraftPoint] = Field(default_factory=list)


# --- Verified: safe to show --------------------------------------------------


class Point(BaseModel):
    """A critique point that passed the gate."""

    kind: PointKind
    clause: Clause | None = None  # rubric points
    metric: Metric | None = None  # measurement points
    answer_quote: str | None = None
    observation: str
    ask: str | None = None

    model_config = {"arbitrary_types_allowed": True}

    def anchor_label(self) -> str:
        if self.clause is not None:
            return self.clause.label
        if self.metric is not None:
            return self.metric.display
        return "unanchored"


class Critique(BaseModel):
    """A verified critique. Every point traces to a rubric clause or a computed metric."""

    criterion_id: str
    criterion_name: str
    assessable: bool
    internal_score: int
    route: str
    points: list[Point]

    model_config = {"arbitrary_types_allowed": True}

    @property
    def rubric_points(self) -> list[Point]:
        return [point for point in self.points if point.kind == "rubric"]

    @property
    def measurement_points(self) -> list[Point]:
        return [point for point in self.points if point.kind == "measurement"]
