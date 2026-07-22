"""Question models.

Two distinct shapes, and the distinction is the whole design:

- **Drafts** are what the model emits. They are untrusted. A draft carries a
  `source_quote` — the span of the chunk the model claims supports its answer.
- **Questions** are what BadgeDay stores. A question has a `Citation` built from the
  chunk's own metadata, and carries no quote at all.

The model never authors a citation. It is given one chunk and asked to write questions
from it; the citation is then attached from that chunk's stored location. A citation
therefore cannot be wrong about *where* it points — only about whether the question is
genuinely supported there, which is what `source_quote` exists to prove.

`source_quote` is a verification artifact and is deliberately discarded after checking.
It is never stored and never displayed, because storing verbatim source text is what the
copyright constraint forbids.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.ingest.models import Chunk

QuestionType = Literal["multiple_choice", "true_false", "short_answer"]


class Citation(BaseModel):
    """Where a question came from. Built from chunk metadata, never from model output."""

    document_id: str
    chunk_id: str
    section_number: str | None
    section_title: str | None
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)

    @classmethod
    def from_chunk(cls, chunk: Chunk) -> "Citation":
        return cls(
            document_id=chunk.document_id,
            chunk_id=chunk.chunk_id,
            section_number=chunk.section_number,
            section_title=chunk.section_title,
            page_start=chunk.page_start,
            page_end=chunk.page_end,
        )

    def display(self) -> str:
        """The source reference shown to the candidate on review."""
        pages = (
            f"p. {self.page_start}"
            if self.page_start == self.page_end
            else f"pp. {self.page_start}–{self.page_end}"
        )
        if self.section_number and self.section_title:
            return f"§ {self.section_number} {self.section_title}, {pages}"
        if self.section_number:
            return f"§ {self.section_number}, {pages}"
        return pages


# --- Drafts: untrusted model output ------------------------------------------


class _DraftBase(BaseModel):
    stem: str = Field(min_length=1)
    source_quote: str = Field(
        min_length=1,
        description=(
            "The span of the provided section that supports the correct answer, copied "
            "exactly. Used to verify grounding, then discarded — never shown to anyone."
        ),
    )
    explanation: str = Field(
        min_length=1, description="Why the answer is correct, in original words."
    )


class DraftMultipleChoice(_DraftBase):
    type: Literal["multiple_choice"]
    options: list[str] = Field(min_length=3, max_length=5)
    correct_index: int = Field(ge=0)


class DraftTrueFalse(_DraftBase):
    type: Literal["true_false"]
    correct_answer: bool


class DraftShortAnswer(_DraftBase):
    type: Literal["short_answer"]
    model_answer: str = Field(min_length=1)


DraftQuestion = Annotated[
    DraftMultipleChoice | DraftTrueFalse | DraftShortAnswer,
    Field(discriminator="type"),
]


class DraftBatch(BaseModel):
    """The top-level shape the model is constrained to emit."""

    questions: list[DraftQuestion]


# --- Questions: verified and storable ----------------------------------------


class Question(BaseModel):
    """A question that passed verification. Safe to store and to show a candidate."""

    question_id: str
    type: QuestionType
    stem: str
    explanation: str
    citation: Citation

    # Multiple choice only.
    options: list[str] | None = None
    correct_index: int | None = None

    # True/false only.
    correct_answer: bool | None = None

    # Short answer only.
    model_answer: str | None = None
