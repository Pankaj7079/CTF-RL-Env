# Authentication and access-control behavior.

from __future__ import annotations

import httpx
from app.config import get_config

from tests.conftest import login


async def test_login_success_and_failure(client: httpx.AsyncClient) -> None:
    cfg = get_config()
    ok = await client.post(
        "/login", json={"username": cfg.reviewer_username, "password": cfg.reviewer_password}
    )
    assert ok.status_code == 200 and ok.json()["token"].startswith("sess_")

    bad = await client.post("/login", json={"username": "reviewer", "password": "wrong"})
    assert bad.status_code == 401


async def test_artifacts_requires_session(client: httpx.AsyncClient) -> None:
    unauth = await client.get("/artifacts")
    assert unauth.status_code == 401

    token = await login(client)
    auth = await client.get("/artifacts", headers={"Authorization": f"Bearer {token}"})
    assert auth.status_code == 200
    assert any(a["status"] == "quarantined" for a in auth.json()["artifacts"])
