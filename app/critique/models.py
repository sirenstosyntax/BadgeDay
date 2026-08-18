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
# - "inventory" — the default, and most gaps are this. The answer does not show the thing,
#                 and we cannot tell from here whether he has a better instance in his life
#                 or none at all. He can tell in five seconds and we cannot tell at all, so
#                 the point asks him: is there a better story for this, and if there is not,
#                 that is the thing to go and get. Either branch makes him better, which is
#                 why the fork is free.
# - "answer"    — the material is visibly present in this answer and merely mishandled: the
#                 outcome buried, the specific thing said and dropped. No guess required.
# - "candidate" — the answer positively establishes the absence — he said he has never done
#                 it. Narrow on purpose; inferring it is how we would end up asserting
#                 things about a life we cannot see.
# - "risk"      — not a gap at all. A way of retelling this material that would cost him at
#                 the next board, attached to material that worked here. Scoring note 10:
#                 reported, never deducted for, because it names something *absent* from the
#                 answer. Kept separate from the gaps for the same reason "candidate" is kept
#                 separate from "answer" — rendered among faults, a caution reads as one.
# - "none"      — the point records something that worked, with nothing to change.
#
# The distinction this field exists to protect: a gap that needs him to go and do something
# must not render as a note about phrasing. The reason most gaps carry "inventory" instead
# of a verdict is that deciding between the last two requires knowing his history, and one
# answer is not his history.
Improvement = Literal["inventory", "answer", "candidate", "risk", "none"]

# What the criterion could conclude from this answer. Three states rather than two,
# because "his life lacks this" and "this answer told us nothing" are opposite epistemic
# positions and collapsing them lets a man who simply did not answer be told something
# about his history that nobody established.
#
# - "scored"         — enough to apply an anchor.
# - "not_assessable" — the answer positively establishes the material is absent from his
#                      life. A conclusion, and it has to be earned: the gate requires a
#                      quote of the words that establish it.
# - "not_answered"   — silence, refusal, a pivot elsewhere. No basis either way, so the
#                      honest output asks him. The inventory fork, one level up.
Outcome = Literal["scored", "not_assessable", "not_answered"]


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
            "'inventory' — the default for a gap. The answer does not show the thing and "
            "you cannot tell whether he has a better instance or none; ask him, and say "
            "what follows if the answer is no. 'answer' only when the material is visibly "
            "in this answer and merely mishandled. 'candidate' only when the answer states "
            "outright that he has never done it. 'risk' when nothing here is wrong but a "
            "way of retelling this material would cost him next time — never a deduction, "
            "at most one. 'none' when it records something that worked."
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
            "material. Never a suggested answer. Required on an 'inventory' point, where "
            "it asks whether he has a better instance AND says what to do if he does not. "
            "On 'inventory' and 'candidate' points it names what is absent from his "
            "experience; it never prescribes a specific certification, programme or "
            "provider."
        ),
    )


class DraftCritique(BaseModel):
    """The top-level shape the model is constrained to emit.

    **Field order is load-bearing.** Structured output is emitted in declaration order, so
    the determination is written before the score and the score before the points. The
    outcome is a conclusion drawn from a named clause, and a model that emits the number
    first and the reasoning after has decided nothing — it has guessed and then justified.
    """

    outcome: Outcome = Field(
        description=(
            "'scored' when an anchor applies. 'not_assessable' only when the answer says "
            "outright that his life does not contain this material — you must be able to "
            "quote him. 'not_answered' when he gave nothing to judge either way: silence, "
            "a refusal, a request to repeat, or a pivot to another subject."
        )
    )
    deciding_clause_id: str = Field(
        min_length=1,
        description=(
            "The one clause of the rubric that decided this outcome — the anchor the answer "
            "lands on, or the scoring note that took it somewhere else. Must be a clause_id "
            "from the catalogue supplied with the rubric. Where a scoring note overrides an "
            "anchor, name the note, because the note is what decided it."
        ),
    )
    determination: str = Field(
        min_length=1,
        description=(
            "Why that clause and not the one on either side of it, in a sentence or two, "
            "referring to what the candidate actually said. This is the reasoning the score "
            "rests on and it is written before the score, not after it. Internal — never "
            "shown to the candidate."
        ),
    )
    internal_score: int = Field(
        ge=0, le=5, description="The anchor the answer lands on, or 0 when not scored."
    )
    route: Literal["4A", "4B", "n/a"] = "n/a"
    points: list[DraftPoint] = Field(default_factory=list)


# --- Verified: safe to show --------------------------------------------------


class Point(BaseModel):
    """A critique point that passed the gate."""

    kind: PointKind
    improvement: Improvement = "inventory"
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
    """A verified critique. Every point traces to a rubric clause or a computed metric.

    So does the outcome. `deciding_clause` is the anchor determination, resolved against
    the rubric that was actually loaded — the same treatment a point's clause gets, for the
    same reason. It was added after the outcome turned out to be the one judgment in the
    pipeline anchored to nothing, and the one that moved: 80 runs of zero variance on the
    scorer path against a three-anchor swing here, on identical rubric text. See
    `recruit_design_decisions.md` §7.
    """

    criterion_id: str
    criterion_name: str
    outcome: Outcome
    deciding_clause: Clause | None = None
    determination: str = ""
    internal_score: int
    route: str
    points: list[Point]

    model_config = {"arbitrary_types_allowed": True}

    @property
    def scored(self) -> bool:
        return self.outcome == "scored"

    @property
    def rubric_points(self) -> list[Point]:
        return [point for point in self.points if point.kind == "rubric"]

    @property
    def measurement_points(self) -> list[Point]:
        return [point for point in self.points if point.kind == "measurement"]

    @property
    def inventory_gaps(self) -> list[Point]:
        """The default, and the drill: has he a better instance, and if not that is the gap.

        These are the points that decline to guess at his history. Each one routes itself
        once he answers it — a better story found is board skill, an experience gone and got
        is the firefighter — which is why forking costs nothing.
        """
        return [point for point in self.points if point.improvement == "inventory"]

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
    def risks(self) -> list[Point]:
        """Nothing here is wrong. This is what would cost him if he took it to the next board.

        Kept out of `answer_gaps` deliberately. A risk names something *absent* from the
        answer, so presenting it as a fault tells a candidate he did badly at a thing he did
        not do — and it is attached to material that worked, which is the reverse of a gap.
        See scoring note 10.
        """
        return [point for point in self.points if point.improvement == "risk"]

    @property
    def worked(self) -> list[Point]:
        return [point for point in self.points if point.improvement == "none"]
