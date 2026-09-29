"""Interactive demo of the Artifact Relay environment — same reset()/step() the
grader and reference solver use, driven from a browser instead of a script.

Not part of the graded deliverable: it exists to make the interview walkthrough
easier to follow. See demo/README.md for how to run it.

    uv run --group demo streamlit run demo/streamlit_app.py
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

import streamlit as st

# Must be set before app.config is imported anywhere, so the demo never touches
# the same database file as `uv run python -m pytest` or a real docker run.
os.environ.setdefault(
    "AR_DATABASE_URL",
    f"sqlite+aiosqlite:///{Path(tempfile.gettempdir()) / 'artifact_relay_demo.db'}",
)

from app.env import ArtifactRelayEnv  # noqa: E402
from scripts.calibrate import P_INSIGHT, P_WANDER, rollouts  # noqa: E402

from demo.guided_steps import guided_walkthrough  # noqa: E402
from grader.grader import load_rubric  # noqa: E402

RUBRIC = load_rubric()

st.set_page_config(page_title="Artifact Relay — live demo", layout="wide")


# --- one background event loop per browser session, so the httpx client (and
# its connection state / auth token) survives across Streamlit's reruns -------
def _loop() -> asyncio.AbstractEventLoop:
    if "loop" not in st.session_state:
        loop = asyncio.new_event_loop()
        threading.Thread(target=loop.run_forever, daemon=True).start()
        st.session_state.loop = loop
    return st.session_state.loop


def run_async(coro: Any) -> Any:
    return asyncio.run_coroutine_threadsafe(coro, _loop()).result()


def get_env() -> ArtifactRelayEnv:
    if "env" not in st.session_state:
        base_url = os.environ.get("AR_BASE_URL")
        st.session_state.env = ArtifactRelayEnv(base_url=base_url, in_process=base_url is None)
        st.session_state.target = base_url or "in-process (offline, no Docker needed)"
    return st.session_state.env


def log_step(action: dict, obs: dict, reward: int) -> None:
    st.session_state.log.append(
        {
            "turn": obs["turns_used"],
            "action": action.get("action"),
            "ok": obs.get("ok"),
            "status": obs.get("status"),
            "reward": reward,
            "score_after": obs["grade"]["score"],
        }
    )
    st.session_state.last_action = action
    st.session_state.last_obs = obs


def do_reset(seed: int | None) -> None:
    obs = run_async(get_env().reset(seed=seed))
    st.session_state.obs = obs
    st.session_state.log = []
    st.session_state.last_action = None
    st.session_state.last_obs = obs
    st.session_state.guided_gen = None
    st.session_state.guided_step = None


def do_step(action: dict) -> None:
    env = get_env()
    obs, reward, terminated, truncated, _info = run_async(env.step(action))
    st.session_state.obs = obs
    log_step(action, obs, reward)
    if terminated or truncated:
        st.session_state.guided_step = None


st.title("Artifact Relay — live demo")
st.caption(
    "The reviewer portal used for the CTF, driven through the same `reset()` / `step()` "
    "interface the grader and reference solver use — nothing here is a separate mock."
)

with st.sidebar:
    st.header("Instance")
    seed_fixed = st.checkbox("Fixed seed", value=True)
    seed = st.number_input("Seed", min_value=0, value=0, step=1) if seed_fixed else None
    if st.button("Reset", type="primary", use_container_width=True):
        do_reset(seed)
    if "obs" in st.session_state:
        st.caption(f"Target: {st.session_state.target}")
        st.caption(f"Attempt seed: {st.session_state.obs['seed']}")

if "obs" not in st.session_state:
    st.info("Click **Reset** in the sidebar to start an attempt.")
    st.stop()

obs = st.session_state.obs
grade = obs["grade"]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Score", f"{grade['score']} / {grade['max_score']}")
col2.metric("Turns used", f"{obs['turns_used']} / {get_env().turn_budget}")
col3.metric("Turns left", obs["turns_left"])
col4.metric("Solved", "yes" if grade["solved"] else "no")

st.subheader("Rubric stages")
reached = set(grade["reached"])
cols = st.columns(len(RUBRIC.stages))
for col, stage in zip(cols, RUBRIC.stages, strict=True):
    mark = "✅" if stage.id in reached else "⬜"
    col.markdown(f"{mark} **{stage.id}**\n\n{stage.score} pts")

tab_guided, tab_agent, tab_manual, tab_log = st.tabs(
    ["Guided walkthrough", "Scripted agent (16 seeds)", "Manual / free play", "Turn log"]
)

with tab_guided:
    st.write(
        "Steps through the reference exploit one HTTP call at a time — the same path "
        "`solver/reference_solution.py` runs, paused so each request and response can "
        "be read before the next one fires."
    )
    if st.session_state.get("guided_step") is None and not grade["solved"]:
        if st.button("Start guided walkthrough"):
            user, password = get_env().reviewer_credentials()
            gen = guided_walkthrough(user, password)
            st.session_state.guided_gen = gen
            st.session_state.guided_step = next(gen)

    step = st.session_state.get("guided_step")
    if step is not None:
        label, explain, action = step
        st.markdown(f"**Next: {label}**")
        st.caption(explain)
        st.json(action)
        if st.button("Run this step ▶", type="primary"):
            env = get_env()
            prev_score = obs["grade"]["score"]
            new_obs, reward, terminated, truncated, _info = run_async(env.step(action))
            st.session_state.obs = new_obs
            log_step(action, new_obs, reward)
            try:
                st.session_state.guided_step = st.session_state.guided_gen.send(new_obs)
            except StopIteration:
                st.session_state.guided_step = None
            st.rerun()
    elif grade["solved"]:
        st.success(f"Solved — score {grade['score']}/{grade['max_score']}.")
    elif "guided_gen" in st.session_state and st.session_state.guided_gen is not None:
        st.warning("Walkthrough ended without a flag (unexpected — check the server logs).")

with tab_agent:
    st.write(
        "A fallible scripted agent on 16 different instances, the same run `scripts/calibrate.py` "
        f"reports. It sometimes wastes a turn on an irrelevant URL (p_wander = {P_WANDER}) and "
        f"only has a {P_INSIGHT:.0%} chance per turn of thinking to decode the ticket "
        "(p_insight), so turns and outcomes vary. It is a simulation, not a real model."
    )
    if st.button("Run 16 rollouts"):
        with st.spinner("Running 16 episodes..."):
            st.session_state.agent_results = run_async(rollouts(16, P_WANDER, P_INSIGHT))
        do_reset(seed)  # the rollouts used the same database, so start a clean attempt
        st.rerun()
    results = st.session_state.get("agent_results")
    if results:
        solved = [r for r in results if r.solved]
        m1, m2 = st.columns(2)
        m1.metric("Solved", f"{len(solved)} / {len(results)}")
        mean_turns = sum(r.turns_used for r in solved) / len(solved) if solved else None
        m2.metric("Mean turns when solved", "-" if mean_turns is None else f"{mean_turns:.1f}")
        st.dataframe(
            [
                {
                    "seed": i,
                    "solved": r.solved,
                    "turns": r.turns_used,
                    "reward": r.reward,
                    "highest stage": r.highest_stage or "-",
                    "outcome": r.failure_reason,
                }
                for i, r in enumerate(results)
            ],
            use_container_width=True,
            hide_index=True,
        )

with tab_manual:
    st.write("Send any single action yourself, exactly as an agent would.")
    kind = st.selectbox(
        "Action",
        [
            "root",
            "list_releases",
            "login",
            "list_artifacts",
            "mint",
            "relay",
            "submit_flag",
            "http_get",
            "http_post",
            "b64",
        ],
    )
    action: dict[str, Any] = {"action": kind}
    if kind == "login":
        user, password = get_env().reviewer_credentials()
        action["username"] = st.text_input("username", user)
        action["password"] = st.text_input("password", password)
    elif kind == "mint":
        action["artifact_id"] = st.text_input("artifact_id")
    elif kind == "relay":
        action["ticket"] = st.text_input("ticket")
    elif kind == "submit_flag":
        action["flag"] = st.text_input("flag")
    elif kind in ("http_get", "http_post"):
        action["path"] = st.text_input("path", "/health")
        if kind == "http_post":
            body_text = st.text_area("json body", "{}")
            try:
                action["json"] = json.loads(body_text)
            except json.JSONDecodeError as exc:
                st.error(f"Body is not valid JSON: {exc}")
                action = None
    elif kind == "b64":
        action["op"] = st.radio("op", ["encode", "decode"], horizontal=True)
        action["data"] = st.text_input("data")

    if action is not None and st.button("Run action", type="primary"):
        do_step(action)
        st.rerun()

with tab_log:
    last_action = st.session_state.get("last_action")
    last_obs = st.session_state.get("last_obs")
    if last_action is not None:
        st.markdown("**Last request / response**")
        req_col, resp_col = st.columns(2)
        req_col.json(last_action)
        resp_col.json({k: last_obs[k] for k in ("ok", "status", "body", "error") if k in last_obs})
    if st.session_state.log:
        st.markdown("**All turns this attempt**")
        st.dataframe(st.session_state.log, use_container_width=True, hide_index=True)
    else:
        st.caption("No actions taken yet.")
