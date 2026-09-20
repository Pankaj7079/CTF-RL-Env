"""Challenge event vocabulary and emit helper.

Events are the *only* thing the grader trusts. Each event is attempt-scoped and
written by the server in response to a genuine, verified state transition — never
in response to agent-supplied text. This is the backbone of the
anti-reward-hacking design.
"""

from __future__ import annotations

from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ChallengeEvent


class EventType(StrEnum):
    """The observable milestones a grader can key rewards off of."""

    RELEASES_LISTED = "RELEASES_LISTED"
    SESSION_ESTABLISHED = "SESSION_ESTABLISHED"
    TICKET_MINTED = "TICKET_MINTED"
    RELAY_OK = "RELAY_OK"
    PROTECTED_ARTIFACT_READ = "PROTECTED_ARTIFACT_READ"
    FLAG_CORRECT = "FLAG_CORRECT"


async def emit(
    session: AsyncSession, attempt_id: str, event_type: EventType, detail: str = ""
) -> None:
    """Append an attempt-scoped event. Caller commits."""

    session.add(ChallengeEvent(attempt_id=attempt_id, type=str(event_type), detail=detail))


async def event_types_for_attempt(session: AsyncSession, attempt_id: str) -> set[str]:
    """Return the set of event type names recorded for ``attempt_id``."""

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
