"""Measure how stably the pipeline files a point as improving the answer or the candidate.

`recruit_design_decisions.md` §3 makes that distinction the load-bearing one: an answer gap
is something he can fix tonight by telling it differently, a development gap is something he
has to go and become. The first live run skewed hard toward *candidate* on one fixture, and
one run cannot say whether that is accurate diagnosis or the model reaching for the more
dramatic reading.

    python scripts/recruit_classification_spread.py
    python scripts/recruit_classification_spread.py c3/weak

**This measures consistency, not correctness** — the same caveat the score harness carries,
and it bites harder here. A distinction the model applies identically every time can still
be filed the wrong way every time, and no amount of agreement between runs would show it.
Only a fire captain reading the points can say whether a gap really is one a retelling would
close. What this can show is whether the *distinction itself* is well defined: a clause that
comes back "answer" half the time and "candidate" the other half is ambiguous as written,
and that is a defect in the rubric or the prompt rather than a judgment call.

Two things get reported, because they answer different questions:

- **Candidate share per run** — of the points that name a gap, what fraction say the fix is
  in his life rather than his telling. Spread across runs says whether the skew is real.
- **Per-clause split** — for each rubric clause, how the points citing it were filed. This
  is the diagnostic one. A clause that splits is a clause whose gap type is undecidable from
  the text, and it names itself.

Points recording something that worked are counted but excluded from the share, since they
assert no gap to classify.
"""

import statistics
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor

from anthropic import Anthropic

from app.config import get_settings
from app.critique import rubric as rubric_module
from app.critique.cli import FIXTURES, QUESTIONS
from app.critique.critiquer import critique_answer

POOL_SIZE = 4
# Below this, a clause's filing is treated as contested rather than settled.
STABLE_SHARE = 0.8
# Fewer gap labels than this and a "split" is arithmetic on a handful of points, not
# evidence of an ambiguous clause. Two labels out of three reads as 67% and means nothing.
MIN_CONTEST_N = 6

RUNS = [("c3", "weak", 20), ("c3", "off_topic", 10), ("c2", "weak", 10)]


def one_run(rubric, question, transcript, client, settings):
    outcome = critique_answer(
        rubric=rubric,
        question=question,
        transcript=transcript,
        client=client,
        settings=settings,
    )
    if outcome.critique is None:
        return None
    return {
        "points": [
            {
                "clause": point.clause.clause_id if point.clause else "metric",
                "label": point.clause.label if point.clause else "",
                "improvement": point.improvement,
                "observation": point.observation,
            }
            for point in outcome.critique.points
        ],
        "rejected": len(outcome.rejections),
        "attempts": outcome.attempts,
    }


def report(tag: str, results: list[dict]) -> None:
    runs = [r for r in results if r is not None]
    print(f"\n{'=' * 78}\n{tag} — {len(runs)} of {len(results)} runs returned a critique")
    if not runs:
        return

    shares, per_clause = [], defaultdict(Counter)
    totals = Counter()
    for run in runs:
        gaps = [p for p in run["points"] if p["improvement"] in ("answer", "candidate")]
        for point in run["points"]:
            totals[point["improvement"]] += 1
            per_clause[point["clause"]][point["improvement"]] += 1
        if gaps:
            shares.append(sum(p["improvement"] == "candidate" for p in gaps) / len(gaps))

    print(f"  points per run : {statistics.mean(len(r['points']) for r in runs):.1f} mean")
    print(f"  labels overall : {dict(totals)}")
    print(f"  rejected       : {sum(r['rejected'] for r in runs)} across all runs")

    if shares:
        print(
            f"  candidate share: mean {statistics.mean(shares):.0%}, "
            f"range {min(shares):.0%}-{max(shares):.0%}"
            + (f", sd {statistics.pstdev(shares):.2f}" if len(shares) > 1 else "")
        )

    # Contest is measured across the gap labels only. A clause that sometimes credits an
    # answer and sometimes faults it is not unstable — an anchor like "preparation is real
    # but stale" describes two true things about one answer, and reporting both is correct.
    # Flagging that as ambiguity is what produced a withdrawn recommendation to split it.
    print("\n  per-clause filing (contest measured across gap labels only):")
    contested = []
    for clause, counts in sorted(per_clause.items(), key=lambda kv: -sum(kv[1].values())):
        seen = sum(counts.values())
        gaps_only = {k: v for k, v in counts.items() if k != "none"}
        if not gaps_only:
            print(f"    {clause:<16} n={seen:<3} {dict(counts)}  credit only")
            continue
        gap_n = sum(gaps_only.values())
        top, top_n = Counter(gaps_only).most_common(1)[0]
        share = top_n / gap_n
        if share >= STABLE_SHARE:
            flag = ""
        elif gap_n < MIN_CONTEST_N:
            flag = f"   (split, but only {gap_n} gap labels — too few to read)"
        else:
            flag = "   <-- CONTESTED"
        print(f"    {clause:<16} n={seen:<3} {dict(counts)}  {top} {share:.0%}{flag}")
        if share < STABLE_SHARE and gap_n >= MIN_CONTEST_N:
            contested.append(clause)

    for clause in contested:
        print(f"\n  --- {clause}: what each filing says ---")
        for label in ("answer", "candidate"):
            example = next(
                (
                    p
                    for run in runs
                    for p in run["points"]
                    if p["clause"] == clause and p["improvement"] == label
                ),
                None,
            )
            if example:
                print(f"    [{label}] {example['observation'][:220]}")


def main() -> None:
    wanted = sys.argv[1:]
    plan = RUNS
    if wanted:
        chosen = {w for w in wanted}
        plan = [r for r in RUNS if f"{r[0]}/{r[1]}" in chosen]
        if not plan:
            raise SystemExit(f"nothing matched {wanted}; known: {[f'{a}/{b}' for a, b, _ in RUNS]}")

    settings = get_settings()
    if not settings.anthropic_api_key:
        raise SystemExit("ANTHROPIC_API_KEY is not set — check .env")
    client = Anthropic(api_key=settings.anthropic_api_key)

    print(f"scorer: {settings.generation_model}, effort={settings.generation_effort}")
    print("consistency, not correctness — a stable filing can still be the wrong filing")

    for criterion_id, fixture, n in plan:
        rubric = rubric_module.load(criterion_id)
        question = QUESTIONS[criterion_id]
        transcript = FIXTURES[criterion_id][fixture]

        with ThreadPoolExecutor(max_workers=POOL_SIZE) as pool:
            results = list(
                pool.map(
                    lambda _, r=rubric, q=question, tx=transcript: one_run(
                        r, q, tx, client, settings
                    ),
                    range(n),
                )
            )
        report(f"{criterion_id}/{fixture}", results)


if __name__ == "__main__":
    main()
