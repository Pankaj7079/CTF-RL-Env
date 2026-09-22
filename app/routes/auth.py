# /login — establish a reviewer session (reward stage 2).

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import check_credentials, create_reviewer_session
from app.config import ChallengeConfig, get_config
from app.database import get_active_attempt, get_session
from app.events import EventType, emit
from app.schemas import LoginRequest, LoginResponse

router = APIRouter(tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    db: AsyncSession = Depends(get_session),  # noqa: TC002, B008
    config: ChallengeConfig = Depends(get_config),  # noqa: TC002, B008
) -> LoginResponse:
    if not check_credentials(config, body.username, body.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials.")
    attempt = await get_active_attempt(db)
    session = await create_reviewer_session(db, attempt.id, body.username)
    await emit(db, attempt.id, EventType.SESSION_ESTABLISHED, detail=body.username)
    await db.commit()
    return LoginResponse(token=session.token, role=session.role)
