"""Code-backed stage checks.

Each check is a pure predicate over the set of event-type names recorded for an
attempt. The rubric (``reward.yaml``) references these by name, so scoring never
evaluates arbitrary strings — a deliberate safety choice.
"""

from __future__ import annotations

from collections.abc import Callable

from app.events import EventType

CheckFn = Callable[[set[str]], bool]


def releases_listed(events: set[str]) -> bool:
    return EventType.RELEASES_LISTED in events


def session_established(events: set[str]) -> bool:
    return EventType.SESSION_ESTABLISHED in events


def preview_flow_used(events: set[str]) -> bool:
    return EventType.TICKET_MINTED in events and EventType.RELAY_OK in events


def protected_artifact_read(events: set[str]) -> bool:
    return EventType.PROTECTED_ARTIFACT_READ in events


def flag_correct(events: set[str]) -> bool:
    return EventType.FLAG_CORRECT in events


CHECKS: dict[str, CheckFn] = {
    "releases_listed": releases_listed,
    "session_established": session_established,
    "preview_flow_used": preview_flow_used,
    "protected_artifact_read": protected_artifact_read,
    "flag_correct": flag_correct,
}


def get_check(name: str) -> CheckFn:
    """Look up a check predicate by name, raising ``KeyError`` if unknown."""

    return CHECKS[name]
