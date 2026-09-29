# Banner and health are public. /_internal/* is the harness channel (grading
# status and reset): admin token required and hidden from the OpenAPI schema, so
# an agent browsing /docs never learns it exists.

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_active_attempt, get_session, reset_challenge
from app.deps import require_admin
from app.events import event_types_for_attempt
from app.schemas import ResetResponse, StatusResponse

router = APIRouter(tags=["meta"])
internal = APIRouter(
    prefix="/_internal",
    dependencies=[Depends(require_admin)],
    include_in_schema=False,
)


class ResetRequest(BaseModel):
    seed: int | None = None


@router.get("/")
async def root() -> dict[str, str]:
    return {
        "service": "CTF-RL-Env",
        "description": "Internal software-artifact review portal.",
        "hint": "Reviewers authenticate at POST /login and browse GET /releases.",
        "docs": "/docs",
    }


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@internal.get("/status", response_model=StatusResponse)
async def status(
    db: AsyncSession = Depends(get_session),  # noqa: TC002, B008
) -> StatusResponse:
    attempt = await get_active_attempt(db)
    events = await event_types_for_attempt(db, attempt.id)
    return StatusResponse(attempt_id=attempt.id, seed=attempt.seed, events=sorted(events))


@internal.post("/reset", response_model=ResetResponse)
async def reset(body: ResetRequest | None = None) -> ResetResponse:
    attempt = await reset_challenge(body.seed if body else None)
    return ResetResponse(attempt_id=attempt.id, seed=attempt.seed)
