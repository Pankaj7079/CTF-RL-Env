# Pytest fixtures — an isolated, reset in-process app per test. A throwaway SQLite
# file is set BEFORE importing any app module (config is cached), and each test
# gets a freshly reset attempt over an httpx ASGI client (no network).

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator

# Configure a throwaway DB before importing app modules (config is cached).
_TMP_DB = os.path.join(tempfile.gettempdir(), "artifact_relay_test.db")
os.environ.setdefault("AR_DATABASE_URL", f"sqlite+aiosqlite:///{_TMP_DB}")

import httpx  # noqa: E402
import pytest  # noqa: E402
from app.database import init_db, reset_challenge  # noqa: E402
from app.main import create_app  # noqa: E402


@pytest.fixture
async def client() -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    await init_db()
    await reset_challenge()
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://challenge") as c:
        yield c


async def login(client: httpx.AsyncClient) -> str:
    from app.config import get_config

    cfg = get_config()
    r = await client.post(
        "/login", json={"username": cfg.reviewer_username, "password": cfg.reviewer_password}
    )
    assert r.status_code == 200
    return r.json()["token"]
