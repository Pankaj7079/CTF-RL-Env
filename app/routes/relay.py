"""Artifact relay route — the vulnerable endpoint (reward stages 3b & 4).

Given a signed ticket, the relay serves the artifact named by the ticket's
``aid`` field. It verifies:

1. the ticket signature (which, by design, covers only ``scope``);
2. that the requested artifact's scope equals the ticket's scope;
3. that the ticket belongs to the *active* attempt (anti stale/replay).

Critically, it never re-checks ``quarantined``. That policy is only enforced at
mint time, so a ticket minted for an available artifact and redirected (via a
rewritten ``aid``) to a quarantined artifact in the same scope is served. This
is the intended confused-deputy flaw.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ChallengeConfig, get_config
from app.database import get_active_attempt, get_session
from app.events import EventType, emit
from app.models import Artifact
from app.tickets import verify_ticket

router = APIRouter(tags=["relay"])


@router.get("/relay")
async def relay_artifact(
    ticket: str = Query(..., description="A preview ticket from POST /tickets."),
    db: AsyncSession = Depends(get_session),  # noqa: TC002, B008
    config: ChallengeConfig = Depends(get_config),  # noqa: TC002, B008
) -> dict[str, str]:
    """Serve an artifact's content for a valid ticket."""

    payload = verify_ticket(config.ticket_secret, ticket)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ticket.")

    # Anti-replay across resets: the ticket must belong to the active attempt.
    attempt = await get_active_attempt(db)
    if payload.attempt != attempt.id:
        raise HTTPException(
            status_code=status.HTTP_410_GONE, detail="Ticket is stale (belongs to a past attempt)."
        )

    artifact = (
        (await db.execute(select(Artifact).where(Artifact.id == payload.aid))).scalars().first()
    )
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such artifact.")

    # The only authorization check on the relay path: scope match.
    # (Note: quarantine status is deliberately NOT re-checked here.)
    if artifact.scope != payload.scope:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Ticket scope does not cover artifact."
        )

    await emit(db, attempt.id, EventType.RELAY_OK, detail=artifact.id)
    if artifact.quarantined:
        await emit(db, attempt.id, EventType.PROTECTED_ARTIFACT_READ, detail=artifact.id)
    await db.commit()

    return {"artifact_id": artifact.id, "name": artifact.name, "content": artifact.content}
