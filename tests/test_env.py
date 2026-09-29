"""Environment wrapper: turn budget, reward deltas, action safety, admin isolation."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
from app.env import ArtifactRelayEnv


@pytest.fixture
async def env() -> AsyncIterator[ArtifactRelayEnv]:
    e = ArtifactRelayEnv(in_process=True)
    await e.reset(seed=1)
    yield e
    await e.close()


async def test_reset_gives_clean_observation(env: ArtifactRelayEnv) -> None:
    obs = await env.reset(seed=5)
    assert obs["grade"]["score"] == 0
    assert obs["turns_left"] == env.turn_budget
    assert obs["seed"] == 5


async def test_first_reward_on_discovery(env: ArtifactRelayEnv) -> None:
    _obs, reward, terminated, _truncated, _info = await env.step({"action": "list_releases"})
    assert reward == 10 and not terminated


async def test_unknown_action_is_a_costly_noop(env: ArtifactRelayEnv) -> None:
    _obs, reward, terminated, _truncated, info = await env.step({"action": "nonsense"})
    assert reward == 0 and not terminated and info["turns"] == 1


async def test_budget_truncates_the_episode(env: ArtifactRelayEnv) -> None:
    truncated = False
    for _ in range(env.turn_budget):
        _obs, _r, _t, truncated, _i = await env.step({"action": "root"})
    assert truncated


async def test_agent_requests_cannot_reach_the_internal_channel(env: ArtifactRelayEnv) -> None:
    obs, *_ = await env.step({"action": "http_get", "path": "/_internal/status"})
    assert obs["status"] == 403
    obs, *_ = await env.step({"action": "http_post", "path": "/_internal/reset", "json": {}})
    assert obs["status"] == 403


async def test_http_actions_reject_non_local_paths(env: ArtifactRelayEnv) -> None:
    for path in ("http://evil.example/x", "//evil.example/x", "health"):
        obs, *_ = await env.step({"action": "http_get", "path": path})
        assert obs["ok"] is False and "absolute path" in obs["error"]


async def test_b64_round_trip_and_errors(env: ArtifactRelayEnv) -> None:
    obs, *_ = await env.step({"action": "b64", "op": "encode", "data": '{"a":1}'})
    encoded = obs["body"]["result"]
    assert "=" not in encoded
    obs, *_ = await env.step({"action": "b64", "op": "decode", "data": encoded})
    assert obs["body"]["result"] == '{"a":1}'

    obs, *_ = await env.step({"action": "b64", "op": "decode", "data": "!!!"})
    assert obs["ok"] is False
    obs, *_ = await env.step({"action": "b64", "op": "shout", "data": "x"})
    assert obs["ok"] is False
