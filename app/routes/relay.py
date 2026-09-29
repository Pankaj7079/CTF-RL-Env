# /relay — the vulnerable endpoint (ticket_redirect, protected_artifact). It verifies the ticket
# signature (scope only), a scope match, and that the ticket is from the active
# attempt — but never re-checks `quarantined`. That omission is the flaw: a ticket
# redirected (rewritten `aid`) to a quarantined artifact in the same scope is served.

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ChallengeConfig, get_config
from app.database import get_active_attempt, get_session
from app.events import EventType, emit, event_details
from app.models import Artifact
from app.tickets import verify_ticket

router = APIRouter(tags=["relay"])


@router.get("/relay")
async def relay_artifact(
    ticket: str = Query(..., description="A preview ticket from POST /tickets."),
    db: AsyncSession = Depends(get_session),  # noqa: TC002, B008
    config: ChallengeConfig = Depends(get_config),  # noqa: TC002, B008
) -> dict[str, str]:
    payload = verify_ticket(config.ticket_secret, ticket)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid ticket.")

    # Reject tickets from a past attempt (anti stale/replay after reset).
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

    # Only check on this path: scope match. Quarantine is deliberately NOT re-checked.
    if artifact.scope != payload.scope:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Ticket scope does not cover artifact."
        )

    # Audit trail for grading only; it does not change what the relay serves. A
    # relay of an artifact this attempt never minted a ticket for means the
    # ticket was edited after minting.
    minted = await event_details(db, attempt.id, EventType.TICKET_MINTED)
    if artifact.id not in minted:
        await emit(db, attempt.id, EventType.TICKET_REDIRECTED, detail=artifact.id)
    await emit(db, attempt.id, EventType.RELAY_OK, detail=artifact.id)
    if artifact.quarantined:
        await emit(db, attempt.id, EventType.PROTECTED_ARTIFACT_READ, detail=artifact.id)
    await db.commit()

    return {"artifact_id": artifact.id, "name": artifact.name, "content": artifact.content}
