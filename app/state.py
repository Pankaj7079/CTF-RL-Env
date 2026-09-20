"""Derive attempt state from the event log.

State is a pure projection of the append-only event log — never mutated
directly. This guarantees the grader and the environment agree on progress and
that no reward can be granted without a real, recorded transition.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.events import EventType


class AttemptState(BaseModel):
    """Boolean projection of milestones reached in one attempt."""

    api_discovered: bool = False
    session_created: bool = False
    preview_flow_used: bool = False
    protected_artifact_accessed: bool = False
    flag_submitted: bool = False


def project_state(event_types: set[str]) -> AttemptState:
    """Project a set of recorded event type names into an ``AttemptState``."""

    return AttemptState(
        api_discovered=EventType.RELEASES_LISTED in event_types,
        session_created=EventType.SESSION_ESTABLISHED in event_types,
        preview_flow_used=(
            EventType.TICKET_MINTED in event_types and EventType.RELAY_OK in event_types
        ),
        protected_artifact_accessed=EventType.PROTECTED_ARTIFACT_READ in event_types,
        flag_submitted=EventType.FLAG_CORRECT in event_types,
    )
