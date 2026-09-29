# /flag — submit the flag (reward stage 5). Accepted only if it matches AND this
# attempt actually read the protected artifact — so a guessed/leaked string fails.

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_active_attempt, get_session
from app.events import EventType, emit, event_types_for_attempt
from app.schemas import FlagRequest, FlagResponse

router = APIRouter(tags=["flag"])


@router.post("/flag", response_model=FlagResponse)
async def submit_flag(
    body: FlagRequest,
    db: AsyncSession = Depends(get_session),  # noqa: TC002, B008
) -> FlagResponse:
    attempt = await get_active_attempt(db)
    matches = secrets.compare_digest(body.flag.strip().encode(), attempt.flag.encode())
    if not matches:
        return FlagResponse(correct=False, message="Incorrect flag.")

    # Anti-cheat: a correct string alone isn't enough — the attempt must have
    # actually reached the protected artifact through the relay.
    seen = await event_types_for_attempt(db, attempt.id)
    if EventType.PROTECTED_ARTIFACT_READ not in seen:
        return FlagResponse(
            correct=False,
            message="Flag not accepted: the protected artifact was not reached in this attempt.",
        )

    await emit(db, attempt.id, EventType.FLAG_CORRECT, detail="ok")
    await db.commit()
    return FlagResponse(correct=True, message="Correct — challenge solved.")
