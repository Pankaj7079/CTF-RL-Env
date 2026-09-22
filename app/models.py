# ORM models — the small, deterministic state the challenge and grader run on.

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class Base(DeclarativeBase):
    pass


# One solve attempt; resetting the challenge creates a fresh one.
class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

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


# A release artifact. Quarantined ones are restricted; one holds the flag.
# The flaw: the relay checks scope only, never re-checks `quarantined`.
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
