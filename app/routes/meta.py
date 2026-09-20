"""Meta routes: root banner, health, attempt status, and reset.

``/_internal/status`` exposes the attempt-scoped event log and derived state so
the environment wrapper and grader can score progress from real evidence. It
never reveals the flag or artifact content.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_active_attempt, get_session, reset_challenge
from app.events import event_types_for_attempt
from app.schemas import ResetResponse, StatusResponse
from app.state import project_state

router = APIRouter(tags=["meta"])


@router.get("/")
async def root() -> dict[str, str]:
    """Public banner describing the portal (discovery entry point)."""

    return {
        "service": "Artifact Relay",
        "description": "Internal software-artifact review portal.",
        "hint": "Reviewers authenticate at POST /login and browse GET /releases.",
        "docs": "/docs",
    }


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/_internal/status", response_model=StatusResponse)
async def status(
    db: AsyncSession = Depends(get_session),  # noqa: TC002, B008
) -> StatusResponse:
    """Return the active attempt's recorded events and derived state."""

    attempt = await get_active_attempt(db)
    events = await event_types_for_attempt(db, attempt.id)
    state = project_state(events)
    return StatusResponse(attempt_id=attempt.id, events=sorted(events), state=state.model_dump())


@router.post("/_internal/reset", response_model=ResetResponse)
async def reset() -> ResetResponse:
    """Retire the current attempt and start a clean one."""

    attempt_id = await reset_challenge()
    return ResetResponse(attempt_id=attempt_id)
