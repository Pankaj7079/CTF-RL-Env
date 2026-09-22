# Environment wrapper: turn budget, reward deltas, and no-op safety.

from __future__ import annotations

from app.env import ArtifactRelayEnv


async def test_reset_gives_clean_observation() -> None:
    env = ArtifactRelayEnv(in_process=True)
    try:
        obs = await env.reset()
        assert obs["grade"]["score"] == 0
        assert obs["turns_left"] == env.turn_budget
    finally:
        await env.close()


async def test_unknown_action_is_safe_noop() -> None:
    env = ArtifactRelayEnv(in_process=True)
    try:
        await env.reset()
        obs, reward, terminated, truncated, info = await env.step({"action": "nonsense"})
        assert reward == 0 and not terminated
        assert info["turns"] == 1
    finally:
        await env.close()


async def test_first_reward_on_discovery() -> None:
    env = ArtifactRelayEnv(in_process=True)
    try:
        await env.reset()
        _obs, reward, _t, _tr, _i = await env.step({"action": "list_releases"})
        assert reward == 10  # app_discovery stage
    finally:
        await env.close()
