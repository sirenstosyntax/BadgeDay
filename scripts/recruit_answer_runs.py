"""Run one review-set answer through the shipping critique path, repeatedly.

    python scripts/recruit_answer_runs.py F --runs 1 --show
    python scripts/recruit_answer_runs.py E K --runs 5
    python scripts/recruit_answer_runs.py --all --runs 5

The named tool of the 2026-08-06 calibration review, which had been run without being
committed. It exists because the other two harnesses answer different questions:

- `recruit_noise_floor.py` measures the **scorer** prompt, which asks for a score and the
  deciding criterion and nothing else. `recruit_design_decisions.md` §7 records what that
  cost — 80 runs of zero variance there against a three-anchor swing on the path that
  actually ships.
- `recruit_review_compare.py` runs the **whole set once** and reports agreement with the
  SME's blind scores. It answers "where do we disagree", not "does this answer sit still".

This one is the narrow instrument: one answer, `critique_answer`, N times, with the
critique itself printable. That is what a calibration follow-up needs — the earlier finding
on answer F was only trustworthy because it was six observations rather than one, and a
revision is only shown to have worked if the rerun says so more than once.

**One run is one observation, and the pipeline moves.** `--runs 1` is for reading a
critique, not for concluding anything about the outcome. The summary says so when n is 1.

The answers are synthetic. No real candidate is described.
"""

import argparse
import statistics
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from anthropic import Anthropic

from app.config import get_settings
from app.critique import rubric as rubric_module
from app.critique.cli import render_critique
from app.critique.critiquer import critique_answer
from app.critique.review_set import ANSWERS, QUESTION, by_ref

POOL_SIZE = 4

# The review set was written against Criterion 3. Kept as a constant rather than an option
# so the script cannot quietly run c2 anchors over c3 answers.
RUBRIC_ID = "c3"


def verdict(outcome) -> str:
    """The comparable value, on the same rules `recruit_review_compare.py` uses."""
    critique = outcome.critique
    if critique is None:
        return "FAILED"
    if critique.outcome != "scored":
        return critique.outcome.replace("_", " ")
    if critique.route in ("4A", "4B"):
        return critique.route
    return str(critique.internal_score)


def numeric(value: str) -> int | None:
    """The anchor as a number, for spread. Route tags collapse; non-scores are not zeros."""
    head = value.rstrip("AB")
    return int(head) if head.isdigit() else None


def run_answer(ref: str, runs: int, show: bool, rubric, client, settings) -> None:
    answer = by_ref(ref)
    print(f"\n{'=' * 78}\nanswer {ref} — {runs} run(s)\n{'=' * 78}")

    def once(_):
        return critique_answer(
            rubric=rubric,
            question=QUESTION,
            transcript=answer.transcript,
            client=client,
            settings=settings,
        )

    # One first, so the rest read the cached rubric rather than all missing together.
    outcomes = [once(0)]
    if runs > 1:
        with ThreadPoolExecutor(max_workers=POOL_SIZE) as pool:
            outcomes += list(pool.map(once, range(runs - 1)))

    verdicts = [verdict(o) for o in outcomes]
    dist = Counter(verdicts)
    print(f"  distribution : {dict(sorted(dist.items()))}")

    scores = [n for n in (numeric(v) for v in verdicts) if n is not None]
    if len(scores) > 1:
        spread = max(scores) - min(scores)
        print(f"  spread       : {spread} anchor(s)   sigma {statistics.pstdev(scores):.2f}")
        if spread >= 1:
            print("  a divergence smaller than this spread is not readable — §7")
    elif runs == 1:
        print("  one run is one observation; the pipeline moves by up to two anchors — §7")

    print("\n  the determination each distinct outcome rested on:")
    seen: set[str] = set()
    for value, outcome in zip(verdicts, outcomes, strict=True):
        if value in seen or outcome.critique is None:
            continue
        seen.add(value)
        clause = outcome.critique.deciding_clause
        clause_id = clause.clause_id if clause else "unanchored"
        print(f"    [{value}] {clause_id}: {outcome.critique.determination}")

    failures = [o.failure for o in outcomes if o.failure]
    for failure in failures:
        print(f"  FAILED: {failure}")

    if show:
        for index, outcome in enumerate(outcomes, start=1):
            if outcome.critique is None or not outcome.critique.points:
                continue
            print(f"\n{'-' * 78}\nrun {index} of {len(outcomes)}")
            for rejection in outcome.rejections:
                print(f"  rejected [{rejection.code}] {rejection.detail}")
            render_critique(outcome.critique, RUBRIC_ID in rubric_module.DRAFT_RUBRICS)

    # What this answer was written to probe, printed last: it is the reviewer's frame, and
    # showing it above the critique would tell a reader where to land before he has read it.
    print(f"\n  ({ref} probes: {answer.probes})")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    refs = [a.ref for a in ANSWERS]
    parser.add_argument("refs", nargs="*", metavar="REF", help=f"one of {', '.join(refs)}")
    parser.add_argument("--runs", type=int, default=5, help="runs per answer (default 5)")
    parser.add_argument("--all", action="store_true", help="every answer in the review set")
    parser.add_argument("--show", action="store_true", help="print each critique in full")
    args = parser.parse_args()

    wanted = refs if args.all else [ref.upper() for ref in args.refs]
    if not wanted:
        parser.error("name at least one answer, or pass --all")
    unknown = [ref for ref in wanted if ref not in refs]
    if unknown:
        raise SystemExit(f"unknown answer(s) {unknown}; choose from {refs}")
    if args.runs < 1:
        raise SystemExit("--runs must be at least 1")

    settings = get_settings()
    if not settings.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set — check .env")

    client = Anthropic(api_key=settings.anthropic_api_key)
    rubric = rubric_module.load(RUBRIC_ID)

    print(f"rubric: {rubric.name}  ({len(rubric.clauses)} citable clauses)")
    print(f"model : {settings.generation_model}, effort={settings.generation_effort}")
    print("path  : critique_answer — the one that ships, not the scorer prompt")

    for ref in wanted:
        run_answer(ref, args.runs, args.show, rubric, client, settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
