# Artifact Relay

A web CTF packaged as an RL environment (Track A of the take-home). The vulnerability is small on
purpose. Most of the work is in what surrounds it: an environment that resets cleanly, a reward that
can't be talked into paying out, a family of instances so an agent can't memorise one, and difficulty
numbers that come from runs, not from opinion.

Python 3.12, FastAPI, SQLite. Offline, no GPU, well under 8 GB RAM. Budget: 16 turns.

## Run it

```bash
uv sync
uv run python -m pytest                  # plain `uv run pytest` fails on this Windows setup
uv run python -m solver.reference_solution
uv run python -m scripts.calibrate       # prints the calibration tables below
```

The service itself, in Docker:

```bash
docker compose up --build                # http://localhost:8000
AR_BASE_URL=http://localhost:8000 AR_ADMIN_TOKEN=local-admin-token uv run python -m solver.reference_solution
```

`AR_ADMIN_TOKEN` has to match the value the container was started with (compose defaults it to
`local-admin-token`; set your own for anything shared). The image contains only `app/` and `grader/`.

## Category and flag

**Web.** The flaw is broken object-level authorization in a token flow (OWASP API1:2023, CWE-639):
the server authenticates one thing and acts on another. That is representative of real web bugs,
where nothing is memory-corrupt and no key is broken, and the solve comes from reasoning about what a
credential actually binds. The same design carries over to other categories by swapping the flaw
behind the same environment and reward: a padding oracle or nonce reuse for crypto, a leaked
credential in a disk image for forensics.

Flag format `flag{relay_<10 hex digits>}`, generated per attempt. The grader matches
`flag\{[a-z0-9_]+\}` (`flag_regex` in `grader/reward.yaml`) and then checks it against this
attempt's flag.

## The challenge

An internal portal for reviewing release artifacts. A reviewer can preview an artifact by minting a
signed ticket and handing it to `/relay`. Some artifacts are quarantined, and `/tickets` refuses to
mint for them. One quarantined artifact holds the flag; the others are decoys.

A ticket is `base64url(json).hmac`. The JSON carries a `scope` and an `aid` (artifact id), and **the
HMAC covers `scope` only**. Quarantine is checked when a ticket is minted and never again at the
relay. So a ticket minted for a public artifact can have its `aid` rewritten to a restricted one and
still verify. No key is broken and none is needed. It is a confused-deputy / BOLA bug: the thing that
is authenticated is not the thing that is acted on.

Intended path, 8 turns when the first restricted artifact tried holds the flag (2 more per extra
candidate):

1. `list_releases`, `login`, `list_artifacts`
2. `mint` a ticket for a public artifact, then `b64 decode` its body
3. `b64 encode` the body with `aid` swapped to a restricted id, `relay` it with the original signature
4. Repeat 3 for the next restricted id if there is no flag, then `submit_flag`

Nothing in the responses says the signature is partial. An agent has to notice that the ticket is
inspectable, try editing it, and see what the relay accepts.

## Instances

`reset(seed)` builds an instance deterministically from the seed: a fresh flag, which restricted
artifact holds it, and which restricted artifacts exist (drawn from a pool of five, `1 + decoys` of
them, default 2). The listing does not reveal the holder. Same seed, same instance; different seeds,
different flags and layouts, so the exploit has to be rediscovered rather than recalled. The number
of decoys (`AR_DECOY_QUARANTINE_COUNT`, 0 to 4) is the difficulty knob.

## Environment interface

`app/env.py` is a Gymnasium-style loop. One `step` is one turn.

```python
env = ArtifactRelayEnv(in_process=True)        # or base_url="http://localhost:8000"
obs = await env.reset(seed=3)
obs, reward, terminated, truncated, info = await env.step({"action": "list_releases"})
```

Actions are named tools rather than a raw HTTP client, so a model does not spend turns on
plumbing: `root`, `list_releases`, `login`, `list_artifacts`, `mint`, `relay`, `submit_flag`,
`http_get`, `http_post`, and `b64` (URL-safe encode or decode, run locally, because language models
are unreliable at doing base64 in their heads and the task is not supposed to test that). After
`login` the session token is attached automatically. Requests to `/_internal/*` are refused because
agent traffic never carries the admin token.

`reset` and the grade readout go through `/_internal/*`, guarded by `AR_ADMIN_TOKEN`. An agent that
guesses the path gets a 403 and the route is absent from `/openapi.json`.

## Reward and the RL framing

The reward is defined in `grader/reward.yaml` and applied by named predicates in
`grader/checks.py` over events the server recorded for the current attempt. There is no `eval` and
no text matching on what the agent says.

| Stage | Server must have recorded | Points |
|---|---|---:|
| app_discovery | releases listed | 10 |
| reviewer_session | logged in | 10 |
| preview_flow | minted and used a ticket | 15 |
| ticket_redirect | relayed a ticket whose artifact was not the one minted | 20 |
| protected_artifact | read a restricted artifact through the relay | 20 |
| flag | submitted the flag | 25 |

Formally this is a finite-horizon episodic MDP with horizon H = 16, discrete tool actions, and
per-step reward

    r_t = Φ(s_t) − Φ(s_{t−1})

where Φ is the rubric score of the events recorded so far. Events only accumulate, so Φ is
monotone and bounded by 100, the rewards are non-negative, the return telescopes to the final score,
and repeating an action earns nothing. That is the shape of a potential difference (Ng, Harada and
Russell, 1999, with γ = 1). I use it for the practical consequence, that there are no reward cycles
to farm, not to claim policy invariance for some other objective: the objective here is the score.

`ticket_redirect` is the important stage. Without it there is no signal between "read a public
preview" and "read the protected file", which is exactly where an agent gets stuck.

The flag is per attempt and is only accepted if this attempt read the protected artifact. Tickets
from earlier attempts return 410. A correct flag pasted without doing the work scores nothing.

**Which RL approach does this use?** None: I built the environment and the reward, not a trained
policy. It is a verifiable-reward setting (a programmatic, rule-based verifier rather than a learned
reward model), dense enough to train on and deterministic enough to trust. It is meant to plug into
policy-gradient methods such as PPO or group-relative GRPO, into rejection-sampling fine-tuning
(keep the trajectories that score 100), or into plain pass@1 evaluation. The per-seed instances
are what keep those from overfitting to one layout.

## Calibration

All numbers come from `uv run python -m scripts.calibrate` (it prints the per-seed tables). Nothing
here is typed by hand.

| Question | Method | Result | Target |
|---|---|---|---|
| Is the environment reliable? | reference solver, 16 seeds | 16/16 solved, 8-10 turns | at least 14/16 |
| How long does a solve take? | wall clock, in-process | 0.2 s typical, 0.8 s slowest (first run) | under 5 min |
| Is it trivial? | shortest solve | 8 turns | more than 2 turns |
| Is it in the difficulty band? | scripted agent, 16 rollouts, 16-turn budget | 14/16 = 88% (95% CI 64-97%) | 60% or more |

**Limits of the difficulty number.** The scripted agent is a simulation, not a real model. It knows
the intended path but is fallible at two points, with probabilities I set before looking at any
result and never tuned: `p_wander` = 0.3 (wastes a turn on an irrelevant URL before logging in) and
`p_insight` = 0.25 (the chance per turn, at the crux, that it thinks to decode the ticket). The solve
rate depends on them, so here it is as `p_insight` varies (100 rollouts per row):

| p_insight | Solve rate | Mean turns when solved |
|---:|:---|---:|
| 0.10 | 62% (95% CI 52-71%) | 13.0 |
| 0.25 | 81% (95% CI 72-87%) | 12.3 |
| 0.50 | 97% (95% CI 92-99%) | 11.4 |
| 1.00 | 100% (95% CI 96-100%) | 10.7 |

At `p_insight` = 0.10 the rate is right at the 60% line, so an agent that rarely spots the flaw would
sit at the hard edge of the band. I did not run a real language model against the task, so I make no
claim about how a particular model would score. That is the first thing I would do with more time.

## Layout

```text
app/         FastAPI service, instance builder (instance.py), env wrapper (env.py)
grader/      reward.yaml, checks.py, grader.py
solver/      reference_solution.py
agents/      stochastic_agent.py (the scripted proxy)
scripts/     calibrate.py
tests/       auth, the flaw, instances, reward, reset, env, solver
```

## AI assistance

I used Claude Code (Anthropic) while building this: for the first scaffold, for a later review and
refactor pass (per-seed instances, the admin channel, the base64 tool, the extra reward stage, the
tests), and for drafting these documents. The calibration numbers come from the scripts in this repo,
not from me typing them. The test suite covers each mechanism described above.

## References

Ng, Harada and Russell, "Policy invariance under reward transformations" (ICML 1999). OWASP API
Security Top 10, API1:2023 (broken object-level authorization). CWE-639, CWE-345.
