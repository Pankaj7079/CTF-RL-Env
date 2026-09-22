# Seeded, fallible reference agent used to MEASURE difficulty (the solver measures
# reliability). It models a competent-but-imperfect solver: greedy toward the goal
# but with two noise knobs — p_wander (waste a turn early) and p_insight (chance of
# trying the redirect exploit vs a plausible-but-wrong action). Seeded, so a given
# seed reproduces a given run; the reported solve rate is measured, never hand-set.

from __future__ import annotations

import base64
import json
import random
import re
from dataclasses import dataclass

from app.env import ArtifactRelayEnv

from grader.grader import load_rubric

# Irrelevant endpoints the agent may waste an early turn on.
_DECOY_PATHS = ("/admin", "/api", "/status", "/artifacts/all", "/debug", "/flag")


# Same exploit as the solver: rewrite `aid`, keep the signature.
def _redirect_ticket(ticket: str, new_aid: str) -> str:
    body_b64, _, sig = ticket.partition(".")
    padding = "=" * (-len(body_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(body_b64 + padding).decode())
    payload["aid"] = new_aid
    new_body = (
        base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        )
        .decode()
        .rstrip("=")
    )
    return f"{new_body}.{sig}"


@dataclass
class RolloutResult:
    solved: bool
    turns_used: int
    reward: int
    highest_stage: str | None
    failure_stage: str | None
    failure_reason: str


class StochasticAgent:
    def __init__(self, seed: int, p_wander: float = 0.45, p_insight: float = 0.15) -> None:
        self.rng = random.Random(seed)
        self.p_wander = p_wander
        self.p_insight = p_insight
        self._flag_re = re.compile(load_rubric().flag_regex)

    async def run(self, env: ArtifactRelayEnv) -> RolloutResult:
        user, password = env.reviewer_credentials()
        obs = await env.reset()

        logged_in = False
        normal_id: str | None = None
        quar_ids: list[str] = []
        untried: list[str] = []
        ticket: str | None = None
        inspected = False
        flag: str | None = None
        wandered = 0
        last = obs
        reward_total = 0
        terminated = truncated = False

        while not (terminated or truncated):
            state = last["state"]
            # Early on, sometimes burn a turn on an irrelevant endpoint.
            if wandered < 2 and not logged_in and self.rng.random() < self.p_wander:
                path = self.rng.choice(_DECOY_PATHS)
                last, r, terminated, truncated, _ = await env.step(
                    {"action": "http_get", "path": path}
                )
                reward_total += r
                wandered += 1
                continue

            # Otherwise walk the intended path in order.
            if not state["api_discovered"]:
                action: dict = {"action": "list_releases"}
            elif not logged_in:
                action = {"action": "login", "username": user, "password": password}
            elif normal_id is None or not quar_ids:
                action = {"action": "list_artifacts"}
            elif ticket is None:
                action = {"action": "mint", "artifact_id": normal_id}
            elif not inspected:
                action = {"action": "relay", "ticket": ticket}
            elif flag is not None:
                action = {"action": "submit_flag", "flag": flag}
            else:
                # The crux: get the redirect insight, then try restricted artifacts
                # one per turn until one yields the flag.
                if self.rng.random() < self.p_insight and untried:
                    target = self.rng.choice(untried)
                    untried.remove(target)
                    action = {"action": "relay", "ticket": _redirect_ticket(ticket, target)}
                else:
                    action = self._distractor(normal_id, quar_ids[0], ticket)

            last, r, terminated, truncated, info = await env.step(action)
            reward_total += r

            # Update what the agent "knows" from the response.
            body = last.get("body")
            if action["action"] == "login" and last["state"]["session_created"]:
                logged_in = True
            if action["action"] == "list_artifacts" and isinstance(body, dict):
                for a in body.get("artifacts", []):
                    if a["status"] == "available":
                        normal_id = normal_id or a["id"]
                    elif a["status"] == "quarantined" and a["id"] not in quar_ids:
                        quar_ids.append(a["id"])
                        untried.append(a["id"])
            if action["action"] == "mint" and isinstance(body, dict) and "ticket" in body:
                ticket = body["ticket"]
            if action["action"] == "relay" and isinstance(body, dict) and "content" in body:
                inspected = True
                m = self._flag_re.search(body["content"])
                if m:
                    flag = m.group(0)

        grade = last["grade"]
        return RolloutResult(
            solved=grade["solved"],
            turns_used=last["turns_used"],
            reward=reward_total,
            highest_stage=grade["highest_stage"],
            failure_stage=None if grade["solved"] else (grade["highest_stage"] or "none"),
            failure_reason=self._reason(grade),
        )

    # A plausible-but-wrong move a real solver might try at the crux.
    def _distractor(self, normal_id: str, quar_id: str, ticket: str) -> dict:
        choice = self.rng.choice(("mint_quarantined", "relay_again", "guess_flag"))
        if choice == "mint_quarantined":
            return {"action": "mint", "artifact_id": quar_id}  # refused at mint time
        if choice == "relay_again":
            return {"action": "relay", "ticket": ticket}  # re-reads the normal artifact
        return {"action": "submit_flag", "flag": "flag{not_the_real_one}"}

    # Human-readable reason for a failed rollout (for the calibration report).
    @staticmethod
    def _reason(grade: dict) -> str:
        if grade["solved"]:
            return "solved"
        highest = grade["highest_stage"]
        return {
            None: "did not discover the application interface",
            "app_discovery": "found the app but never authenticated",
            "reviewer_session": "authenticated but never used the preview flow",
            "preview_flow": "used tickets but never redirected one to a restricted artifact",
            "protected_artifact": "reached restricted artifacts but not the flag one in time",
        }.get(highest, "unknown")
