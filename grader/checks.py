# Stage checks — pure predicates over an attempt's event names. reward.yaml refers
# to these by name, so scoring never eval's arbitrary strings (a safety choice).

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


def ticket_redirected(events: set[str]) -> bool:
    return EventType.TICKET_REDIRECTED in events


def protected_artifact_read(events: set[str]) -> bool:
    return EventType.PROTECTED_ARTIFACT_READ in events


def flag_correct(events: set[str]) -> bool:
    return EventType.FLAG_CORRECT in events


# Maps the `check` name in reward.yaml to its predicate.
CHECKS: dict[str, CheckFn] = {
    "releases_listed": releases_listed,
    "session_established": session_established,
    "preview_flow_used": preview_flow_used,
    "ticket_redirected": ticket_redirected,
    "protected_artifact_read": protected_artifact_read,
    "flag_correct": flag_correct,
}


def get_check(name: str) -> CheckFn:
    return CHECKS[name]
