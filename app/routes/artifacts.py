"""Artifact metadata route (requires a reviewer session).

Lists artifact metadata including the quarantined artifact — the agent can see
that a restricted object exists and learn its id, but cannot mint a ticket for it
directly (see ``tickets.py``). Content is never served here; only via the relay.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.deps import require_session
from app.models import Artifact, Session
from app.schemas import ArtifactInfo, ArtifactsResponse

router = APIRouter(tags=["artifacts"])


@router.get("/artifacts", response_model=ArtifactsResponse)
async def list_artifacts(
    release: str | None = None,
    _session: Session = Depends(require_session),  # noqa: TC002, B008
    db: AsyncSession = Depends(get_session),  # noqa: TC002, B008
) -> ArtifactsResponse:
    """List artifact metadata, optionally filtered by release."""

    stmt = select(Artifact)
    if release:
        stmt = stmt.where(Artifact.release == release)
    artifacts = (await db.execute(stmt.order_by(Artifact.id))).scalars().all()
    return ArtifactsResponse(
        artifacts=[
            ArtifactInfo(
                id=a.id,
                release=a.release,
                name=a.name,
                scope=a.scope,
                status="quarantined" if a.quarantined else "available",
            )
            for a in artifacts
        ]
    )
