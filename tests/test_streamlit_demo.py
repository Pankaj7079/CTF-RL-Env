"""The optional Streamlit demo page renders and its scripted-agent tab shows real results."""

from __future__ import annotations

import pytest

pytest.importorskip("streamlit", reason="needs the optional `demo` dependency group")

from streamlit.testing.v1 import AppTest  # noqa: E402


def test_scripted_agent_tab_runs_sixteen_rollouts() -> None:
    page = AppTest.from_file("demo/streamlit_app.py", default_timeout=120).run()
    page.sidebar.button[0].click().run()
    assert not page.exception

    next(b for b in page.button if b.label == "Run 16 rollouts").click().run()
    assert not page.exception
    solved = next(m for m in page.metric if m.label == "Solved" and "/" in m.value)
    assert solved.value.endswith("/ 16")
    table = page.dataframe[0].value
    assert len(table) == 16
    assert set(table["turns"]) != {10}
