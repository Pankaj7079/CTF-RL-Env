"""Async SQLite engine plus attempt lifecycle (start, reset)."""

from __future__ import annotations

import secrets
import uuid
from collections.abc import AsyncIterator

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_config
from app.instance import build_instance
from app.logging_config import get_logger
from app.models import Artifact, Attempt, Base, ChallengeEvent, Session

log = get_logger(__name__)

_engine = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Build the process-wide engine on first use."""
    global _engine, _sessionmaker
    if _sessionmaker is None:
        _engine = create_async_engine(get_config().database_url, future=True)
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False)
    return _sessionmaker


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one AsyncSession per request."""
    async with get_sessionmaker()() as session:
        yield session


async def _start_attempt(session: AsyncSession, seed: int | None) -> Attempt:
    """Wipe all state and open a fresh attempt on the instance for ``seed``.

    Old sessions and tickets die with the old attempt id, so nothing earned in a
    previous attempt carries over.
    """
    seed = secrets.randbelow(2**31) if seed is None else seed
    flag, artifacts = build_instance(get_config(), seed)
    for model in (ChallengeEvent, Session, Artifact, Attempt):
        await session.execute(delete(model))
    attempt = Attempt(id=str(uuid.uuid4()), active=True, seed=seed, flag=flag)
    session.add_all([attempt, *artifacts])
    await session.commit()
    log.info("attempt.started", attempt_id=attempt.id, seed=seed, artifacts=len(artifacts))
    return attempt


async def init_db() -> None:
    """Create tables and make sure an attempt exists. Safe on every startup."""
    get_sessionmaker()
    assert _engine is not None
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with get_sessionmaker()() as session:
        await get_active_attempt(session)


async def get_active_attempt(session: AsyncSession) -> Attempt:
    """The attempt everything is currently graded against."""
    attempt = (
        (await session.execute(select(Attempt).where(Attempt.active.is_(True)))).scalars().first()
    )
    return attempt or await _start_attempt(session, None)


async def reset_challenge(seed: int | None = None) -> Attempt:
    """Start a clean attempt, on a random instance unless ``seed`` is given."""
    async with get_sessionmaker()() as session:
        return await _start_attempt(session, seed)
