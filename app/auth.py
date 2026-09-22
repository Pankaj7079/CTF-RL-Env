# Reviewer auth. Sessions are opaque bearer tokens tied to one attempt. There's
# no admin path — the challenge is about authorization logic, not stealing creds.

from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ChallengeConfig
from app.models import Session


async def create_reviewer_session(session: AsyncSession, attempt_id: str, username: str) -> Session:
    token = f"sess_{secrets.token_urlsafe(24)}"
    obj = Session(token=token, attempt_id=attempt_id, username=username, role="reviewer")
    session.add(obj)
    return obj


# Look up a session from the bearer token, tolerating the "Bearer " prefix.
async def resolve_session(session: AsyncSession, token: str | None) -> Session | None:
    if not token:
        return None
    token = token.removeprefix("Bearer ").strip()
    return (await session.execute(select(Session).where(Session.token == token))).scalars().first()


def check_credentials(config: ChallengeConfig, username: str, password: str) -> bool:
    # Constant-time compare to avoid a credential timing side channel.
    ok_user = secrets.compare_digest(username, config.reviewer_username)
    ok_pass = secrets.compare_digest(password, config.reviewer_password)
    return ok_user and ok_pass
