"""Authentication, access control and the harness-only admin channel."""

from __future__ import annotations

import httpx
from app.config import get_config

from tests.conftest import admin, login


async def test_login_success_and_failure(client: httpx.AsyncClient) -> None:
    cfg = get_config()
    ok = await client.post(
        "/login", json={"username": cfg.reviewer_username, "password": cfg.reviewer_password}
    )
    assert ok.status_code == 200 and ok.json()["token"].startswith("sess_")

    bad = await client.post("/login", json={"username": "reviewer", "password": "wrong"})
    assert bad.status_code == 401


async def test_artifacts_requires_session(client: httpx.AsyncClient) -> None:
    assert (await client.get("/artifacts")).status_code == 401

    listing = await client.get("/artifacts", headers=await login(client))
    assert listing.status_code == 200
    assert any(a["status"] == "quarantined" for a in listing.json()["artifacts"])


async def test_internal_routes_need_the_admin_token(client: httpx.AsyncClient) -> None:
    session = await login(client)
    for headers in ({}, session, {"X-Admin-Token": "guess"}):
        assert (await client.get("/_internal/status", headers=headers)).status_code == 403
        assert (await client.post("/_internal/reset", headers=headers)).status_code == 403
    assert (await client.get("/_internal/status", headers=admin())).status_code == 200


async def test_internal_routes_are_not_advertised(client: httpx.AsyncClient) -> None:
    schema = (await client.get("/openapi.json")).json()
    assert not [p for p in schema["paths"] if p.startswith("/_internal")]
