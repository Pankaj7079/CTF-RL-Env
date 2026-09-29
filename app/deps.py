# Shared FastAPI dependencies.

from __future__ import annotations

import secrets

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import resolve_session
from app.config import ChallengeConfig, get_config
from app.database import get_session
from app.models import Session


# Only the harness (env wrapper) holds the admin token; agent traffic never does.
async def require_admin(
    x_admin_token: str | None = Header(default=None),
    config: ChallengeConfig = Depends(get_config),  # noqa: B008
) -> None:
    supplied = (x_admin_token or "").encode()
    if not secrets.compare_digest(supplied, config.admin_token.encode()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin token required.")


# Require a valid reviewer session from the Authorization header, else 401.
async def require_session(
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_session),  # noqa: TC002, B008
) -> Session:
    session = await resolve_session(db, authorization)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Valid reviewer session required."
        )
    return session
