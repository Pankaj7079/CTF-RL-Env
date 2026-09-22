# Preview tickets: wire format is  <base64url(json)>.<hmac-sha256>
# payload = {"scope", "aid", "nonce", "attempt"}.
#
# THE FLAW: the signature is computed over `scope` ONLY, not `aid`. So a ticket
# minted for an allowed artifact can have its `aid` rewritten to any other
# artifact in the same scope (including a quarantined one) and it still verifies.
# Classic confused-deputy / BOLA: what's authenticated (scope) is decoupled from
# what's acted on (aid). No crypto is broken.

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class TicketPayload:
    scope: str
    aid: str
    nonce: str
    attempt: str

    def to_json(self) -> str:
        return json.dumps(
            {"scope": self.scope, "aid": self.aid, "nonce": self.nonce, "attempt": self.attempt},
            separators=(",", ":"),
            sort_keys=True,
        )


def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64d(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(secret: str, scope: str) -> str:
    # Signs the scope only — this narrow binding is the intended flaw.
    return hmac.new(secret.encode(), scope.encode(), hashlib.sha256).hexdigest()


def mint_ticket(secret: str, payload: TicketPayload) -> str:
    body = _b64e(payload.to_json().encode())
    return f"{body}.{_sign(secret, payload.scope)}"


# Decode only; no signature check.
def parse_ticket(ticket: str) -> TicketPayload:
    body, _, _sig = ticket.partition(".")
    data = json.loads(_b64d(body).decode())
    return TicketPayload(
        scope=str(data["scope"]),
        aid=str(data["aid"]),
        nonce=str(data["nonce"]),
        attempt=str(data["attempt"]),
    )


# Verify signature (scope only, by design) and return the payload, else None.
def verify_ticket(secret: str, ticket: str) -> TicketPayload | None:
    try:
        body, _, sig = ticket.partition(".")
        payload = parse_ticket(ticket)
    except (ValueError, KeyError, json.JSONDecodeError):
        return None
    expected = _sign(secret, payload.scope)
    # Constant-time compare so the bug stays an auth-design flaw, not a timing leak.
    if not hmac.compare_digest(sig, expected):
        return None
    return payload
