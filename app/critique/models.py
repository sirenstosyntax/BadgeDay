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

# What a point asks the candidate to change. The score is instrumental; this is the part
# of a critique that does the work, and the two kinds are not interchangeable.
#
# - "answer"    — he has the material and did not deploy it. The fix is in the telling and
#                 he can act on it today.
# - "candidate" — he does not have the material. He covered a man's section for six weeks
#                 and never asked him why; no retelling fixes that. The fix is in his life,
#                 and this is what the readiness gap analysis is for.
# - "none"      — the point records something the answer did, with nothing to change.
#
# Collapsing the first two is what this field exists to prevent: rendered as one kind of
# bullet, a gap that requires going and doing something reads like a note about phrasing.
Improvement = Literal["answer", "candidate", "none"]


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
    improvement: Improvement = Field(
        description=(
            "'answer' when he has the material and did not deploy it — the fix is in the "
            "telling. 'candidate' when the material is missing from his life and no "
            "retelling would produce it — the fix is something he has to go and do. "
            "'none' when the point records something that worked."
        )
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
            "material. Never a suggested answer. On a 'candidate' point this names what is "
            "absent from his experience; it does not prescribe a specific certification, "
            "programme or provider."
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
    improvement: Improvement = "answer"
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

    @property
    def answer_gaps(self) -> list[Point]:
        """He has the material. The fix is in the telling."""
        return [point for point in self.points if point.improvement == "answer"]

    @property
    def development_gaps(self) -> list[Point]:
        """He does not have the material. The fix is in his life, not his phrasing.

        These are the points that feed the readiness gap analysis, and the reason the
        classification exists — rendered as ordinary bullets they read like notes about
        wording, when what they actually say is that a candidate needs to go and become
        someone who has the answer.
        """
        return [point for point in self.points if point.improvement == "candidate"]

    @property
    def worked(self) -> list[Point]:
        return [point for point in self.points if point.improvement == "none"]
