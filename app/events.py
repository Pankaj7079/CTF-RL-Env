# The event vocabulary + helpers. The server writes an event only on a real,
# verified state transition — never from agent text. This is the anti-cheat core.

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChallengeEvent


# The observable milestones the grader keys rewards off.
class EventType(StrEnum):
    RELEASES_LISTED = "RELEASES_LISTED"
    SESSION_ESTABLISHED = "SESSION_ESTABLISHED"
    TICKET_MINTED = "TICKET_MINTED"
    RELAY_OK = "RELAY_OK"
    PROTECTED_ARTIFACT_READ = "PROTECTED_ARTIFACT_READ"
    FLAG_CORRECT = "FLAG_CORRECT"


# Record an event for this attempt. Caller is responsible for committing.
async def emit(
    session: AsyncSession, attempt_id: str, event_type: EventType, detail: str = ""
) -> None:
    session.add(ChallengeEvent(attempt_id=attempt_id, type=str(event_type), detail=detail))


# All event type names seen in one attempt (what the grader reads).
async def event_types_for_attempt(session: AsyncSession, attempt_id: str) -> set[str]:
    rows = (
        (
            await session.execute(
                select(ChallengeEvent.type).where(ChallengeEvent.attempt_id == attempt_id)
            )
        )
        .scalars()
        .all()
    )
    return set(rows)
