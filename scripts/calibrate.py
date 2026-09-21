"""Calibration harness — measure the numbers the assignment requires.

Two independent measurements, both fully offline and reproducible:

1. RELIABILITY (deterministic solver): run the golden path N times, record
   success and wall-clock time. Target: >= 14/16 successes, < 5 min each.

2. DIFFICULTY (stochastic reference agent): run N seeded rollouts at the 16-turn
   budget, record solve/turns/reward/failure-stage. Target: solve rate in the
   learnable band (>= 60% solved, i.e. < 40% failure; and not > 80% failure).

Results are written to CALIBRATION.md and printed. Numbers are whatever the runs
produce — nothing is hand-set.

Usage:
    uv run python scripts/calibrate.py --runs 16
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from pathlib import Path

from agents.stochastic_agent import RolloutResult, StochasticAgent
from app.env import ArtifactRelayEnv
from solver.reference_solution import solve

REPORT_PATH = Path(__file__).resolve().parents[1] / "CALIBRATION.md"


async def measure_reliability(runs: int) -> list[dict]:
    env = ArtifactRelayEnv(in_process=True)
    rows: list[dict] = []
    try:
        for i in range(1, runs + 1):
            t0 = time.perf_counter()
            obs = await solve(env)
            dt = time.perf_counter() - t0
            rows.append(
                {
                    "run": i,
                    "solved": obs["grade"]["solved"],
                    "score": obs["grade"]["score"],
                    "turns": obs["turns_used"],
                    "seconds": round(dt, 3),
                }
            )
    finally:
        await env.close()
    return rows


async def measure_difficulty(
    runs: int, p_wander: float, p_insight: float, turn_budget: int | None = None
) -> list[RolloutResult]:
    env = ArtifactRelayEnv(in_process=True, turn_budget=turn_budget)
    results: list[RolloutResult] = []
    try:
        for seed in range(runs):
            agent = StochasticAgent(seed=seed, p_wander=p_wander, p_insight=p_insight)
            results.append(await agent.run(env))
    finally:
        await env.close()
    return results


async def measure_curve(
    runs: int, p_wander: float, p_insight: float, budgets: tuple[int, ...]
) -> str:
    """Difficulty vs turn budget — shows the reward gradient as the task tightens."""

    lines = ["| Turn budget | Solve rate | Failure rate |", "|---:|---:|---:|"]
    for b in budgets:
        results = await measure_difficulty(runs, p_wander, p_insight, turn_budget=b)
        solved = sum(1 for r in results if r.solved)
        lines.append(f"| {b} | {solved / runs:.0%} | {(runs - solved) / runs:.0%} |")
    return "\n".join(lines)


def _fmt_reliability(rows: list[dict]) -> tuple[str, dict]:
    solved = sum(1 for r in rows if r["solved"])
    times = [r["seconds"] for r in rows]
    summary = {
        "successes": solved,
        "runs": len(rows),
        "max_seconds": max(times),
        "mean_seconds": round(statistics.mean(times), 3),
    }
    lines = ["| Run | Solved | Score | Turns | Seconds |", "|---:|:---:|---:|---:|---:|"]
    for r in rows:
        mark = "✅" if r["solved"] else "❌"
        lines.append(f"| {r['run']} | {mark} | {r['score']} | {r['turns']} | {r['seconds']} |")
    return "\n".join(lines), summary


def _fmt_difficulty(results: list[RolloutResult]) -> tuple[str, dict]:
    n = len(results)
    solved = sum(1 for r in results if r.solved)
    turns_solved = [r.turns_used for r in results if r.solved]
    rewards = [r.reward for r in results]
    fail_hist: dict[str, int] = {}
    for r in results:
        if not r.solved:
            fail_hist[r.failure_stage or "none"] = fail_hist.get(r.failure_stage or "none", 0) + 1
    summary = {
        "runs": n,
        "solved": solved,
        "solve_rate": round(solved / n, 3) if n else 0.0,
        "failure_rate": round((n - solved) / n, 3) if n else 0.0,
        "mean_turns_solved": round(statistics.mean(turns_solved), 2) if turns_solved else None,
        "median_turns_solved": statistics.median(turns_solved) if turns_solved else None,
        "mean_reward": round(statistics.mean(rewards), 2) if rewards else 0.0,
        "failure_stage_histogram": fail_hist,
    }
    lines = [
        "| Seed | Solved | Turns | Reward | Highest stage | Failure reason |",
        "|---:|:---:|---:|---:|:---|:---|",
    ]
    for i, r in enumerate(results):
        lines.append(
            f"| {i} | {'✅' if r.solved else '❌'} | {r.turns_used} | {r.reward} | "
            f"{r.highest_stage or '-'} | {r.failure_reason} |"
        )
    return "\n".join(lines), summary


def _verdict(rel: dict, diff: dict) -> str:
    ok_rel = rel["successes"] >= 14 and rel["max_seconds"] < 300
    ok_band = diff["failure_rate"] < 0.40 and diff["failure_rate"] <= 0.80
    return (
        f"- Reliability target (>=14/16 & <5min): **{'PASS' if ok_rel else 'REVIEW'}** "
        f"({rel['successes']}/{rel['runs']}, max {rel['max_seconds']}s)\n"
        f"- Difficulty band (solve>=60%, fail<40%): **{'PASS' if ok_band else 'REVIEW'}** "
        f"(solve {diff['solve_rate']:.0%}, fail {diff['failure_rate']:.0%})"
    )


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate Artifact Relay.")
    parser.add_argument("--runs", type=int, default=16)
    parser.add_argument("--p-wander", type=float, default=0.45)
    parser.add_argument("--p-insight", type=float, default=0.15)
    args = parser.parse_args()

    rel_rows = await measure_reliability(args.runs)
    rel_table, rel_summary = _fmt_reliability(rel_rows)
    diff_results = await measure_difficulty(args.runs, args.p_wander, args.p_insight)
    diff_table, diff_summary = _fmt_difficulty(diff_results)
    curve_table = await measure_curve(args.runs, args.p_wander, args.p_insight, (16, 12, 10, 8))

    rel_line = (
        f"**Summary:** {rel_summary['successes']}/{rel_summary['runs']} solved · "
        f"mean {rel_summary['mean_seconds']}s · max {rel_summary['max_seconds']}s."
    )
    diff_line = (
        f"**Summary:** solve rate {diff_summary['solve_rate']:.0%} · "
        f"failure rate {diff_summary['failure_rate']:.0%} · "
        f"mean turns (solved) {diff_summary['mean_turns_solved']} · "
        f"median {diff_summary['median_turns_solved']} · mean reward {diff_summary['mean_reward']}."
    )
    hist = diff_summary["failure_stage_histogram"]

    report = f"""# Calibration Report — Artifact Relay

_All numbers below are measured from actual runs of this repository, fully offline._

## 1. Environment reliability (deterministic reference solver)

Golden-path solver run {args.runs} times. Target: >= 14/16 successes, each < 5 min.

{rel_table}

{rel_line}

## 2. Difficulty band (stochastic reference agent)

Competent-but-imperfect agent (`p_wander={args.p_wander}`, `p_insight={args.p_insight}`),
{args.runs} seeded rollouts at a 16-turn budget. Target: solve >= 60% (failure < 40%).

{diff_table}

{diff_line}

Failure-stage histogram: `{hist}`

## 3. Difficulty curve (solve rate vs turn budget)

Same agent, varying the turn budget. Tightening the budget lowers the solve rate,
demonstrating a genuine difficulty gradient and reward signal (not a cliff).

{curve_table}

## 4. Verdict

{_verdict(rel_summary, diff_summary)}
"""
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
