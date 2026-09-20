# Design Note — Artifact Relay (1 page)

## Problem
I chose to demonstrate the skill the role actually hires for: turning an interactive task into a
*reliable, measurable RL environment*. A single vulnerable web app is easy; the hard, valuable part
is making an agent's progress **observable, reproducible, and scorable** without trusting the agent's
own words. So the challenge is deliberately a clean multi-step authorization task, and most of the
engineering is in the environment, verifier, reward, reset, and calibration around it.

## Environment
FastAPI + SQLite + Docker, wrapped in a Gymnasium-style `reset()`/`step()` interface where one step is
exactly one turn (one action + observation), matching the assignment's 16-turn definition. SQLite
gives deterministic, resettable state without external services; the env can run fully in-process over
an ASGI transport, so calibration and tests need **no network and no GPU** and are byte-for-byte
reproducible. State is a pure projection of an append-only event log, so the environment and grader
can never disagree about what happened.

## The vulnerability
An original confused-deputy / broken-object-level-authorization bug: preview tickets are HMAC-signed
over the `scope` field only, while the relay serves whatever `aid` the ticket names (checking only
that its scope matches and that quarantine is enforced *at mint time, not at relay time*). The agent
must reason that the signed thing (scope) is decoupled from the acted-on thing (artifact id) and
redirect a legitimately-minted ticket to the quarantined artifact — no cryptography is broken and no
secret is needed, which is precisely why the design is dangerous and instructive. It generalizes
across web/API tasks (IDOR, mass-assignment, JWT claim confusion) far better than a one-off puzzle.

## Reward design
Five cumulative, strictly-monotonic stages (10/15/20/25/30 = 100), expressed in a machine-readable
`reward.yaml` and scored by code-backed predicates over the event set (no `eval`). Dense intermediate
reward matters because a flag-only signal is far too sparse for a long-horizon agent: here the agent
gets observable credit for discovery, authentication, using the preview flow, and reaching the
protected artifact, while the final objective is unchanged.

## Verification / anti-reward-hacking
The grader keys only off server-emitted, attempt-scoped events. A correct flag string is rejected
unless the attempt genuinely read the protected artifact through the relay; the flag never appears in
HTML/JS/errors; and tickets are attempt-bound so stale or cross-attempt state returns `410` and earns
nothing. This is the line between usable RL data and a writeup.

## Calibration
Two *separate* agents, by design. A **deterministic reference solver** measures environment
*reliability* (16/16 solves, <1 s each) — it must succeed every time or the reward would reflect flaky
infra, not skill. A **seeded, fallible reference agent** measures *difficulty*: at the 16-turn budget
it solves ~88% (inside the assignment's ≥60% band), and a turn-budget sweep (88→81→62→19% at
16→12→10→8) shows a real gradient that collapses only as the budget approaches the 8-turn solution
length. Every number is measured by `scripts/calibrate.py`; none is hand-set.

## Trade-offs
I kept the reference agent scripted rather than LLM-driven so calibration is offline, free, and
reproducible for this deadline; the same `env.step()` interface accepts a drop-in LLM agent. I fixed
the flag and seed data for deterministic grading, and kept the domain small (4 artifacts, one flaw) so
the whole design is explainable in the walkthrough.

## Next steps
Thread the instance seed through artifact **identifiers** so `scripts/generate_task.py` yields a full
*family* of isomorphic instances; add sibling flaws (JWT claim confusion, mass-assignment) behind the
same env/grader interface; and swap in an LLM reference agent to cross-check the scripted calibration.
