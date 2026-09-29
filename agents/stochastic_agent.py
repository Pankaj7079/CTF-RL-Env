from __future__ import annotations

import json
import random
import re
from dataclasses import dataclass, field
from typing import Any

from app.env import CTFRLEnv

from grader.grader import load_rubric

_WANDER_PATHS = ("/admin", "/api", "/status", "/artifacts/all", "/debug", "/flag")

_FAILURE_REASONS = {
    None: "never discovered the application interface",
    "app_discovery": "found the app but never logged in",
    "reviewer_session": "logged in but never used the preview flow",
    "preview_flow": "previewed a ticket but never redirected one",
    "ticket_redirect": "redirected a ticket but ran out of turns before the flag",
    "protected_artifact": "read restricted artifacts but ran out of turns before the flag",
}


@dataclass
class RolloutResult:
    solved: bool
    turns_used: int
    reward: int
    highest_stage: str | None
    failure_reason: str


@dataclass
class _Knowledge:
    """What the agent has learned so far, all from responses to its own actions."""

    discovered: bool = False
    logged_in: bool = False
    previewed: bool = False
    wandered: int = 0
    public_id: str | None = None
    untried: list[str] = field(default_factory=list)
    ticket: str | None = None
    payload: dict[str, Any] | None = None
    forged_ticket: str | None = None
    flag: str | None = None


class StochasticAgent:
    def __init__(self, seed: int, p_wander: float = 0.3, p_insight: float = 0.25) -> None:
        self.seed = seed
        self.rng = random.Random(seed)
        self.p_wander = p_wander
        self.p_insight = p_insight
        self._flag_re = re.compile(load_rubric().flag_regex)

    async def run(self, env: CTFRLEnv) -> RolloutResult:
        """Play one episode on the instance for this agent's seed."""
        user, password = env.reviewer_credentials()
        await env.reset(seed=self.seed)
        know = _Knowledge()
        total = 0
        terminated = truncated = False
        obs: dict[str, Any] = {}
        while not (terminated or truncated):
            action = self._next_action(know, user, password)
            obs, reward, terminated, truncated, _ = await env.step(action)
            total += reward
            self._learn(know, action, obs)

        grade = obs["grade"]
        return RolloutResult(
            solved=grade["solved"],
            turns_used=obs["turns_used"],
            reward=total,
            highest_stage=grade["highest_stage"],
            failure_reason="solved"
            if grade["solved"]
            else _FAILURE_REASONS.get(grade["highest_stage"], "unknown"),
        )

    def _next_action(self, k: _Knowledge, user: str, password: str) -> dict[str, Any]:
        if k.flag:
            return {"action": "submit_flag", "flag": k.flag}
        if k.forged_ticket:
            ticket, k.forged_ticket = k.forged_ticket, None
            return {"action": "relay", "ticket": ticket}
        if k.wandered < 2 and not k.logged_in and self.rng.random() < self.p_wander:
            k.wandered += 1
            return {"action": "http_get", "path": self.rng.choice(_WANDER_PATHS)}
        if not k.discovered:
            return {"action": "list_releases"}
        if not k.logged_in:
            return {"action": "login", "username": user, "password": password}
        if k.public_id is None:
            return {"action": "list_artifacts"}
        if k.ticket is None:
            return {"action": "mint", "artifact_id": k.public_id}
        if not k.previewed:
            return {"action": "relay", "ticket": k.ticket}

        # The crux: decode the ticket, then forge it toward each restricted artifact.
        if k.payload is not None and k.untried:
            k.payload["aid"] = k.untried.pop(0)
            forged = json.dumps(k.payload, separators=(",", ":"), sort_keys=True)
            return {"action": "b64", "op": "encode", "data": forged}
        if k.payload is None and self.rng.random() < self.p_insight:
            return {"action": "b64", "op": "decode", "data": k.ticket.partition(".")[0]}
        return self._distractor(k)

    def _distractor(self, k: _Knowledge) -> dict[str, Any]:
        """A plausible move that makes no progress."""
        choice = self.rng.choice(("mint_restricted", "relay_again", "guess_flag"))
        if choice == "mint_restricted" and k.untried:
            return {"action": "mint", "artifact_id": k.untried[0]}
        if choice == "guess_flag":
            return {"action": "submit_flag", "flag": "flag{not_the_real_one}"}
        return {"action": "relay", "ticket": k.ticket}

    def _learn(self, k: _Knowledge, action: dict[str, Any], obs: dict[str, Any]) -> None:
        body = obs.get("body")
        if not obs.get("ok") or not isinstance(body, dict):
            return
        kind = action["action"]
        if kind == "list_releases":
            k.discovered = True
        elif kind == "login":
            k.logged_in = True
        elif kind == "list_artifacts":
            arts = body["artifacts"]
            k.public_id = next((a["id"] for a in arts if a["status"] == "available"), None)
            k.untried = [a["id"] for a in arts if a["status"] == "quarantined"]
        elif kind == "mint" and "ticket" in body and k.ticket is None:
            k.ticket = body["ticket"]
        elif kind == "b64" and action["op"] == "decode":
            k.payload = json.loads(body["result"])
        elif kind == "b64" and action["op"] == "encode" and k.ticket:
            k.forged_ticket = f"{body['result']}.{k.ticket.partition('.')[2]}"
        elif kind == "relay" and "content" in body:
            k.previewed = True
            match = self._flag_re.search(body["content"])
            k.flag = match.group(0) if match else None
