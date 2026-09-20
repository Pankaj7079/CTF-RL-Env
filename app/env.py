"""Gymnasium-style environment wrapper around the Artifact Relay challenge.

This turns the HTTP challenge into a standard agent-environment loop:

    obs = env.reset()
    obs, reward, terminated, truncated, info = env.step(action)

A *turn* is exactly one ``step`` — one agent action and the observation it
returns — matching the assignment's definition and its 16-turn budget. Reward is
the increase in the grader's cumulative score caused by that action, so the
signal is dense and monotonic.

The environment can run two ways:

* in-process (``in_process=True``): an ASGI transport talks to a fresh app with
  no network at all — used for deterministic, offline calibration and tests;
* over HTTP (``base_url=...``): against a running container.

The action space is a small, explicit dict protocol (see ``ACTIONS``). Unknown or
malformed actions are safe no-ops that cost a turn — an agent cannot crash the
environment or earn reward without a real state transition.
"""

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
    """An async, resettable environment for one solve attempt at a time."""

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

    # --- lifecycle ----------------------------------------------------------
    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            if self._in_process:
                # Import lazily so the module is importable without a DB.
                from app.database import init_db
                from app.main import create_app

                app = create_app()
                await init_db()
                transport = httpx.ASGITransport(app=app)
                self._client = httpx.AsyncClient(transport=transport, base_url=self._base_url)
            else:
                self._client = httpx.AsyncClient(base_url=self._base_url, timeout=10.0)
        return self._client

    async def reset(self) -> dict[str, Any]:
        """Start a clean attempt and return the initial observation."""

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

    # --- stepping -----------------------------------------------------------
    async def step(self, action: dict[str, Any]) -> tuple[dict[str, Any], int, bool, bool, dict]:
        """Apply one action. Returns (obs, reward, terminated, truncated, info)."""

        client = await self._ensure_client()
        self._turns += 1
        result = await self._dispatch(client, action)

        # Surface the action's response at the top level of the observation
        # (``ok``/``status``/``body``/``error``) for convenient agent access.
        obs = await self._observe(action_result=result, **result)
        new_score = obs["grade"]["score"]
        reward = new_score - self._score
        self._score = new_score

        terminated = obs["grade"]["solved"]
        truncated = (not terminated) and self._turns >= self.turn_budget
        info = {"turns": self._turns, "turn_budget": self.turn_budget}
        return obs, reward, terminated, truncated, info

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
        except httpx.HTTPError as exc:  # network/transport failure is a safe no-op
            return {"ok": False, "error": f"transport error: {exc}"}

        body: Any
        try:
            body = r.json()
        except ValueError:
            body = r.text
        return {"ok": r.is_success, "status": r.status_code, "body": body}

    # --- observation --------------------------------------------------------
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

    # --- convenience --------------------------------------------------------
    @staticmethod
    def reviewer_credentials() -> tuple[str, str]:
        """Return the reviewer credentials (public knowledge for the reference agent)."""

        cfg = get_config()
        return cfg.reviewer_username, cfg.reviewer_password
