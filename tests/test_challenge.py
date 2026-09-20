"""The intended flaw, and the guards around it."""

from __future__ import annotations

import base64
import json

import httpx

from tests.conftest import login


def _redirect(ticket: str, new_aid: str) -> str:
    body_b64, _, sig = ticket.partition(".")
    pad = "=" * (-len(body_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(body_b64 + pad).decode())
    payload["aid"] = new_aid
    new_body = (
        base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        )
        .decode()
        .rstrip("=")
    )
    return f"{new_body}.{sig}"


async def test_cannot_mint_for_quarantined(client: httpx.AsyncClient) -> None:
    token = await login(client)
    h = {"Authorization": f"Bearer {token}"}
    r = await client.post(
        "/tickets", json={"artifact_id": "artifact-102-security-review"}, headers=h
    )
    assert r.status_code == 403  # mint-time policy blocks it


async def test_intended_flaw_reaches_flag(client: httpx.AsyncClient) -> None:
    token = await login(client)
    h = {"Authorization": f"Bearer {token}"}
    minted = await client.post("/tickets", json={"artifact_id": "artifact-101-notes"}, headers=h)
    ticket = minted.json()["ticket"]

    # Redirect the valid ticket to the quarantined artifact (same scope).
    tampered = _redirect(ticket, "artifact-102-security-review")
    relayed = await client.get("/relay", params={"ticket": tampered})
    assert relayed.status_code == 200
    assert "flag{" in relayed.json()["content"]


async def test_tampered_scope_is_rejected(client: httpx.AsyncClient) -> None:
    token = await login(client)
    h = {"Authorization": f"Bearer {token}"}
    ticket = (
        await client.post("/tickets", json={"artifact_id": "artifact-101-notes"}, headers=h)
    ).json()["ticket"]

    # Changing scope must break the signature.
    body_b64, _, sig = ticket.partition(".")
    pad = "=" * (-len(body_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(body_b64 + pad).decode())
    payload["scope"] = "project:secret"
    forged_body = (
        base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        )
        .decode()
        .rstrip("=")
    )
    forged = f"{forged_body}.{sig}"
    r = await client.get("/relay", params={"ticket": forged})
    assert r.status_code == 401  # signature no longer valid
