# Gymnasium-style wrapper: turns the HTTP challenge into reset()/step().
#   obs = env.reset()
#   obs, reward, terminated, truncated, info = env.step(action)
# One step = one turn (action + observation). Reward = increase in the grader's
# cumulative score, so the signal is dense and monotonic.
#
# Two modes: in_process=True talks to a fresh app over an ASGI transport (offline,
# for tests/calibration); base_url=... hits a running container. Unknown/malformed
# actions are safe no-ops that still cost a turn.

from __future__ import annotations

from typing import Any

import httpx

from app.config import get_config
from grader.grader import Rubric, grade, load_rubric

ACTIONS = (
    "root",
    "list_releases",
    "login",
    "list_artifacts",
    "mint",
    "relay",
    "submit_flag",
    "http_get",
    "http_post",
)


class ArtifactRelayEnv:
    def __init__(
        self,
        base_url: str | None = None,
        in_process: bool = True,
        turn_budget: int | None = None,
    ) -> None:
        self._rubric: Rubric = load_rubric()
        self.turn_budget = turn_budget or self._rubric.turn_budget
        self._in_process = in_process
        self._base_url = base_url or "http://challenge"
        self._client: httpx.AsyncClient | None = None
        self._token: str | None = None
        self._turns = 0
        self._score = 0

    # Build the HTTP client lazily (ASGI in-process, or a real network client).
    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            if self._in_process:
                # Imported here so this module loads without a DB configured.
                from app.database import init_db
                from app.main import create_app

                app = create_app()
                await init_db()
                transport = httpx.ASGITransport(app=app)
                self._client = httpx.AsyncClient(transport=transport, base_url=self._base_url)
            else:
                self._client = httpx.AsyncClient(base_url=self._base_url, timeout=10.0)
        return self._client

    # Start a clean attempt; return the first observation.
    async def reset(self) -> dict[str, Any]:
        client = await self._ensure_client()
        await client.post("/_internal/reset")
        self._token = None
        self._turns = 0
        self._score = 0
        return await self._observe(note="environment reset; attempt is clean")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # Apply one action -> (obs, reward, terminated, truncated, info).
    async def step(self, action: dict[str, Any]) -> tuple[dict[str, Any], int, bool, bool, dict]:
        client = await self._ensure_client()
        self._turns += 1
        result = await self._dispatch(client, action)

        # Flatten the response (ok/status/body/error) into the observation.
        obs = await self._observe(action_result=result, **result)
        new_score = obs["grade"]["score"]
        reward = new_score - self._score
        self._score = new_score

        terminated = obs["grade"]["solved"]
        truncated = (not terminated) and self._turns >= self.turn_budget
        info = {"turns": self._turns, "turn_budget": self.turn_budget}
        return obs, reward, terminated, truncated, info

    # Map an action dict to the matching HTTP call; keep the session token in sync.
    async def _dispatch(self, client: httpx.AsyncClient, action: dict[str, Any]) -> dict[str, Any]:
        kind = action.get("action")
        headers = {"Authorization": f"Bearer {self._token}"} if self._token else {}
        try:
            if kind == "root":
                r = await client.get("/")
            elif kind == "list_releases":
                r = await client.get("/releases")
            elif kind == "login":
                r = await client.post(
                    "/login",
                    json={
                        "username": action.get("username", ""),
                        "password": action.get("password", ""),
                    },
                )
                if r.status_code == 200:
                    self._token = r.json()["token"]
            elif kind == "list_artifacts":
                params = {"release": action["release"]} if action.get("release") else {}
                r = await client.get("/artifacts", params=params, headers=headers)
            elif kind == "mint":
                r = await client.post(
                    "/tickets", json={"artifact_id": action.get("artifact_id", "")}, headers=headers
                )
            elif kind == "relay":
                r = await client.get("/relay", params={"ticket": action.get("ticket", "")})
            elif kind == "submit_flag":
                r = await client.post("/flag", json={"flag": action.get("flag", "")})
            elif kind == "http_get":
                r = await client.get(action.get("path", "/"), headers=headers)
            elif kind == "http_post":
                r = await client.post(
                    action.get("path", "/"), json=action.get("json", {}), headers=headers
                )
            else:
                return {"ok": False, "error": f"unknown action: {kind!r}", "actions": ACTIONS}
        except httpx.HTTPError as exc:  # transport failure -> safe no-op
            return {"ok": False, "error": f"transport error: {exc}"}

        body: Any
        try:
            body = r.json()
        except ValueError:
            body = r.text
        return {"ok": r.is_success, "status": r.status_code, "body": body}

    # Read attempt status from the server and score it with the grader.
    async def _observe(self, **extra: Any) -> dict[str, Any]:
        client = await self._ensure_client()
        status = (await client.get("/_internal/status")).json()
        result = grade(set(status["events"]))
        return {
            "attempt_id": status["attempt_id"],
            "state": status["state"],
            "events": status["events"],
            "grade": result.as_dict(),
            "turns_used": self._turns,
            "turns_left": max(0, self.turn_budget - self._turns),
            **extra,
        }

    # Reviewer creds are public knowledge for the reference agents.
    @staticmethod
    def reviewer_credentials() -> tuple[str, str]:
        cfg = get_config()
        return cfg.reviewer_username, cfg.reviewer_password
