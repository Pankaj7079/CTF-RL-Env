# Design note

## What I built and why

A web CTF, Artifact Relay, packaged as an RL environment. The vulnerability is a confused-deputy
bug: preview tickets are HMAC-signed over `scope` but not over the artifact id, and quarantine is
enforced when a ticket is minted, not when it is used. I picked something an agent can reach only by
reasoning about what a token actually protects. The bug is small; the effort went into the parts that
decide whether the result is usable as training data.

## Decisions

**Reward from server events, as a potential difference.** The grader reads events the server
recorded for the current attempt, through named predicates listed in `reward.yaml`. Per-step reward
is the increase in the rubric score, so it is dense, non-negative and cannot be farmed by repeating
an action. I added a `ticket_redirect` stage after seeing that the original five stages left no
signal at the hard step (the jump from previewing a public file to reading a protected one).

**Anti-hacking.** A correct flag is rejected unless this attempt read the protected artifact. The
flag is generated per attempt. Old tickets return 410. `/_internal/*` (status, reset) needs an admin
token only the harness holds, and is absent from the OpenAPI schema, so an agent cannot read the
event log or reset the world.

**A family of instances, not one puzzle.** `reset(seed)` derives the flag, the number of decoys and
which restricted artifact holds the flag. The listing does not reveal the holder. A memorised
answer from one seed is worthless on the next.

**Tools shaped for models.** Actions are named tools, plus a local `b64` codec. Base64 is not what
this task is meant to test, and models are poor at it, so forcing it would make the measured
difficulty about the wrong skill. The exploit is still entirely the agent's to find: the prompt
never says the signature is partial.

**Two kinds of calibration evidence, kept apart.** A deterministic solver measures reliability
(16/16). A scripted agent gives a difficulty proxy, but it is a simulation whose result depends on
two probabilities I chose, so `scripts/calibrate.py` also sweeps one of them rather than presenting a
single number as fact.

## Weak points I know about

- The scripted agent is a proxy. Its solve rate says the task is reachable within budget by an agent
  with a given failure profile, not how a real model will do. I did not measure a real model.
- Every instance shares one vulnerability. The family varies data and layout, not structure.
- The ticket key is random per process, so the service must run as a single worker (or be given
  `AR_TICKET_SECRET`).

## With more time

Run real models through the environment and replace the scripted proxy with measured solve rates
across a few model sizes; add more flaw variants behind the same interface (token claim confusion,
mass assignment) so the family varies structure too; and do a training run (for example GRPO on the
per-seed instances) to check that the reward actually produces improvement, which so far I have
argued but not shown.
