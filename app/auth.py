"""Reviewer authentication and session lookup.

Sessions are opaque bearer tokens bound to a single attempt. Credentials are the
low-privileged reviewer account; there is no admin path — the challenge is about
authorization logic, not credential theft.
"""

from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import ChallengeConfig
from app.models import Session


async def create_reviewer_session(session: AsyncSession, attempt_id: str, username: str) -> Session:
    """Create and persist a reviewer session for the current attempt."""

    token = f"sess_{secrets.token_urlsafe(24)}"
    obj = Session(token=token, attempt_id=attempt_id, username=username, role="reviewer")
    session.add(obj)
    return obj


async def resolve_session(session: AsyncSession, token: str | None) -> Session | None:
    """Return the ``Session`` for a bearer token, or ``None``."""

    if not token:
        return None
    token = token.removeprefix("Bearer ").strip()
    return (await session.execute(select(Session).where(Session.token == token))).scalars().first()


def check_credentials(config: ChallengeConfig, username: str, password: str) -> bool:
    """Constant-time credential check for the reviewer account."""

    ok_user = secrets.compare_digest(username, config.reviewer_username)
    ok_pass = secrets.compare_digest(password, config.reviewer_password)
    return ok_user and ok_pass
