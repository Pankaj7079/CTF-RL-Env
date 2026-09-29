"""Shared fixtures: an isolated in-process app reset to a fixed seed per test."""

from __future__ import annotations

import base64
import json
import os
import tempfile
from collections.abc import AsyncIterator

# The config is cached, so point it at a throwaway DB before importing app modules.
_TMP_DB = os.path.join(tempfile.gettempdir(), "ctf_rl_env_test.db")
if os.path.exists(_TMP_DB):
    os.remove(_TMP_DB)
os.environ["CTF_DATABASE_URL"] = f"sqlite+aiosqlite:///{_TMP_DB}"

import httpx  # noqa: E402
import pytest  # noqa: E402
from app.config import get_config  # noqa: E402
from app.database import init_db, reset_challenge  # noqa: E402
from app.instance import build_instance  # noqa: E402
from app.main import create_app  # noqa: E402

SEED = 7


def admin() -> dict[str, str]:
    """Headers for the harness-only /_internal/* routes."""
    return {"X-Admin-Token": get_config().admin_token}


def instance(seed: int = SEED) -> tuple[str, dict[str, str], list[str], str]:
    """``(flag, public ids by name, restricted ids, flag holder id)`` for ``seed``."""
    flag, artifacts = build_instance(get_config(), seed)
    restricted = [a.id for a in artifacts if a.quarantined]
    holder = next(a.id for a in artifacts if flag in a.content)
    public = {a.name: a.id for a in artifacts if not a.quarantined}
    return flag, public, restricted, holder


def redirect(ticket: str, new_aid: str) -> str:
    """Rewrite a ticket's ``aid`` and keep its signature (the exploit)."""
    body, _, signature = ticket.partition(".")
    payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    payload["aid"] = new_aid
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    return f"{base64.urlsafe_b64encode(raw).decode().rstrip('=')}.{signature}"


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    await init_db()
    await reset_challenge(SEED)
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://challenge") as c:
        yield c


async def login(client: httpx.AsyncClient) -> dict[str, str]:
    """Log in as the reviewer; return the Authorization header."""
    cfg = get_config()
    r = await client.post(
        "/login", json={"username": cfg.reviewer_username, "password": cfg.reviewer_password}
    )
    assert r.status_code == 200
    return {"Authorization": f"Bearer {r.json()['token']}"}
