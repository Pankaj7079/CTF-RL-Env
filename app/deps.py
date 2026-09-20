"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import resolve_session
from app.database import get_session
from app.models import Session


async def require_session(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_session),  # noqa: TC002, B008
) -> Session:
    """Resolve and require a valid reviewer session from the Authorization header."""

    session = await resolve_session(db, authorization)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Valid reviewer session required."
        )
    return session
