# Task generator — one design, many instances. A whole instance is just a config,
# so a seed deterministically derives a new flag, secret, scope, and id salt. The
# env, grader, solver, and calibration are unchanged; only the data varies.
# Emits env vars for the seed:  uv run python scripts/generate_task.py --seed 4242

from __future__ import annotations

import argparse
import hashlib


# Derive one instance's config from a seed.
def _derive(seed: int) -> dict[str, str]:
    h = hashlib.sha256(str(seed).encode()).hexdigest()
    return {
        "AR_INSTANCE_SEED": str(seed),
        "AR_FLAG": f"flag{{artifact_relay_{h[:12]}}}",
        "AR_TICKET_SECRET": f"ar_ticket_key_{h[12:28]}",
        "AR_PROJECT_SCOPE": f"project:{['releng', 'platform', 'infra', 'apps'][seed % 4]}",
        "AR_REVIEWER_PASSWORD": f"review-{h[28:36]}",
        # id_salt varies every artifact/release identifier for this instance.
        "AR_ID_SALT": h[36:42],
        # keep difficulty in-band across instances (1 decoy => ~75% reference solve).
        "AR_DECOY_QUARANTINE_COUNT": "1",
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
