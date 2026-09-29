"""The intended flaw, and the guards around it."""

from __future__ import annotations

import base64
import json

import httpx

from tests.conftest import admin, instance, login, redirect


async def _mint(client: httpx.AsyncClient, headers: dict[str, str], artifact_id: str) -> str:
    r = await client.post("/tickets", json={"artifact_id": artifact_id}, headers=headers)
    assert r.status_code == 200
    return r.json()["ticket"]


async def test_cannot_mint_for_quarantined(client: httpx.AsyncClient) -> None:
    headers = await login(client)
    _flag, _public, restricted, _holder = instance()
    for artifact_id in restricted:
        r = await client.post("/tickets", json={"artifact_id": artifact_id}, headers=headers)
        assert r.status_code == 403  # the mint-time policy holds


async def test_redirected_ticket_reads_the_holder(client: httpx.AsyncClient) -> None:
    headers = await login(client)
    flag, public, _restricted, holder = instance()
    ticket = await _mint(client, headers, public["release_notes.txt"])

    relayed = await client.get("/relay", params={"ticket": redirect(ticket, holder)})
    assert relayed.status_code == 200
    assert flag in relayed.json()["content"]


async def test_decoys_do_not_contain_the_flag(client: httpx.AsyncClient) -> None:
    headers = await login(client)
    flag, public, restricted, holder = instance()
    ticket = await _mint(client, headers, public["release_notes.txt"])
    for artifact_id in (a for a in restricted if a != holder):
        r = await client.get("/relay", params={"ticket": redirect(ticket, artifact_id)})
        assert r.status_code == 200 and flag not in r.json()["content"]


async def test_editing_scope_breaks_the_signature(client: httpx.AsyncClient) -> None:
    headers = await login(client)
    _flag, public, _restricted, _holder = instance()
    ticket = await _mint(client, headers, public["release_notes.txt"])

    body, _, signature = ticket.partition(".")
    payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    payload["scope"] = "project:secret"
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
    forged = f"{base64.urlsafe_b64encode(raw).decode().rstrip('=')}.{signature}"
    assert (await client.get("/relay", params={"ticket": forged})).status_code == 401


async def test_redirect_is_recorded_only_when_the_ticket_was_edited(
    client: httpx.AsyncClient,
) -> None:
    headers = await login(client)
    _flag, public, _restricted, _holder = instance()
    notes, manifest = public["release_notes.txt"], public["manifest.json"]
    ticket = await _mint(client, headers, notes)

    await client.get("/relay", params={"ticket": ticket})
    events = (await client.get("/_internal/status", headers=admin())).json()["events"]
    assert "TICKET_REDIRECTED" not in events

    # Editing a ticket toward another public artifact is still a redirect.
    await client.get("/relay", params={"ticket": redirect(ticket, manifest)})
    events = (await client.get("/_internal/status", headers=admin())).json()["events"]
    assert "TICKET_REDIRECTED" in events
    assert "PROTECTED_ARTIFACT_READ" not in events
