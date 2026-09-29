"""Gymnasium-style wrapper that turns the HTTP challenge into reset()/step().

    obs = await env.reset(seed=7)
    obs, reward, terminated, truncated, info = await env.step(action)

One step is one turn. The reward is the increase in the grader's score, so it is
dense and the episode return equals the final score. The agent only ever sees
responses to its own requests. Grading reads the server's event log through the
admin-token channel, which agent-driven requests never use.

in_process=True talks to a private app over an ASGI transport (offline, used by
the tests and calibration). base_url=... drives a running container, in which
case AR_ADMIN_TOKEN must match the container's.
"""

from __future__ import annotations

import base64
import binascii
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
    "b64",
)


def _b64(op: str, data: str) -> dict[str, Any]:
    """URL-safe base64 encode/decode; padding is handled on both sides."""
    try:
        if op == "encode":
            result = base64.urlsafe_b64encode(data.encode()).decode().rstrip("=")
        elif op == "decode":
            raw = base64.b64decode(data + "=" * (-len(data) % 4), altchars=b"-_", validate=True)
            result = raw.decode()
        else:
            return {"ok": False, "error": "b64 op must be 'encode' or 'decode'"}
    except (binascii.Error, UnicodeError, ValueError) as exc:
        return {"ok": False, "error": f"b64 {op} failed: {exc}"}
    return {"ok": True, "body": {"result": result}}


class ArtifactRelayEnv:
    """One agent-facing episode loop over the challenge service."""

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
        self._admin = {"X-Admin-Token": get_config().admin_token}
        self._client: httpx.AsyncClient | None = None
        self._token: str | None = None
        self._turns = 0
        self._score = 0
        self.seed: int | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            if self._in_process:
                from app.database import init_db
                from app.main import create_app

                app = create_app()
                await init_db()
                transport = httpx.ASGITransport(app=app)
                self._client = httpx.AsyncClient(transport=transport, base_url=self._base_url)
            else:
                self._client = httpx.AsyncClient(base_url=self._base_url, timeout=10.0)
        return self._client

    async def reset(self, seed: int | None = None) -> dict[str, Any]:
        """Start a clean attempt (a random instance unless ``seed`` is given)."""
        client = await self._ensure_client()
        r = await client.post("/_internal/reset", json={"seed": seed}, headers=self._admin)
        if r.status_code == 403:
            raise RuntimeError(
                "Admin token rejected: set AR_ADMIN_TOKEN to the value the server runs with."
            )
        r.raise_for_status()
        self._token = None
        self._turns = 0
        self._score = 0
        return await self._observe(note="environment reset; attempt is clean")

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def step(self, action: dict[str, Any]) -> tuple[dict[str, Any], int, bool, bool, dict]:
        """Apply one action and return ``(obs, reward, terminated, truncated, info)``."""
        client = await self._ensure_client()
        self._turns += 1
        result = await self._dispatch(client, action)
        obs = await self._observe(**result)
        reward = obs["grade"]["score"] - self._score
        self._score = obs["grade"]["score"]

        terminated = obs["grade"]["solved"]
        truncated = not terminated and self._turns >= self.turn_budget
        return obs, reward, terminated, truncated, {"turns": self._turns}

    async def _dispatch(self, client: httpx.AsyncClient, action: dict[str, Any]) -> dict[str, Any]:
        """Map an action to one HTTP call (or a local codec op). Bad input is a no-op."""
        kind = action.get("action")
        if kind == "b64":
            return _b64(str(action.get("op", "")), str(action.get("data", "")))

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
            elif kind in ("http_get", "http_post"):
                path = str(action.get("path", "/"))
                if not path.startswith("/") or path.startswith("//"):
                    return {"ok": False, "error": "path must be an absolute path like /health"}
                if kind == "http_get":
                    r = await client.get(path, headers=headers)
                else:
                    r = await client.post(path, json=action.get("json", {}), headers=headers)
            else:
                return {"ok": False, "error": f"unknown action: {kind!r}", "actions": ACTIONS}
        except httpx.HTTPError as exc:
            return {"ok": False, "error": f"transport error: {exc}"}

        try:
            body: Any = r.json()
        except ValueError:
            body = r.text
        return {"ok": r.is_success, "status": r.status_code, "body": body}

    async def _observe(self, **response: Any) -> dict[str, Any]:
        """Score the attempt from the server's event log and attach the response."""
        client = await self._ensure_client()
        status = (await client.get("/_internal/status", headers=self._admin)).json()
        self.seed = status["seed"]
        return {
            "attempt_id": status["attempt_id"],
            "seed": status["seed"],
            "events": status["events"],
            "grade": grade(set(status["events"])).as_dict(),
            "turns_used": self._turns,
            "turns_left": max(0, self.turn_budget - self._turns),
            **response,
        }

    @staticmethod
    def reviewer_credentials() -> tuple[str, str]:
        """The account the agent is handed, as in a gray-box engagement."""
        cfg = get_config()
        return cfg.reviewer_username, cfg.reviewer_password
