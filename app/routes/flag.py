"""Flag submission route (reward stage 5).

The flag is accepted only if it matches exactly AND the active attempt has
already read the protected artifact through the relay. This ties the final reward
to real environment evidence, not to a guessed or leaked string.
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ChallengeConfig, get_config
from app.database import get_active_attempt, get_session
from app.events import EventType, emit, event_types_for_attempt
from app.schemas import FlagRequest, FlagResponse

router = APIRouter(tags=["flag"])


@router.post("/flag", response_model=FlagResponse)
async def submit_flag(
    body: FlagRequest,
    db: AsyncSession = Depends(get_session),  # noqa: TC002, B008
    config: ChallengeConfig = Depends(get_config),  # noqa: TC002, B008
) -> FlagResponse:
    """Submit the flag for the active attempt."""

    attempt = await get_active_attempt(db)
    matches = secrets.compare_digest(body.flag.strip(), config.flag)
    if not matches:
        return FlagResponse(correct=False, message="Incorrect flag.")

    # Anti-reward-hacking: a correct string alone is not enough — the attempt must
    # have genuinely reached the protected artifact through the challenge.
    seen = await event_types_for_attempt(db, attempt.id)
    if EventType.PROTECTED_ARTIFACT_READ not in seen:
        return FlagResponse(
            correct=False,
            message="Flag not accepted: the protected artifact was not reached in this attempt.",
        )

    await emit(db, attempt.id, EventType.FLAG_CORRECT, detail="ok")
    await db.commit()
    return FlagResponse(correct=True, message="Correct — challenge solved.")
