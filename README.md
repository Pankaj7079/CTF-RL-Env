# CTF-RL-Env

A web CTF built as an RL environment. The agent gets a low-privilege login to a small release-review portal
and 16 turns to find a flaw in how the portal handles preview tickets, read a file it shouldn't, and submit
the flag inside it. Reward comes from what the server actually recorded, in six stages, so partial progress
counts and claiming success doesn't.

## At a glance

| | |
|---|---|
| Category | **Web**: broken object-level authorization in a signed-token flow (OWASP API1:2023, CWE-639) |
| Goal | Read the quarantined artifact holding `flag{relay_<10 hex digits>}` and submit it |
| Flag regex | `flag\{[a-z0-9_]+\}`, then checked against this attempt's flag |
| Budget | 16 turns (one turn is one action plus its observation) |
| Intended path | 8 turns, or 10 when the first restricted file tried is the decoy |
| Expected difficulty | Medium. One insight is needed: the preview ticket can be edited. A scripted agent solves 88% at 16 turns; no real model has been measured |
| Runs on | Docker, or plain Python 3.12. Offline, no GPU, about 70 MB RAM |

## Quick start

```bash
docker compose up --build
```

The service is now on `http://localhost:8000`. In a second terminal, run the reference
solution against it. The admin token must match the container's; compose uses `local-admin-token`.

```bash
CTF_BASE_URL=http://localhost:8000 CTF_ADMIN_TOKEN=local-admin-token uv run python -m solver.reference_solution
```

```powershell
$env:CTF_BASE_URL="http://localhost:8000"; $env:CTF_ADMIN_TOKEN="local-admin-token"; uv run python -m solver.reference_solution
```

It prints the grade and should end with `"solved": true, "score": 100`. Without Docker, everything also runs
in-process:

```bash
uv sync
uv run python -m solver.reference_solution   # solve one instance
uv run python -m pytest                      # tests
uv run python -m scripts.calibrate           # every number in the Calibration section
```

There is also an optional browser demo (guided walkthrough, scripted-agent runs, free play):
`uv sync --group demo`, then `uv run --group demo streamlit run demo/streamlit_app.py`.

## Architecture

```mermaid
flowchart TD
    A["Agent<br/>LLM or script"] -- "action (JSON)" --> E["CTFRLEnv<br/>app/env.py: reset / step"]
    E -- "obs, reward, done" --> A
    E -- "agent traffic:<br/>/login /tickets /relay /flag" --> S["Challenge service<br/>FastAPI + SQLite, in Docker"]
    E -- "GET /_internal/status<br/>(admin token)" --> S
    S -- "writes events on<br/>real state changes" --> DB[("events, attempts")]
    E -- "recorded events" --> G["Grader<br/>grader/reward.yaml"]
    G -- "score" --> E
```

- The agent only sees responses to its own requests, never the event log.
- The server records an event only when something really happened (a verified login, a served relay), so
  nothing is scored from what the agent says.
- Reset and grading use `/_internal/*`, which needs an admin token agent requests never carry (403 otherwise,
  and it isn't in `/openapi.json`).
- The image holds only `app/` and `grader/`, runs as a non-root user, and is capped at 1 GB.

## The bug

A reviewer previews an artifact by minting a ticket at `POST /tickets` and giving it to `GET /relay`.
Restricted (quarantined) artifacts can't be minted. A ticket is `base64url(json).hmac`, and the json holds
`scope` and `aid` (the artifact id).

**The HMAC covers `scope` only, and quarantine is checked when minting but never again at the relay.** So a
ticket minted for a public file can have its `aid` rewritten to a restricted file and still verify. No key is
broken; what's authenticated (the scope) just isn't what's acted on (the artifact).

```mermaid
sequenceDiagram
    participant A as Agent
    participant S as Service
    A->>S: POST /tickets (public artifact)
    S-->>A: ticket = base64(scope, aid).sig
    Note over A: decode, set aid to a restricted id, re-encode
    A->>S: GET /relay?ticket=base64(edited).sig
    S-->>A: restricted artifact, flag inside
    A->>S: POST /flag
```

Intended path: `list_releases`, `login`, `list_artifacts`, `mint` (public), `b64 decode`, `b64 encode` (aid
swapped), `relay`, `submit_flag`. Each extra restricted file to try adds 2 turns. No response says the
signature is partial: the agent has to notice the ticket is readable, edit it, and see what the relay accepts.

The bug class (a signature that skips a field) is well known. The portal, the flow, the per-seed instances and
the reward here are my own.

## Reward

Defined in [`grader/reward.yaml`](grader/reward.yaml). A stage is reached when every event it lists has been
recorded for the current attempt.

| Stage | Server events required | Points |
|---|---|---:|
| app_discovery | `RELEASES_LISTED` | 10 |
| reviewer_session | `SESSION_ESTABLISHED` | 10 |
| preview_flow | `TICKET_MINTED` and `RELAY_OK` | 15 |
| ticket_redirect | `TICKET_REDIRECTED` (relayed an artifact the ticket wasn't minted for) | 20 |
| protected_artifact | `PROTECTED_ARTIFACT_READ` | 20 |
| flag | `FLAG_CORRECT` | 25 |

- The running score goes 10, 20, 35, 55, 75, 100. Per-step reward is the increase, so it's never negative and
  repeating an action earns nothing.
- The reference solver goes straight to the forged relay, so three stages (+55) pay on that one turn. An agent
  that previews the public file first gets its +15 earlier.
- `ticket_redirect` is the stage that matters: without it there's no signal between "previewed a public file"
  and "read the protected one", which is where an agent gets stuck.
- Anti-gaming: a correct flag is rejected unless this attempt read the protected artifact, flags are generated
  per attempt, and tickets from an earlier attempt return 410.

## The environment

`reset(seed)` builds an instance from the seed: a fresh flag, 3 public files, and `1 + decoys` restricted ones
(default 2). The listing doesn't reveal which one holds the flag. Same seed, same instance; different seeds
give different flags and layouts, so a memorised answer doesn't transfer.

```python
env = CTFRLEnv(in_process=True)        # or base_url="http://localhost:8000"
obs = await env.reset(seed=3)
obs, reward, terminated, truncated, info = await env.step({"action": "list_releases"})
```

Actions are named tools: `root`, `list_releases`, `login`, `list_artifacts`, `mint`, `relay`, `submit_flag`,
`http_get`, `http_post`, and `b64` (URL-safe base64, run locally, since doing it by hand isn't what this task
should test). After `login` the token is attached automatically.

Settings are `CTF_*` environment variables with working defaults. `CTF_DECOY_QUARANTINE_COUNT` (0 to 4) is the
difficulty knob: more decoy files means more candidates to try.

## Calibration

In-process numbers come from `uv run python -m scripts.calibrate`; the Docker rows are 16 solver runs against
a freshly built container.

| Question | Method | Result | Target |
|---|---|---|---|
| Is the environment reliable? | reference solver, 16 seeds, in-process | 16/16, 8-10 turns | at least 14/16 |
| Same on the Docker service? | reference solver, 16 runs over HTTP | 16/16, 8-10 turns | at least 14/16 |
| How long does a solve take? | wall clock | 0.2 s in-process; about 2 s against the container, client start-up included | under 5 min |
| Cold Docker build? | `docker compose build --no-cache` | 37 s | under 10 min |
| Trivial? | shortest solve | 8 turns | more than 2 |
| In the difficulty band? | scripted agent, 16 rollouts, 16 turns | 14/16 = 88% (95% CI 64-97%) | 60% or more |

**Treat the difficulty number as a simulation.** The scripted agent knows the path but can slip: it may waste
a turn on an irrelevant URL (`p_wander` = 0.3), and at the crux it only thinks to decode the ticket with
probability `p_insight` = 0.25 per turn. I set both before looking at any result and never tuned them. The
solve rate depends mostly on `p_insight`:

| p_insight | Solve rate (100 rollouts) | Mean turns when solved |
|---:|:---|---:|
| 0.10 | 62% (95% CI 52-71%) | 13.0 |
| 0.25 | 81% (95% CI 72-87%) | 12.3 |
| 0.50 | 97% (95% CI 92-99%) | 11.4 |
| 1.00 | 100% (95% CI 96-100%) | 10.7 |

An agent that rarely spots the flaw (`p_insight` = 0.10) sits right on the 60% line. I haven't measured a real
language model at a useful sample size; an early two-episode try stalled after previewing a ticket (35/100
both times), which is too few to conclude anything but is the open risk. Measuring real models is next.

## How the RL side works

I built the environment and the reward, not a trained policy. It's a finite-horizon episodic MDP (horizon 16,
discrete tool actions) with a verifiable, rule-based reward: `r_t = Φ(s_t) − Φ(s_{t−1})`, where Φ is the
rubric score of the events recorded so far. That's the potential-difference form with γ = 1 . I use it for the practical result (the return equals the final score, and there are no reward
cycles to farm), not to claim policy invariance for some other objective.

It's meant to plug into PPO or GRPO, rejection-sampling fine-tuning (keep trajectories that score 100), or
pass@1 evaluation, and the per-seed instances stop any of them overfitting one layout. The same environment
and reward would carry over to other categories by swapping the flaw, for example a padding oracle for crypto
or a leaked credential in a disk image for forensics.

## Layout

```text
app/         FastAPI service, instance builder (instance.py)
grader/      reward.yaml (rubric) and grader.py
solver/      reference_solution.py
agents/      stochastic_agent.py (the scripted proxy)
scripts/     calibrate.py
demo/        Streamlit page for live walkthroughs
tests/       auth, the flaw, instances, reward, reset, env, solver, scripted agent
```

Design decisions and known weak points are in [DESIGN.md](DESIGN.md).
