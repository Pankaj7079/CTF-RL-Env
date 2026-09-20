"""The deterministic reference solver solves the challenge in-process."""

from __future__ import annotations

from app.env import ArtifactRelayEnv
from solver.reference_solution import solve


async def test_reference_solver_solves() -> None:
    env = ArtifactRelayEnv(in_process=True)
    try:
        obs = await solve(env)
    finally:
        await env.close()
    assert obs["grade"]["solved"] is True
    assert obs["grade"]["score"] == 100
    assert obs["turns_used"] <= 16
