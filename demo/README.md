# Demo UI

A Streamlit page for showing the environment live in an interview. Not part of the graded
deliverable — the assignment doesn't ask for one, and it isn't needed to build, run, or grade the
challenge. It's a thin client over the exact `reset()` / `step()` interface in
[`app/env.py`](../app/env.py); it contains no exploit logic of its own beyond
[`guided_steps.py`](guided_steps.py), which mirrors `solver/reference_solution.py` one action at a
time. (The script is named `streamlit_app.py`, not `app.py`, because Streamlit puts the script's own
directory first on `sys.path` — a file named `app.py` there would shadow the project's `app` package.)

## Run it

```bash
uv sync --group demo
uv run --group demo streamlit run demo/streamlit_app.py
```

Opens at `http://localhost:8501`. By default it runs the challenge in-process, offline, in a scratch
SQLite file outside the repo — no Docker needed.

To point it at a running container instead:

```bash
docker compose up --build
AR_BASE_URL=http://localhost:8000 AR_ADMIN_TOKEN=local-admin-token uv run --group demo streamlit run demo/streamlit_app.py
```

## What it shows

- **Reset**, with a fixed or random seed, to start a fresh attempt — the same instance family the
  grader and tests use.
- **Score, turns, and the six rubric stages**, updating live from the server's event log, exactly as
  `grader/grader.py` computes them from `grader/reward.yaml`.
- **Guided walkthrough**: one button per step of the reference solution, showing the request sent
  and the response received before you advance.
- **Manual / free play**: send any single action yourself, with the raw JSON request and response.
- **Turn log**: every action taken this attempt, in order.
