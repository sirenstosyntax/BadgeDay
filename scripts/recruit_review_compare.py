"""Compare the SME's blind scores against what the anchors produce.

    python scripts/recruit_review_compare.py

Reads the filled-in `reviews/c3-scoring-exercise.md`, runs the critique pipeline over the
same answers, and reports where the two agree and where they do not.

**A divergence is a finding about the rubric, not about either party.** The anchors were
drafted from published sources by something that has never sat a panel; where they disagree
with a fire captain the presumption is that the anchor is wrong. The output is therefore a
list of clauses to rewrite, ordered by how far apart the two readings are.

Agreement is weaker evidence than it looks and the report says so. Ten answers is a small
set, the answers were written by the same party that drafted the anchors, and an anchor can
be agreed with here and still be wrong about a candidate nobody thought to write.

## Blind scores and revisions are two different records

The ```scores block is the SME's **blind** judgment — scored with no rubric in front of him,
which is the whole reason the exercise is worth anything. **It is never edited.** Editing it
to match a later opinion would destroy the one property that makes it evidence.

An SME can still change his mind, and on 2026-08-10 he did: F was recorded 5 blind, and after
the anchor rulings he read it as a strong 4. Without somewhere to put that, this script
compares the pipeline against a superseded position and reports the *intended* outcome as a
divergence — F coming back 4 would print as a clause to rewrite, which is backwards.

So a second ```scores-revised block holds later rulings. Comparison runs against the revised
value where one exists; the blind score is still printed beside it, because a ref whose score
moved is a different kind of result from one that never did, and the report should not be able
to hide which is which.
"""

import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from anthropic import Anthropic

from app.config import get_settings
from app.critique import rubric as rubric_module
from app.critique.critiquer import critique_answer
from app.critique.review_set import ANSWERS, QUESTION, by_ref

EXERCISE = Path("reviews/c3-scoring-exercise.md")
POOL_SIZE = 4

_SCORE_LINE = re.compile(r"^\s*([A-K])\s*=\s*(.*?)\s*$", re.I)


def parse_block(text: str, name: str) -> dict[str, tuple[str, str]]:
    """Pull `REF = score, optional note` out of a named fenced block."""
    block = re.search(rf"```{name}\n(.*?)```", text, re.S)
    if block is None:
        return {}

    scores: dict[str, tuple[str, str]] = {}
    for line in block.group(1).splitlines():
        match = _SCORE_LINE.match(line)
        if not match or not match.group(2):
            continue
        raw = match.group(2)
        # "3, felt like a 2 on the closing line" -> ("3", "felt like a 2 ...")
        value, _, note = raw.partition(",")
        scores[match.group(1).upper()] = (value.strip().lower(), note.strip())
    return scores


def parse_scores(text: str) -> dict[str, tuple[str, str]]:
    """The blind scores. Required — without them there is no exercise."""
    scores = parse_block(text, "scores")
    if not scores:
        raise SystemExit(f"{EXERCISE} has no ```scores block — regenerate the exercise")
    return scores


def parse_revisions(text: str) -> dict[str, tuple[str, str]]:
    """Later SME rulings that supersede a blind score. Optional, and usually empty.

    Kept apart from the blind block rather than merged into it: the blind score is evidence
    *because* it was given without a rubric in view, and overwriting it with a later opinion
    would spend that property to save a line of parsing.
    """
    return parse_block(text, "scores-revised")


def normalise(value: str) -> str:
    value = value.strip().lower().rstrip(".")
    if value in {"na", "n/a", "not assessable", "unassessable"}:
        return "not assessable"
    if value in {"nans", "not answered", "no answer", "unanswered"}:
        return "not answered"
    return value


def pipeline_verdict(outcome) -> tuple[str, str]:
    """What the anchors produced, as a comparable value plus the clause that decided it."""
    critique = outcome.critique
    if critique is None:
        return "FAILED", ""
    # The real determination, not an inference from point order. This used to read
    # `points[0].clause` — the clause the first point happened to cite — so every
    # "the clause that decided it" in every report before 2026-07-29 named an arbitrary
    # clause, and the divergence-to-rewrite loop was aimed by it. See §7.
    decided_by = critique.deciding_clause.clause_id if critique.deciding_clause else ""
    if critique.outcome != "scored":
        return critique.outcome.replace("_", " "), decided_by
    # The route already carries its own digit — "4A", not "A" — so appending it to the
    # score produced "44a" and reported false divergences on every answer with a route.
    if critique.route in ("4A", "4B"):
        return critique.route.lower(), decided_by
    return str(critique.internal_score), decided_by


def agrees(mine: str, theirs: str) -> bool:
    if mine == "?":
        return False
    if mine == theirs:
        return True
    # "4" agrees with "4a"/"4b" — the reviewer declined to record a route, not disagreed.
    return mine.rstrip("ab") == theirs.rstrip("ab") and mine.rstrip("ab").isdigit()


def main() -> None:
    if not EXERCISE.exists():
        raise SystemExit(f"{EXERCISE} not found — run scripts/recruit_review_exercise.py first")

    text = EXERCISE.read_text()
    blind = parse_scores(text)
    revised = parse_revisions(text)

    # Comparison runs against the current SME position; the blind score stays visible beside
    # any ref that moved. Without this the script measures the pipeline against a superseded
    # opinion and calls the intended answer a divergence.
    scores = {**blind, **revised}

    missing = [a.ref for a in ANSWERS if a.ref not in scores]
    if missing:
        print(f"note: not yet scored — {', '.join(missing)}\n")
    if revised:
        moved = ", ".join(
            f"{ref} {blind.get(ref, ('—', ''))[0]} → {revised[ref][0]}" for ref in sorted(revised)
        )
        print(f"note: comparing against revised rulings — {moved}\n")

    settings = get_settings()
    if not settings.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set — check .env")
    client = Anthropic(api_key=settings.anthropic_api_key)
    rubric = rubric_module.load("c3")

    refs = [ref for ref in scores]

    def run(ref: str):
        return ref, critique_answer(
            rubric=rubric,
            question=QUESTION,
            transcript=by_ref(ref).transcript,
            client=client,
            settings=settings,
        )

    with ThreadPoolExecutor(max_workers=POOL_SIZE) as pool:
        results = dict(pool.map(run, refs))

    print(f"{'':3} {'you':>16}   {'anchors':<16} {'':4} decided by")
    print("-" * 78)

    divergences: list[tuple[str, str, str, str, str]] = []
    failures: list[tuple[str, str]] = []
    for ref in sorted(results):
        mine, note = scores[ref]
        mine = normalise(mine)
        theirs, clause = pipeline_verdict(results[ref])
        # An answer that produced no critique is not a disagreement about a clause, and the
        # 2026-08-10 run printed two of them under "these are the clauses to rewrite" — which
        # is the same false-divergence failure `app/llm_output.py` was written to stop, one
        # layer up. Counted separately, and it does not name a clause because there isn't one.
        if theirs == "FAILED":
            failures.append((ref, mine))
            print(f"{ref:3} {mine:>16}   {'FAILED':<16} !!   (no critique produced)")
            continue

        ok = agrees(mine, theirs)
        mark = "  " if ok else "<>"
        shown = f"{mine} (blind {normalise(blind[ref][0])})" if ref in revised else mine
        print(f"{ref:3} {shown:>16}   {theirs:<16} {mark}   {clause}")
        if note:
            print(f"{'':3} {'':>16}   note: {note}")
        if not ok:
            divergences.append((ref, mine, theirs, clause, note))

    print("\n" + "=" * 78)

    if failures:
        print(
            f"{len(failures)} answer(s) produced no critique: "
            f"{', '.join(ref for ref, _ in failures)}.\n"
            "**Not a rubric finding.** The pipeline failed on these, so the anchors were never\n"
            "asked. Read the logged failure, fix it, and re-run before reading anything below —\n"
            "a set with holes in it understates agreement and overstates nothing.\n"
        )

    scored = len(results) - len(failures)
    if not divergences:
        print(f"No divergences across the {scored} answer(s) that produced a critique.")
    else:
        print(f"{len(divergences)} divergence(s) of {scored} scored — the clauses to rewrite.\n")
        for ref, mine, theirs, clause, note in divergences:
            probe = by_ref(ref).probes
            print(f"  {ref}: you said {mine}, the anchors said {theirs}")
            print(f"     written to probe: {probe}")
            if clause:
                print(f"     the clause that decided it: {clause}")
            if note:
                print(f"     your note: {note}")
            print()

    print(
        "Agreement is weaker evidence than it looks: ten answers, written by the same party\n"
        "that drafted the anchors, so a clause can be agreed with here and still be wrong\n"
        "about a candidate nobody thought to write. Divergence is the reliable signal."
    )
    # A failure is not a pass. Exiting 0 on a run with holes in it would let a set re-run go
    # green in CI while two answers were never scored.
    return 0 if not divergences and not failures else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
