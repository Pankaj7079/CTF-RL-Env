# Reward grading: monotonicity, totals, and no text-only / stale-state credit.

from __future__ import annotations

import httpx
from app.events import EventType

from grader.grader import grade, load_rubric
from tests.conftest import login
from tests.test_challenge import _redirect


def test_rubric_totals_100() -> None:
    rubric = load_rubric()
    assert rubric.max_score == 100
    assert len(rubric.stages) == 5


def test_grade_is_monotonic() -> None:
    rubric = load_rubric()
    order = [
        EventType.RELEASES_LISTED,
        EventType.SESSION_ESTABLISHED,
        EventType.TICKET_MINTED,
        EventType.RELAY_OK,
        EventType.PROTECTED_ARTIFACT_READ,
        EventType.FLAG_CORRECT,
    ]
    prev = -1
    acc: set[str] = set()
    for ev in order:
        acc.add(str(ev))
        score = grade(acc, rubric).score
        assert score >= prev
        prev = score
    assert prev == 100


async def test_flag_rejected_without_protected_read(client: httpx.AsyncClient) -> None:
    # Correct flag string alone must NOT be accepted without real progress.
    from app.config import get_config

    r = await client.post("/flag", json={"flag": get_config().flag})
    assert r.status_code == 200 and r.json()["correct"] is False


async def test_full_solve_scores_100(client: httpx.AsyncClient) -> None:
    from app.config import get_config

    await client.get("/releases")
    token = await login(client)
    h = {"Authorization": f"Bearer {token}"}
    ticket = (
        await client.post("/tickets", json={"artifact_id": "artifact-101-notes"}, headers=h)
    ).json()["ticket"]
    await client.get("/relay", params={"ticket": ticket})
    tampered = _redirect(ticket, "artifact-102-security-review")
    await client.get("/relay", params={"ticket": tampered})
    submit = await client.post("/flag", json={"flag": get_config().flag})
    assert submit.json()["correct"] is True

    status = (await client.get("/_internal/status")).json()
    assert grade(set(status["events"])).score == 100
