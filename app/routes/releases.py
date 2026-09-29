# /releases — discovery surface (app_discovery stage). Unauthenticated on purpose, but
# listing emits RELEASES_LISTED for the active attempt.

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_active_attempt, get_session
from app.events import EventType, emit
from app.models import Artifact
from app.schemas import ReleaseInfo, ReleasesResponse

router = APIRouter(tags=["releases"])


@router.get("/releases", response_model=ReleasesResponse)
async def list_releases(
    db: AsyncSession = Depends(get_session),  # noqa: TC002, B008
) -> ReleasesResponse:
    artifacts = (await db.execute(select(Artifact))).scalars().all()
    counts = Counter(a.release for a in artifacts)
    attempt = await get_active_attempt(db)
    await emit(db, attempt.id, EventType.RELEASES_LISTED, detail=",".join(sorted(counts)))
    await db.commit()
    releases = [ReleaseInfo(release=r, artifact_count=c) for r, c in sorted(counts.items())]
    return ReleasesResponse(releases=releases)
