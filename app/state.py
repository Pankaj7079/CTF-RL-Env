# Attempt state is a pure projection of the event log — never mutated directly,
# so the env and grader always agree and no reward can be faked.

from __future__ import annotations

from pydantic import BaseModel

from app.events import EventType


# Which milestones this attempt has reached.
class AttemptState(BaseModel):
    api_discovered: bool = False
    session_created: bool = False
    preview_flow_used: bool = False
    protected_artifact_accessed: bool = False
    flag_submitted: bool = False


# Turn a set of recorded event names into the boolean state.
def project_state(event_types: set[str]) -> AttemptState:
    return AttemptState(
        api_discovered=EventType.RELEASES_LISTED in event_types,
        session_created=EventType.SESSION_ESTABLISHED in event_types,
        # Preview flow = a ticket was minted AND successfully used on the relay.
        preview_flow_used=(
            EventType.TICKET_MINTED in event_types and EventType.RELAY_OK in event_types
        ),
        protected_artifact_accessed=EventType.PROTECTED_ARTIFACT_READ in event_types,
        flag_submitted=EventType.FLAG_CORRECT in event_types,
    )
