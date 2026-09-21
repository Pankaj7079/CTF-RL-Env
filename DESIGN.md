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
*reliability* (16/16 solves, <1.5 s each) — it must succeed every time or the reward would reflect
flaky infra, not skill. A **seeded, fallible reference agent** measures *difficulty*: at the 16-turn
budget it solves **75%** (centered in the assignment's ≥60% band), and a turn-budget sweep
(75→62→44→19% at 16→12→10→8) shows a real gradient that collapses only as the budget approaches the
~8-turn solution length. Difficulty is tuned by two honest levers — the number of *decoy* restricted
artifacts (the agent must find which one holds the flag) and the modeled solver competence — then
re-measured; nothing is hand-set. Every number is produced by `scripts/calibrate.py`.

## Trade-offs
The scripted agent is offline/free/reproducible for calibration; a real **LLM agent**
(`agents/llm_agent.py`, via Groq's free tier) uses the *same* `env.step()` interface to
cross-check it. I fixed the flag and seed for deterministic grading, and kept the domain small (one
flaw, a handful of artifacts) so the whole design is explainable in the walkthrough.

## Extending to other CTF categories (bonus)
The environment/grader/reward split is category-agnostic: only the challenge service and the
observable events change. A **crypto** task would emit `KEYSTREAM_RECOVERED` / `PLAINTEXT_DECRYPTED`
milestones; a **rev** task `FUNCTION_IDENTIFIED` / `CHECK_BYPASSED`; a **pwn** task `CRASH_TRIGGERED`
/ `LEAK_OBTAINED` / `SHELL` (mapping cleanly onto the Track-B basic/intermediate/advanced tiers). Each
reuses `reset()`/`step()`, the machine-readable `reward.yaml`, the event-backed grader, and the
two-agent calibration unchanged — which is exactly what makes this a task *family*, not one puzzle.

## Next steps
Thread the instance seed through artifact **identifiers** end-to-end (started via `id_salt` +
`scripts/generate_task.py`); add sibling web flaws (JWT claim confusion, mass-assignment) behind the
same interface; and run the LLM agent across several open models to chart solve-rate vs model size.
