"""Reset semantics: fresh attempt, cleared state, stale credentials rejected."""

from __future__ import annotations

import httpx

from tests.conftest import SEED, admin, instance, login, redirect


async def test_reset_clears_state_and_invalidates_tickets(client: httpx.AsyncClient) -> None:
    await client.get("/releases")
    headers = await login(client)
    _flag, public, _restricted, holder = instance()
    ticket = (
        await client.post(
            "/tickets", json={"artifact_id": public["release_notes.txt"]}, headers=headers
        )
    ).json()["ticket"]
    tampered = redirect(ticket, holder)
    assert (await client.get("/relay", params={"ticket": tampered})).status_code == 200

    before = (await client.get("/_internal/status", headers=admin())).json()
    assert before["events"]

    reset = await client.post("/_internal/reset", json={"seed": SEED}, headers=admin())
    after = (await client.get("/_internal/status", headers=admin())).json()
    assert after["attempt_id"] == reset.json()["attempt_id"] != before["attempt_id"]
    assert after["events"] == []

    assert (await client.get("/relay", params={"ticket": tampered})).status_code == 410
    assert (await client.get("/artifacts", headers=headers)).status_code == 401


async def test_reset_with_a_seed_is_reproducible(client: httpx.AsyncClient) -> None:
    async def artifacts_for(seed: int) -> list[dict]:
        await client.post("/_internal/reset", json={"seed": seed}, headers=admin())
        headers = await login(client)
        return (await client.get("/artifacts", headers=headers)).json()["artifacts"]

    first = await artifacts_for(11)
    assert await artifacts_for(11) == first
    assert await artifacts_for(12) != first


async def test_reset_without_a_seed_picks_a_new_instance(client: httpx.AsyncClient) -> None:
    seeds = set()
    for _ in range(3):
        r = await client.post("/_internal/reset", headers=admin())
        seeds.add(r.json()["seed"])
    assert len(seeds) == 3
