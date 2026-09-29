# ORM models — the small, deterministic state the challenge and grader run on.

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class Base(DeclarativeBase):
    pass


# One solve attempt. Resetting creates a fresh one; `seed` fully determines the
# instance (which artifact holds the flag, and the flag itself), so a run can be
# reproduced from its logs.
class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    seed: Mapped[int] = mapped_column(Integer, default=0)
    flag: Mapped[str] = mapped_column(String(64), default="")

    events: Mapped[list[ChallengeEvent]] = relationship(
        back_populates="attempt", cascade="all, delete-orphan"
    )


# A reviewer session token, bound to exactly one attempt.
class Session(Base):
    __tablename__ = "sessions"

    token: Mapped[str] = mapped_column(String(48), primary_key=True)
    attempt_id: Mapped[str] = mapped_column(String(36), ForeignKey("attempts.id"), index=True)
    username: Mapped[str] = mapped_column(String(64))
    role: Mapped[str] = mapped_column(String(32), default="reviewer")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


# A release artifact. Quarantined ones are restricted; exactly one holds the flag.
class Artifact(Base):
    __tablename__ = "artifacts"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    release: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128))
    scope: Mapped[str] = mapped_column(String(64), index=True)
    quarantined: Mapped[bool] = mapped_column(Boolean, default=False)
    content: Mapped[str] = mapped_column(Text)


# Append-only, attempt-scoped events — the grader's only source of truth.
class ChallengeEvent(Base):
    __tablename__ = "challenge_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    attempt_id: Mapped[str] = mapped_column(String(36), ForeignKey("attempts.id"), index=True)
    type: Mapped[str] = mapped_column(String(48), index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    attempt: Mapped[Attempt] = relationship(back_populates="events")
