"""Task generator (stretch) — turn one challenge into a family of instances.

The assignment and the JD both value *task generators*. Because a whole instance
is described by ``ChallengeConfig`` plus the seeded artifact set, generating a new
instance is just producing a new config: a new flag, ticket secret, scope, and
artifact identifiers, all derived deterministically from a seed. The environment,
grader, solver, and calibration harness are unchanged — only the data varies.

This script emits a ``.env`` file for a given seed; run the app with those values
to get a distinct-but-isomorphic instance. It demonstrates the design; wiring the
seed through the artifact ids end-to-end is listed as future work in the README.

Usage:
    uv run python scripts/generate_task.py --seed 4242
"""

from __future__ import annotations

import argparse
import hashlib


def _derive(seed: int) -> dict[str, str]:
    h = hashlib.sha256(str(seed).encode()).hexdigest()
    return {
        "AR_INSTANCE_SEED": str(seed),
        "AR_FLAG": f"flag{{artifact_relay_{h[:12]}}}",
        "AR_TICKET_SECRET": f"ar_ticket_key_{h[12:28]}",
        "AR_PROJECT_SCOPE": f"project:{['releng', 'platform', 'infra', 'apps'][seed % 4]}",
        "AR_REVIEWER_PASSWORD": f"review-{h[28:36]}",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate an Artifact Relay instance config.")
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()
    env = _derive(args.seed)
    print("# Artifact Relay instance — generated deterministically from seed")
    for key, value in env.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
