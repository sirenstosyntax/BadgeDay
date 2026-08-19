"""Rubrics, and the clauses a critique point is allowed to cite.

Promote's verification asks whether a question is grounded in the section it cites, and
can ask it because sections have numbers. Recruit needs the same thing and has to build
it: a critique point must name the clause it came from, so the clauses need names.

They are parsed out of the rubric markdown rather than maintained separately, because a
list of clause IDs kept beside the rubric would drift from it silently — and a gate that
checks against a stale list is worse than no gate, since it still passes.

Two clause kinds are citable:

- **Anchors** — `### 3 — Says the right things` and the lettered routes inside level 4,
  giving `anchor.3` and `anchor.4A`.
- **Scoring notes** — `**2. The behavioural frame**`, giving `note.2`.

Qualified by criterion, so a point cites `c3.anchor.2`. Prose between the headings is not
citable on its own; it is the body of the clause it sits under.

Only the region between the `scorer:start` and `scorer:end` markers is read. Authorship
banners and provenance live outside it — a draft rubric must not be scored differently
for announcing that it is a draft, and a model must not be able to cite the provenance
section as grounds for a critique point.
"""

import re
from dataclasses import dataclass
from pathlib import Path

SCORER_START = "<!-- scorer:start"
SCORER_END = "<!-- scorer:end -->"

# `### 5 — Other people are real...` / `### 4 — Strong on one axis...`
_ANCHOR_RE = re.compile(r"^###\s+(\d)\s*[—\-–]\s*(.+?)\s*$", re.M)
# `**4A — Wants the crew; rough edges.**`
_ROUTE_RE = re.compile(r"^\*\*(\d[A-Z])\s*[—\-–]\s*(.+?)\.?\*\*\s*$", re.M)
# `**3. Some candidates have no team history...**`
_NOTE_RE = re.compile(r"^\*\*(\d+)\.\s+(.+?)\*\*\s*$", re.M)


@dataclass(frozen=True)
class Clause:
    """One citable unit of a rubric."""

    clause_id: str
    kind: str  # "anchor" | "note"
    label: str

    def display(self) -> str:
        return f"{self.clause_id} — {self.label}"


@dataclass(frozen=True)
class Rubric:
    """A criterion, its scorer-visible text, and the clauses a point may cite."""

    criterion_id: str
    name: str
    text: str
    clauses: tuple[Clause, ...]

    @property
    def clause_ids(self) -> frozenset[str]:
        return frozenset(clause.clause_id for clause in self.clauses)

    def clause(self, clause_id: str) -> Clause | None:
        for candidate in self.clauses:
            if candidate.clause_id == clause_id:
                return candidate
        return None

    def catalogue(self) -> str:
        """The citable clauses, listed for the model. This is the whole allowed vocabulary."""
        return "\n".join(f"- {clause.display()}" for clause in self.clauses)


def scorer_region(text: str) -> str:
    """The part of a rubric a model is allowed to see."""
    if SCORER_START not in text or SCORER_END not in text:
        raise ValueError("rubric is missing its scorer:start / scorer:end markers")
    body = text.split(SCORER_START, 1)[1].split(SCORER_END, 1)[0]
    return body.split("-->", 1)[1].strip()


def parse_clauses(criterion_id: str, region: str) -> tuple[Clause, ...]:
    """Extract citable clauses from a rubric's scorer region, in document order."""
    found: list[tuple[int, Clause]] = []

    for match in _NOTE_RE.finditer(region):
        label = match.group(2).rstrip(".")
        found.append(
            (match.start(), Clause(f"{criterion_id}.note.{match.group(1)}", "note", label))
        )

    for match in _ANCHOR_RE.finditer(region):
        found.append(
            (
                match.start(),
                Clause(f"{criterion_id}.anchor.{match.group(1)}", "anchor", match.group(2)),
            )
        )

    for match in _ROUTE_RE.finditer(region):
        found.append(
            (
                match.start(),
                Clause(f"{criterion_id}.anchor.{match.group(1)}", "anchor", match.group(2)),
            )
        )

    # Document order keeps the catalogue readable, and de-duplication guards against a
    # heading that matches two patterns.
    seen: set[str] = set()
    ordered: list[Clause] = []
    for _, clause in sorted(found, key=lambda pair: pair[0]):
        if clause.clause_id in seen:
            continue
        seen.add(clause.clause_id)
        ordered.append(clause)
    return tuple(ordered)


def load_rubric(criterion_id: str, path: Path, name: str) -> Rubric:
    """Read a rubric from disk and parse its citable clauses."""
    region = scorer_region(path.read_text())
    clauses = parse_clauses(criterion_id, region)
    if not clauses:
        raise ValueError(f"{path} yielded no citable clauses; check its heading format")
    return Rubric(criterion_id=criterion_id, name=name, text=region, clauses=clauses)


# The rubrics that exist. Criterion 3 is a draft and is marked as such wherever a human
# sees its output; the pipeline treats both alike, because the gate's job is to check that
# a point is anchored, not to judge whether the anchor is any good.
RUBRIC_FILES = {
    "c2": (Path("recruit_rubric_c2_motivation.md"), "Criterion 2 — Motivation & Preparation"),
    "c3": (Path("recruit_rubric_c3_teamwork.md"), "Criterion 3 — Teamwork & Interpersonal"),
}

DRAFT_RUBRICS = frozenset({"c3"})


def available() -> list[str]:
    return sorted(RUBRIC_FILES)


def _package_root() -> Path:
    """Repo root on a laptop, /app in the image. Never CWD — Azure WORKDIR is /app."""
    return Path(__file__).resolve().parents[2]


def load(criterion_id: str, root: Path | None = None) -> Rubric:
    if criterion_id not in RUBRIC_FILES:
        raise KeyError(f"unknown rubric {criterion_id!r}; choose from {available()}")
    relative, name = RUBRIC_FILES[criterion_id]
    path = (root if root is not None else _package_root()) / relative
    return load_rubric(criterion_id, path, name)
