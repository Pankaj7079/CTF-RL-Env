"""Measure the numbers the assignment asks for and print them as Markdown.

    uv run python -m scripts.calibrate

1. Reliability: the deterministic reference solver on 16 different instances.
2. Difficulty proxy: a seeded scripted agent. Its solve rate depends on two
   probabilities set by hand, so a small sweep shows how much they matter.
"""

from __future__ import annotations

import argparse
import asyncio
import math
import statistics
import time

from agents.stochastic_agent import RolloutResult, StochasticAgent
from app.env import ArtifactRelayEnv
from solver.reference_solution import solve

P_WANDER = 0.3
P_INSIGHT = 0.25
SOLVE_TARGET = 0.60
MIN_ROLLOUTS = 16
RELIABILITY_TARGET = 14
SOLVE_TIME_LIMIT_S = 300


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion."""
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def rate_with_ci(successes: int, n: int) -> str:
    lo, hi = wilson(successes, n)
    return f"{successes / n:.0%} (95% CI {lo:.0%}-{hi:.0%})"


async def reliability(runs: int) -> list[dict]:
    """Run the reference solver once per seed and record outcome and wall-clock time."""
    env = ArtifactRelayEnv(in_process=True)
    rows = []
    try:
        for seed in range(runs):
            start = time.perf_counter()
            obs = await solve(env, seed=seed)
            rows.append(
                {
                    "seed": seed,
                    "solved": obs["grade"]["solved"],
                    "score": obs["grade"]["score"],
                    "turns": obs["turns_used"],
                    "seconds": round(time.perf_counter() - start, 3),
                }
            )
    finally:
        await env.close()
    return rows


async def rollouts(runs: int, p_wander: float, p_insight: float) -> list[RolloutResult]:
    """Seeded scripted-agent episodes on instances 0..runs-1."""
    env = ArtifactRelayEnv(in_process=True)
    try:
        return [await StochasticAgent(seed, p_wander, p_insight).run(env) for seed in range(runs)]
    finally:
        await env.close()


def solved_count(results: list[RolloutResult]) -> int:
    return sum(r.solved for r in results)


def mean_turns(results: list[RolloutResult]) -> str:
    turns = [r.turns_used for r in results if r.solved]
    return f"{statistics.mean(turns):.1f}" if turns else "-"


async def main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate Artifact Relay.")
    parser.add_argument("--runs", type=int, default=16, help="rollouts for the headline tables")
    parser.add_argument("--sweep-runs", type=int, default=100, help="rollouts per sweep row")
    parser.add_argument("--p-wander", type=float, default=P_WANDER)
    parser.add_argument("--p-insight", type=float, default=P_INSIGHT)
    args = parser.parse_args()

    rel = await reliability(args.runs)
    ok = sum(r["solved"] for r in rel)
    slowest = max(r["seconds"] for r in rel)
    shortest = min(r["turns"] for r in rel)
    print(f"## Reliability: reference solver, {args.runs} instances\n")
    print("| Seed | Solved | Score | Turns | Seconds |\n|---:|:---:|---:|---:|---:|")
    for r in rel:
        print(
            f"| {r['seed']} | {'yes' if r['solved'] else 'NO'} | {r['score']} | "
            f"{r['turns']} | {r['seconds']} |"
        )
    print(
        f"\n{ok}/{len(rel)} solved, {shortest}-{max(r['turns'] for r in rel)} turns, "
        f"slowest {slowest}s.\n"
    )

    proxy = await rollouts(args.runs, args.p_wander, args.p_insight)
    proxy_ok = solved_count(proxy)
    print(
        f"## Scripted agent: {args.runs} rollouts, p_wander={args.p_wander}, "
        f"p_insight={args.p_insight}\n"
    )
    print("| Seed | Solved | Turns | Reward | Highest stage | Outcome |")
    print("|---:|:---:|---:|---:|:---|:---|")
    for i, r in enumerate(proxy):
        print(
            f"| {i} | {'yes' if r.solved else 'no'} | {r.turns_used} | {r.reward} | "
            f"{r.highest_stage or '-'} | {r.failure_reason} |"
        )
    print(
        f"\nSolve rate {rate_with_ci(proxy_ok, args.runs)}, "
        f"mean turns when solved {mean_turns(proxy)}.\n"
    )

    print(f"## Sensitivity to p_insight ({args.sweep_runs} rollouts per row)\n")
    print("| p_insight | Solve rate | Mean turns when solved |\n|---:|:---|---:|")
    for p in (0.10, 0.25, 0.50, 1.00):
        results = await rollouts(args.sweep_runs, args.p_wander, p)
        print(
            f"| {p:.2f} | {rate_with_ci(solved_count(results), args.sweep_runs)} "
            f"| {mean_turns(results)} |"
        )

    checks = [
        (
            ok >= RELIABILITY_TARGET and slowest < SOLVE_TIME_LIMIT_S,
            f"reliability {ok}/{len(rel)} (need >= {RELIABILITY_TARGET}), "
            f"slowest {slowest}s (need < {SOLVE_TIME_LIMIT_S}s)",
        ),
        (shortest > 2, f"not trivial: shortest solve {shortest} turns (need > 2)"),
        (
            args.runs >= MIN_ROLLOUTS and proxy_ok / args.runs >= SOLVE_TARGET,
            f"difficulty band: {proxy_ok / args.runs:.0%} over {args.runs} rollouts "
            f"(need >= {SOLVE_TARGET:.0%} over >= {MIN_ROLLOUTS})",
        ),
    ]
    print("\n## Targets\n")
    for passed, text in checks:
        print(f"- {'PASS' if passed else 'FAIL'}: {text}")
    return 0 if all(passed for passed, _ in checks) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
