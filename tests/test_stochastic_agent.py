"""The scripted proxy agent: reproducible per seed, and its two knobs do what they claim."""

from __future__ import annotations

from agents.stochastic_agent import StochasticAgent
from app.env import CTFRLEnv


async def _run(seed: int, p_wander: float, p_insight: float):
    env = CTFRLEnv(in_process=True)
    try:
        return await StochasticAgent(seed, p_wander, p_insight).run(env)
    finally:
        await env.close()


async def test_same_seed_gives_the_same_episode() -> None:
    assert await _run(3, 0.3, 0.25) == await _run(3, 0.3, 0.25)


async def test_agent_that_always_sees_the_flaw_solves() -> None:
    for seed in range(4):
        result = await _run(seed, 0.0, 1.0)
        assert result.solved and result.reward == 100 and result.turns_used <= 16


async def test_agent_that_never_sees_the_flaw_stalls_before_the_redirect() -> None:
    result = await _run(0, 0.0, 0.0)
    assert not result.solved
    assert result.highest_stage == "preview_flow"
    assert result.turns_used == 16
