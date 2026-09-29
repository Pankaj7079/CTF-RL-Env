# /tickets — mint a preview ticket (first half of preview_flow). This path DOES
# enforce the quarantine policy; the relay path is the one that forgets to.

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ChallengeConfig, get_config
from app.database import get_session
from app.deps import require_session
from app.events import EventType, emit
from app.models import Artifact, Session
from app.schemas import MintRequest, MintResponse
from app.tickets import TicketPayload, mint_ticket

router = APIRouter(tags=["tickets"])


@router.post("/tickets", response_model=MintResponse)
async def mint_preview_ticket(
    body: MintRequest,
    session: Session = Depends(require_session),  # noqa: TC002, B008
    db: AsyncSession = Depends(get_session),  # noqa: TC002, B008
    config: ChallengeConfig = Depends(get_config),  # noqa: TC002, B008
) -> MintResponse:
    artifact = (
        (await db.execute(select(Artifact).where(Artifact.id == body.artifact_id)))
        .scalars()
        .first()
    )
    if artifact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No such artifact.")
    if artifact.scope != config.project_scope:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Scope not permitted.")
    # Quarantine policy is enforced at mint time only.
    if artifact.quarantined:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Artifact is quarantined; preview tickets cannot be minted for it.",
        )

    payload = TicketPayload(
        scope=artifact.scope,
        aid=artifact.id,
        nonce=secrets.token_hex(8),
        attempt=session.attempt_id,
    )
    ticket = mint_ticket(config.ticket_secret, payload)
    await emit(db, session.attempt_id, EventType.TICKET_MINTED, detail=artifact.id)
    await db.commit()
    return MintResponse(
        ticket=ticket,
        scope=artifact.scope,
        note="Present this ticket to GET /relay?ticket=... to preview the artifact.",
    )
