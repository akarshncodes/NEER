"""Dashboard tab "Database & API": shows that the UI, the REST API and the database are one connected system.

- API panel: pings the FastAPI backend (GET /api/health) and can run a case THROUGH the API (POST /api/cases).
- Database panel: row counts, the stored cases, one case's timeline / ledger / approvals / work orders,
  and a read-only SQL box - all read straight from the SQLite case database (data/neer.db).
"""
from __future__ import annotations

import os

import httpx
import pandas as pd
import streamlit as st

from neer import config, store

API_URL = os.getenv("NEER_API_URL", "http://localhost:8000")
EXAMPLES = {
    "Cases and their verdicts": "SELECT case_id, scenario, status, verdict, zone, visits FROM cases ORDER BY updated_at DESC",
    "Every human approval (who, role, gate)": "SELECT case_id, gate, approved, by_name, role, area FROM approvals",
    "Digs and who approved them": "SELECT case_id, work_order_id, area_id, result, approved_by, approver_role "
                                  "FROM work_orders WHERE action = 'dig'",
    "AI / rules decisions in the ledger": "SELECT case_id, finding, source FROM ledger WHERE dimension = 'AI decision'",
    "Evidence per dimension": "SELECT dimension, supports, COUNT(*) AS n FROM ledger GROUP BY dimension, supports",
}


def _api_health() -> dict | None:
    try:
        r = httpx.get(f"{API_URL}/api/health", timeout=1.5)
        return r.json() if r.status_code == 200 else None
    except httpx.HTTPError:
        return None


def render(scenario: str, seed: int) -> None:
    st.caption("One system, three layers: the dashboard (UI) and the REST API both run the same agents, and both "
               "write to and read from the same SQLite case database.")
    left, right = st.columns([1, 1.4], gap="large")

    # ------------------------------------------------------------ API
    with left:
        st.markdown("#### REST API (FastAPI)")
        h = _api_health()
        if h:
            st.success(f"Connected to {API_URL} · database tables {h['tables']}")
            st.markdown(f"Interactive docs: [{API_URL}/docs]({API_URL}/docs)")
        else:
            st.warning(f"API not running at {API_URL}. Start it in a second terminal:\n\n"
                       "`uv run uvicorn neer.api.server:app --port 8000`")
        st.code("GET  /api/health\nGET  /api/scenarios\nGET  /api/tools\nPOST /api/cases\nGET  /api/cases\n"
                "GET  /api/cases/{case_id}\nGET  /api/kpi\nGET  /api/trace", language="text")
        if st.button(f"Run '{scenario}' through the API", disabled=h is None, width="stretch",
                     help="POST /api/cases: the API runs the agents, stores the case, and this tab reads it back "
                          "from the database."):
            with st.spinner("POST /api/cases ..."):
                r = httpx.post(f"{API_URL}/api/cases", json={"scenario": scenario, "seed": seed,
                                                              "approver": st.session_state.get("approver", "Supervisor"),
                                                              "approver_role": st.session_state.get("role", "supervisor")},
                               timeout=180)
            st.write(f"HTTP {r.status_code}")
            st.json(r.json())

    # ------------------------------------------------------------ database
    with right:
        st.markdown("#### Case database (SQLite)")
        st.caption(f"File: `{config.CASE_DB}` · WAL mode · shared by the dashboard, the API and the 4 MCP servers")
        counts = store.counts()
        cols = st.columns(len(counts))
        for c, (t, n) in zip(cols, counts.items()):
            c.metric(t, n)
        cases = store.list_cases()
        if not cases:
            st.info("No cases stored yet. Start a case from the sidebar, or run one through the API.")
            return
        st.dataframe(pd.DataFrame(cases)[["case_id", "scenario", "brain", "tool_mode", "status", "verdict", "zone",
                                          "leak_lps", "visits", "replans", "contractor", "updated_at"]],
                     hide_index=True, width="stretch", height=220)
        pick = st.selectbox("Open a stored case", [c["case_id"] for c in cases], key="db_case")
        detail = store.get_case(pick)
        t1, t2, t3, t4 = st.tabs(["Timeline", "Evidence ledger", "Approvals", "Work orders"])
        for tab, key in ((t1, "timeline"), (t2, "ledger"), (t3, "approvals"), (t4, "work_orders")):
            with tab:
                rows = detail[key]
                st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=240) if rows \
                    else st.caption("no rows")

    st.markdown("#### Ask the database (read-only SQL)")
    ex = st.selectbox("Example query", list(EXAMPLES), key="db_example")
    sql = st.text_area("SQL (SELECT only)", EXAMPLES[ex], key=f"db_sql_{ex}", height=80)
    try:
        st.dataframe(pd.DataFrame(store.query_readonly(sql)), hide_index=True, width="stretch")
    except Exception as e:                      # noqa: BLE001 - show any SQL error to the user
        st.error(f"Query refused or failed: {e}")
