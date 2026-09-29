# Artifact Relay

A web CTF (Track A) packaged as a resettable RL environment. An agent gets a low-privilege reviewer
account on a small release-review portal and has 16 turns to find the flaw and read a restricted file
that holds the flag. A programmatic grader scores progress in six stages, so the reward is dense and
cannot be gamed by talking.

## At a glance

| | |
|---|---|
| Category | **Web**: broken object-level authorization in a signed-token flow (OWASP API1:2023, CWE-639) |
| Goal | Read the quarantined artifact holding `flag{relay_<10 hex digits>}` and submit it |
| Flag regex | `flag\{[a-z0-9_]+\}` (`flag_regex` in `grader/reward.yaml`), then checked against this attempt's flag |
| Budget | 16 turns. One turn is one action plus its observation |
| Intended path | 8 turns (10 when the first restricted file tried is the decoy) |
| Expected difficulty | Medium: one insight is needed (the ticket can be edited). Scripted agent solves 88% at 16 turns; not measured on a real language model |
| Stack | Python 3.12, FastAPI, SQLite. Offline, no GPU, about 70 MB RAM in the container |

## Quick start

```bash
docker compose up --build              # challenge service on http://localhost:8000
```

Run the reference solution against the container (the token must match the one the container uses;
compose defaults it to `local-admin-token`):

```bash
AR_BASE_URL=http://localhost:8000 AR_ADMIN_TOKEN=local-admin-token uv run python -m solver.reference_solution
```

```powershell
$env:AR_BASE_URL="http://localhost:8000"; $env:AR_ADMIN_TOKEN="local-admin-token"; uv run python -m solver.reference_solution
```

Without Docker (everything runs in-process, offline):

```bash
uv sync
uv run python -m solver.reference_solution   # solves one instance, prints the grade
uv run python -m pytest                      # test suite
uv run python -m scripts.calibrate           # prints every number in the Calibration section
```

Optional browser demo (guided walkthrough, scripted-agent runs, free play; not part of grading):
`uv run --group demo streamlit run demo/streamlit_app.py`

## Architecture

```mermaid
flowchart TD
    A["Agent<br/>LLM or script"] -- "action (JSON)" --> E["ArtifactRelayEnv<br/>app/env.py: reset / step"]
    E -- "obs, reward, done" --> A
    E -- "agent traffic:<br/>/login /tickets /relay /flag" --> S["Challenge service<br/>FastAPI + SQLite, in Docker"]
    E -- "GET /_internal/status<br/>(admin token)" --> S
    S -- "writes events on<br/>real state changes" --> DB[("events, attempts")]
    E -- "recorded events" --> G["Grader<br/>grader/reward.yaml"]
    G -- "score" --> E
```

- The agent only sees responses to its own requests. It never sees the event log.
- The server writes an event only when the thing really happened (a verified login, a served relay). Nothing
  is scored from what the agent says.
- Reset and grading use `/_internal/*`, which needs an admin token that agent requests never carry. An
  agent that guesses the path gets 403, and the route is absent from `/openapi.json`.
- The Docker image holds only `app/` and `grader/`, runs as a non-root user, and is capped at 1 GB. The solver,
  agents and tests stay out of it.

## The vulnerability

A reviewer previews an artifact by minting a ticket at `POST /tickets` and giving it to `GET /relay`.
Restricted (quarantined) artifacts cannot be minted. A ticket is `base64url(json).hmac`, where the json
holds `scope` and `aid` (the artifact id).

**The HMAC covers `scope` only, and quarantine is checked when minting but never again at the relay.** A
ticket minted for a public file can have its `aid` rewritten to a restricted file and still verify. No key
is broken. What is authenticated (the scope) is not what is acted on (the artifact).

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
swapped), `relay`, `submit_flag`. Each extra restricted file to try adds 2 turns. Nothing in any response says
the signature is partial: the agent has to notice the ticket is inspectable, edit it, and see what the relay
accepts.

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
| ticket_redirect | `TICKET_REDIRECTED` (relayed an artifact the ticket was not minted for) | 20 |
| protected_artifact | `PROTECTED_ARTIFACT_READ` | 20 |
| flag | `FLAG_CORRECT` | 25 |

Cumulative score after each stage is 10, 20, 35, 55, 75, 100, so credit is strictly increasing toward the
goal. The per-step reward is the increase in the score, so it is never negative and repeating an action earns
nothing. The reference solver goes straight to the forged relay, so three stages (+55) pay on that one turn; an
agent that first previews the public file gets its +15 earlier.

`ticket_redirect` is the stage that matters. Without it there is no signal between "previewed a public
file" and "read the protected one", which is where an agent gets stuck.

Anti-gaming: a correct flag is rejected unless this attempt read the protected artifact. The flag is generated
per attempt. Tickets from an earlier attempt return 410.

## Environment

`reset(seed)` builds an instance from the seed: a fresh flag, and which restricted file holds it. There are 3
public files and `1 + decoys` restricted ones (default 2, set by `AR_DECOY_QUARANTINE_COUNT`, 0 to 4). The
listing does not reveal the holder. Same seed gives the same instance; different seeds give different flags and
layouts, so a memorised answer does not transfer.

```python
env = ArtifactRelayEnv(in_process=True)        # or base_url="http://localhost:8000"
obs = await env.reset(seed=3)
obs, reward, terminated, truncated, info = await env.step({"action": "list_releases"})
```

Actions are named tools: `root`, `list_releases`, `login`, `list_artifacts`, `mint`, `relay`, `submit_flag`,
`http_get`, `http_post`, and `b64` (URL-safe encode or decode, run locally, because base64 by hand is a poor
thing for a task like this to test). After `login` the session token is attached automatically.

## Calibration

The in-process numbers come from `uv run python -m scripts.calibrate`. The Docker rows are 16 runs of
`solver.reference_solution` against a freshly built container.

| Question | Method | Result | Target |
|---|---|---|---|
| Is the environment reliable? | reference solver, 16 seeds, in-process | 16/16, 8-10 turns | at least 14/16 |
| Same, on the Docker service? | reference solver, 16 runs over HTTP | 16/16, 8-10 turns | at least 14/16 |
| How long does a solve take? | wall clock | 0.2 s in-process; about 2 s per run against the container, client start-up included | under 5 min |
| Cold Docker build? | `docker compose build --no-cache` | 37 s | under 10 min |
| Trivial? | shortest solve | 8 turns | more than 2 |
| In the difficulty band? | scripted agent, 16 rollouts, 16-turn budget | 14/16 = 88% (95% CI 64-97%) | 60% or more |

**The difficulty number is a simulation.** The scripted agent knows the path but is fallible at two points, with
probabilities I set before looking at results and did not tune: `p_wander` = 0.3 (wastes a turn on an irrelevant
URL before logging in) and `p_insight` = 0.25 (the chance per turn, at the crux, that it thinks to decode the
ticket). Its solve rate depends on them:

| p_insight | Solve rate (100 rollouts) | Mean turns when solved |
|---:|:---|---:|
| 0.10 | 62% (95% CI 52-71%) | 13.0 |
| 0.25 | 81% (95% CI 72-87%) | 12.3 |
| 0.50 | 97% (95% CI 92-99%) | 11.4 |
| 1.00 | 100% (95% CI 96-100%) | 10.7 |

At `p_insight` = 0.10 the rate sits right at the 60% line, so an agent that rarely spots the flaw would be at
the hard edge of the band. I have not measured a real language model at a meaningful sample size. An early
two-episode try with a hosted model stopped after previewing a ticket (35/100 both times); that is far too few
to conclude anything, and I did not keep that tooling in this repo, but it is the open risk for this task.
Measuring real models is the first thing I would do with more time.

## Which RL approach does this use?

None: I built the environment and the reward, not a trained policy. It is a finite-horizon episodic MDP (horizon
16, discrete tool actions) with a verifiable, rule-based reward. The per-step reward is
`r_t = Φ(s_t) − Φ(s_{t−1})`, where Φ is the rubric score of the events recorded so far, in the form of a
potential difference with γ = 1 (Ng, Harada and Russell, 1999). I use that form for its practical consequence,
that the return equals the final score and there are no reward cycles to farm, not to claim policy invariance for
some other objective. It is meant to plug into PPO or GRPO, rejection-sampling fine-tuning (keep trajectories that
score 100), or pass@1 evaluation, and the per-seed instances stop those from overfitting to one layout.

The same design extends to other categories by swapping the flaw behind the same environment and reward: a
padding oracle or nonce reuse for crypto, a leaked credential in a disk image for forensics.

## Layout

```text
app/         FastAPI service, instance builder (instance.py), env wrapper (env.py)
grader/      reward.yaml (rubric) and grader.py
solver/      reference_solution.py
agents/      stochastic_agent.py (the scripted proxy)
scripts/     calibrate.py
demo/        Streamlit page for live walkthroughs (optional)
tests/       auth, the flaw, instances, reward, reset, env, solver, scripted agent
```

Design decisions and known weak points are in [DESIGN.md](DESIGN.md).

## AI assistance

I used Claude Code (Anthropic) while building this: for the first scaffold, for a later review and refactor pass
(per-seed instances, the admin channel, the base64 tool, the extra reward stage, the tests), and for drafting
these documents. The calibration numbers come from the scripts in this repo, not from me typing them, and the
test suite covers each mechanism described above.

## References

Ng, Harada and Russell, "Policy invariance under reward transformations" (ICML 1999). OWASP API Security Top 10,
API1:2023 (broken object-level authorization). CWE-639, CWE-345.
