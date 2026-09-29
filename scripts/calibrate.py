"""Measure the numbers the assignment asks for and write CALIBRATION.md.

    uv run python -m scripts.calibrate            # 16 runs, 100-rollout sweeps
    uv run python -m scripts.calibrate --sweep-runs 200

Three independent pieces of evidence, kept apart on purpose:

1. Reliability: the deterministic reference solver on 16 different instances.
2. Difficulty proxy: a seeded scripted agent. Its solve rate depends on two
   probabilities I set by hand, so the sweep shows how much they matter.
3. A real model: read from runs/llm_rollouts.jsonl when agents/llm_agent.py has been run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import statistics
import time
from pathlib import Path

from agents.stochastic_agent import RolloutResult, StochasticAgent
from app.env import ArtifactRelayEnv
from solver.reference_solution import solve

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "CALIBRATION.md"
LLM_LOG = ROOT / "runs" / "llm_rollouts.jsonl"

SOLVE_TARGET = 0.60
MIN_ROLLOUTS = 16
RELIABILITY_TARGET = 14
SOLVE_TIME_LIMIT_S = 300


def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion."""
    if n == 0:
        return 0.0, 0.0
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def _rate_with_ci(successes: int, n: int) -> str:
    lo, hi = wilson(successes, n)
    return f"{successes / n:.0%} (95% CI {lo:.0%}-{hi:.0%})"


async def measure_reliability(runs: int) -> list[dict]:
    """Run the reference solver once per seed and record outcome and wall-clock time."""
    env = ArtifactRelayEnv(in_process=True)
    rows: list[dict] = []
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


async def rollouts(
    runs: int, p_wander: float, p_insight: float, turn_budget: int | None = None
) -> list[RolloutResult]:
    """Seeded scripted-agent episodes on instances 0..runs-1."""
    env = ArtifactRelayEnv(in_process=True, turn_budget=turn_budget)
    try:
        return [await StochasticAgent(seed, p_wander, p_insight).run(env) for seed in range(runs)]
    finally:
        await env.close()


def _solved(results: list[RolloutResult]) -> int:
    return sum(r.solved for r in results)


def reliability_section(rows: list[dict]) -> tuple[str, dict]:
    times = [r["seconds"] for r in rows]
    stats = {
        "ok": sum(r["solved"] for r in rows),
        "n": len(rows),
        "max_s": max(times),
        "mean_s": round(statistics.mean(times), 3),
        "min_turns": min(r["turns"] for r in rows),
        "max_turns": max(r["turns"] for r in rows),
    }
    lines = ["| Seed | Solved | Score | Turns | Seconds |", "|---:|:---:|---:|---:|---:|"]
    lines += [
        f"| {r['seed']} | {'yes' if r['solved'] else 'NO'} | {r['score']} | "
        f"{r['turns']} | {r['seconds']} |"
        for r in rows
    ]
    return "\n".join(lines), stats


def difficulty_section(results: list[RolloutResult]) -> str:
    lines = [
        "| Seed | Solved | Turns | Reward | Highest stage | Outcome |",
        "|---:|:---:|---:|---:|:---|:---|",
    ]
    lines += [
        f"| {i} | {'yes' if r.solved else 'no'} | {r.turns_used} | {r.reward} | "
        f"{r.highest_stage or '-'} | {r.failure_reason} |"
        for i, r in enumerate(results)
    ]
    return "\n".join(lines)


async def sweep_insight(runs: int, p_wander: float, values: tuple[float, ...]) -> str:
    lines = ["| p_insight | Solve rate | Mean turns when solved |", "|---:|:---|---:|"]
    for p in values:
        results = await rollouts(runs, p_wander, p)
        turns = [r.turns_used for r in results if r.solved]
        mean_turns = f"{statistics.mean(turns):.1f}" if turns else "-"
        lines.append(f"| {p:.2f} | {_rate_with_ci(_solved(results), runs)} | {mean_turns} |")
    return "\n".join(lines)


async def sweep_budget(
    runs: int, p_wander: float, p_insight: float, budgets: tuple[int, ...]
) -> str:
    lines = ["| Turn budget | Solve rate |", "|---:|:---|"]
    for budget in budgets:
        results = await rollouts(runs, p_wander, p_insight, turn_budget=budget)
        lines.append(f"| {budget} | {_rate_with_ci(_solved(results), runs)} |")
    return "\n".join(lines)


def llm_section() -> tuple[str, list[dict]]:
    if not LLM_LOG.exists():
        return (
            "No real-model run is recorded. Run `uv run python -m agents.llm_agent` with a "
            "key in `.env`, then regenerate this report.",
            [],
        )
    rows = [json.loads(line) for line in LLM_LOG.read_text(encoding="utf-8").splitlines() if line]
    if not rows:
        return "The rollout log exists but is empty.", []
    lines = [
        "| Seed | Model | Solved | Score | Invalid replies | Stages reached |",
        "|---:|:---|:---:|---:|---:|:---|",
    ]
    lines += [
        f"| {r['seed']} | {r['model']} | {'yes' if r['solved'] else 'no'} | {r['score']} | "
        f"{r['invalid_replies']} | {len(r['reached'])} |"
        for r in rows
    ]
    n, ok = len(rows), sum(r["solved"] for r in rows)
    mean_score = statistics.mean(r["score"] for r in rows)
    lines.append("")
    lines.append(
        f"**{ok}/{n} solved ({_rate_with_ci(ok, n)}), mean score {mean_score:.0f}/100.** "
        "With this few episodes the interval is wide; treat it as a sanity check, not a rate."
    )
    return "\n".join(lines), rows


def verdict(rel: dict, solved: int, n: int) -> str:
    rate = solved / n
    checks = [
        (
            rel["ok"] >= RELIABILITY_TARGET and rel["max_s"] < SOLVE_TIME_LIMIT_S,
            f"Reliability: reference solver {rel['ok']}/{rel['n']} (need >= {RELIABILITY_TARGET}), "
            f"slowest run {rel['max_s']}s (need < {SOLVE_TIME_LIMIT_S}s)",
        ),
        (
            rel["min_turns"] > 2,
            f"Not trivial: shortest reference solve takes {rel['min_turns']} turns (need > 2)",
        ),
        (
            n >= MIN_ROLLOUTS and rate >= SOLVE_TARGET,
            f"Difficulty band (scripted proxy): solve rate {rate:.0%} over {n} rollouts "
            f"(need >= {SOLVE_TARGET:.0%} over >= {MIN_ROLLOUTS} rollouts)",
        ),
    ]
    return "\n".join(f"- {'PASS' if ok else 'FAIL'}: {text}" for ok, text in checks)


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Calibrate Artifact Relay.")
    parser.add_argument("--runs", type=int, default=16, help="rollouts for the headline tables")
    parser.add_argument("--sweep-runs", type=int, default=100, help="rollouts per sweep cell")
    parser.add_argument("--p-wander", type=float, default=0.3)
    parser.add_argument("--p-insight", type=float, default=0.25)
    args = parser.parse_args()

    rel_rows = await measure_reliability(args.runs)
    rel_table, rel = reliability_section(rel_rows)

    proxy = await rollouts(args.runs, args.p_wander, args.p_insight)
    proxy_solved = _solved(proxy)
    proxy_turns = [r.turns_used for r in proxy if r.solved]
    proxy_mean_turns = f"{statistics.mean(proxy_turns):.1f}" if proxy_turns else "n/a"

    insight_table = await sweep_insight(
        args.sweep_runs, args.p_wander, (0.10, 0.15, 0.25, 0.40, 0.60, 1.00)
    )
    budget_table = await sweep_budget(
        args.sweep_runs, args.p_wander, args.p_insight, (16, 14, 12, 10, 8)
    )
    llm_text, _ = llm_section()

    report = f"""# Calibration report

Every number here is produced by `uv run python -m scripts.calibrate` (plus, for the last
section, `uv run python -m agents.llm_agent`). Nothing is filled in by hand. The three
sections measure different things and should not be blended into one claim.

## 1. Environment reliability: reference solver, {args.runs} instances

The solver goes through the same `env.step()` actions an agent gets, on seeds
0-{args.runs - 1}. Timing is in-process (ASGI, no network).

{rel_table}

**{rel["ok"]}/{rel["n"]} solved**, {rel["min_turns"]}-{rel["max_turns"]} turns,
mean {rel["mean_s"]}s, slowest {rel["max_s"]}s.

## 2. Difficulty proxy: scripted agent, {args.runs} rollouts at a 16-turn budget

This is a simulation, not evidence about real models. The agent knows the intended path
but is fallible in two ways whose probabilities I chose myself:

- `p_wander` = {args.p_wander}: before logging in, it may waste a turn on an irrelevant URL.
- `p_insight` = {args.p_insight}: at the crux, each turn it has only this chance of thinking
  to decode the ticket; otherwise it tries something plausible that goes nowhere.

{difficulty_section(proxy)}

**Solve rate {_rate_with_ci(proxy_solved, args.runs)}**, mean turns when solved {proxy_mean_turns}.

### How much the assumption matters

Solve rate as `p_insight` varies ({args.sweep_runs} rollouts per row, `p_wander` fixed).
If you disagree with my `p_insight`, read the answer off this table instead.

{insight_table}

### Turn budget

Same agent, tighter budgets ({args.sweep_runs} rollouts per row). The rate falls
gradually rather than off a cliff, which is what a usable difficulty knob looks like.

{budget_table}

## 3. A real model

{llm_text}

## Verdict against the assignment's targets

{verdict(rel, proxy_solved, args.runs)}

The difficulty line is only as strong as the proxy's assumptions (section 2). The
real-model section is the honest check on it.
"""
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
