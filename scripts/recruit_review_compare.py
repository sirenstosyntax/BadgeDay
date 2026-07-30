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


def parse_scores(text: str) -> dict[str, tuple[str, str]]:
    """Pull `REF = score, optional note` out of the ```scores block."""
    block = re.search(r"```scores\n(.*?)```", text, re.S)
    if block is None:
        raise SystemExit(f"{EXERCISE} has no ```scores block — regenerate the exercise")

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

    scores = parse_scores(EXERCISE.read_text())
    if not scores:
        raise SystemExit(f"no scores filled in yet in {EXERCISE}")

    missing = [a.ref for a in ANSWERS if a.ref not in scores]
    if missing:
        print(f"note: not yet scored — {', '.join(missing)}\n")

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

    divergences = []
    for ref in sorted(results):
        mine, note = scores[ref]
        mine = normalise(mine)
        theirs, clause = pipeline_verdict(results[ref])
        ok = agrees(mine, theirs)
        mark = "  " if ok else "<>"
        print(f"{ref:3} {mine:>16}   {theirs:<16} {mark}   {clause}")
        if note:
            print(f"{'':3} {'':>16}   note: {note}")
        if not ok:
            divergences.append((ref, mine, theirs, clause, note))

    print("\n" + "=" * 78)
    if not divergences:
        print("No divergences on this set.")
    else:
        print(f"{len(divergences)} divergence(s) — these are the clauses to rewrite.\n")
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
    return 0 if not divergences else 1


if __name__ == "__main__":
    sys.exit(main() or 0)
