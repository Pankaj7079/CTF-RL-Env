"""The reference solver solves every instance within the turn budget."""

from __future__ import annotations

import pytest
from app.env import CTFRLEnv
from solver.reference_solution import solve


@pytest.mark.parametrize("seed", range(8))
async def test_reference_solver_solves(seed: int) -> None:
    env = CTFRLEnv(in_process=True)
    try:
        obs = await solve(env, seed=seed)
    finally:
        await env.close()
    assert obs["grade"]["solved"] is True
    assert obs["grade"]["score"] == 100
    assert 2 < obs["turns_used"] <= env.turn_budget
