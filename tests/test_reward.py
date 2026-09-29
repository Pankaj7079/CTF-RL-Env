"""Reward grading: monotone, totals 100, and no credit for text or stale state."""

from __future__ import annotations

import httpx
from app.events import EventType

from grader.grader import grade, load_rubric
from tests.conftest import SEED, admin, instance, login, redirect


def test_rubric_totals_100() -> None:
    rubric = load_rubric()
    assert rubric.max_score == 100
    assert len(rubric.stages) == 6


def test_grade_is_monotonic_and_reaches_100() -> None:
    order = [
        EventType.RELEASES_LISTED,
        EventType.SESSION_ESTABLISHED,
        EventType.TICKET_MINTED,
        EventType.RELAY_OK,
        EventType.TICKET_REDIRECTED,
        EventType.PROTECTED_ARTIFACT_READ,
        EventType.FLAG_CORRECT,
    ]
    seen: set[str] = set()
    previous = -1
    for event in order:
        seen.add(str(event))
        score = grade(seen).score
        assert score >= previous
        previous = score
    assert previous == 100


def test_flag_stage_alone_solves_but_scores_less() -> None:
    result = grade({str(EventType.FLAG_CORRECT)})
    assert result.solved and result.score < 100


async def test_flag_rejected_without_protected_read(client: httpx.AsyncClient) -> None:
    flag, *_ = instance()
    r = await client.post("/flag", json={"flag": flag})
    assert r.status_code == 200 and r.json()["correct"] is False


async def test_flag_from_another_instance_is_rejected(client: httpx.AsyncClient) -> None:
    headers = await login(client)
    _flag, public, _restricted, holder = instance()
    ticket = (
        await client.post(
            "/tickets", json={"artifact_id": public["release_notes.txt"]}, headers=headers
        )
    ).json()["ticket"]
    await client.get("/relay", params={"ticket": redirect(ticket, holder)})

    other_flag, *_ = instance(SEED + 1)
    r = await client.post("/flag", json={"flag": other_flag})
    assert r.json()["correct"] is False


async def test_full_solve_scores_100(client: httpx.AsyncClient) -> None:
    flag, public, _restricted, holder = instance()
    await client.get("/releases")
    headers = await login(client)
    ticket = (
        await client.post(
            "/tickets", json={"artifact_id": public["release_notes.txt"]}, headers=headers
        )
    ).json()["ticket"]
    await client.get("/relay", params={"ticket": ticket})
    await client.get("/relay", params={"ticket": redirect(ticket, holder)})
    assert (await client.post("/flag", json={"flag": flag})).json()["correct"] is True

    status = (await client.get("/_internal/status", headers=admin())).json()
    assert grade(set(status["events"])).score == 100
