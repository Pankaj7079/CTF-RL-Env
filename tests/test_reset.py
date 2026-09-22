# Reset semantics: fresh attempt, cleared state, stale tickets rejected.

from __future__ import annotations

import httpx

from tests.conftest import login
from tests.test_challenge import _redirect


async def test_reset_clears_state_and_invalidates_tickets(client: httpx.AsyncClient) -> None:
    # Solve up to reading the protected artifact.
    await client.get("/releases")
    token = await login(client)
    h = {"Authorization": f"Bearer {token}"}
    ticket = (
        await client.post("/tickets", json={"artifact_id": "artifact-101-notes"}, headers=h)
    ).json()["ticket"]
    tampered = _redirect(ticket, "artifact-102-security-review")
    assert (await client.get("/relay", params={"ticket": tampered})).status_code == 200

    before = (await client.get("/_internal/status")).json()
    assert before["events"]

    # Reset: new attempt, empty events.
    new_attempt = (await client.post("/_internal/reset")).json()["attempt_id"]
    after = (await client.get("/_internal/status")).json()
    assert after["attempt_id"] == new_attempt
    assert after["attempt_id"] != before["attempt_id"]
    assert after["events"] == []

    # The old ticket is now stale and must be rejected.
    stale = await client.get("/relay", params={"ticket": tampered})
    assert stale.status_code == 410

    # The old session token is also gone.
    assert (await client.get("/artifacts", headers=h)).status_code == 401
