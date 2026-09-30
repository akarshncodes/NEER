"""NEER Control Room - the supervisor's screen.

    uv run streamlit run neer/app/dashboard.py

Left: the city (zones, sensors, meters, relative leak likelihood, search areas).
Middle: the zone water bill, the evidence card and the Auditor's proof meter.
Right: human approvals (with role-based access), the agent timeline, the evidence ledger and the live tool trace.
Sidebar: scenario launcher, LLM chain, tool mode and the chaos switches.
"""
from __future__ import annotations

import os
import time

import numpy as np
import pandas as pd
import streamlit as st
from langgraph.types import Command

from neer import config
from neer.agents.runner import pending_interrupt, start_case, step_events
from neer.app import components as C
from neer.sim.network import get_network
from neer.sim.scenarios import SCENARIOS
from neer.tools import chaos
from neer.tools import world as W
from neer.tools.resilience import read_trace

st.set_page_config(page_title="NEER Control Room", page_icon="💧", layout="wide")
st.markdown(C.CSS, unsafe_allow_html=True)
ss = st.session_state
net = get_network()


# ------------------------------------------------------------------ helpers
def current_world():
    if os.getenv("NEER_WORLD_SHARED") == "1" and config.WORLD_FILE.exists():
        return W.load()
    return W._world


def case_values() -> dict:
    if "graph" not in ss:
        return {}
    return ss.graph.get_state(ss.cfg).values


def run(payload, animate: bool = True) -> None:
    """Advance the agents until they finish or need a human."""
    box = st.empty()
    for node, update in step_events(ss.graph, ss.cfg, payload):
        if animate and update.get("timeline"):
            last = update["timeline"][-1]
            box.info(f"**{last['agent']}**: {last['text'][:160]}")
            time.sleep(ss.get("speed", 0.35))
    box.empty()
    ss.pending = pending_interrupt(ss.graph, ss.cfg)


def start(scenario: str, seed: int, mode: str, llm: str) -> None:
    ss.graph, ss.cfg, init = start_case(scenario, seed, mode, llm)
    ss.scenario = scenario
    ss.brain = llm
    ss.pending = None
    run(init)


def answer(ok: bool) -> None:
    run(Command(resume={"approved": ok, "by": ss.get("approver", "Supervisor"), "role": ss.get("role", "supervisor")}))


def autopilot() -> None:
    while ss.get("pending"):
        answer(True)


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown("### 💧 NEER")
    st.caption("Agentic AI leak detective · SC-02")
    names = list(SCENARIOS)
    scen = st.selectbox("Scenario", names, index=names.index("leak_20"),
                        format_func=lambda n: f"{n} — {SCENARIOS[n].title}")
    seed = st.number_input("Seed", value=7, step=1)
    llm = st.radio("Reasoning", ["rules", "chain"], horizontal=True,
                   format_func=lambda x: "Rules only" if x == "rules" else "LLM chain")
    if llm == "chain":
        keys = {"Groq": bool(os.getenv("GROQ_API_KEY")), "Gemini": bool(os.getenv("GOOGLE_API_KEY")),
                "Ollama": os.getenv("NEER_USE_OLLAMA") == "1"}
        st.caption("Chain: " + " → ".join(f"{k} {'✅' if v else '⛔'}" for k, v in keys.items()) + " → rules ✅")
    brain_note = st.empty()        # filled after the buttons have run, so its counts are current
    mode = st.radio("Tools via", ["direct", "mcp"], horizontal=True,
                    format_func=lambda x: "in-process" if x == "direct" else "4 MCP servers")
    ss.approver = st.text_input("Approver name", value=ss.get("approver", "Supervisor"))
    ss.role = st.selectbox("Approver role (access control)", ["supervisor", "engineer", "field crew", "viewer"],
                           help="Only supervisor / engineer may approve a dig - the safety validator refuses others.")
    ss.speed = st.slider("Animation (s per step)", 0.0, 1.5, 0.35, 0.05)
    c1, c2 = st.columns(2)
    if c1.button("▶ Start case", type="primary", width="stretch"):
        start(scen, int(seed), mode, llm)
    if c2.button("⏩ Autopilot", width="stretch", disabled=not ss.get("pending")):
        autopilot()
    st.markdown("#### ⚡ Chaos switches")
    if st.button("🔌 SCADA times out (×2)", width="stretch"):
        chaos.set_toggle("scada_timeout", 2)
    if st.button("🤖 LLM returns broken JSON (×2)", width="stretch"):
        chaos.set_toggle("llm_bad_json", 2)
    if st.button("📉 Pressure sensor 241 dies", width="stretch"):
        chaos.set_toggle("sensor_dies", "241")
    if st.button("🎧 Crew hears nothing (next check)", width="stretch"):
        chaos.set_toggle("crew_finds_nothing", 1)
    if st.button("Reset chaos", width="stretch"):
        chaos.reset()
    active = {k: v for k, v in chaos.get().items() if v}
    st.caption("Active: " + (", ".join(f"{k}={v}" for k, v in active.items()) if active else "none"))
    reveal = st.toggle("Reveal true leak (judges only)", value=False)

# ------------------------------------------------------------------ header + KPIs
st.markdown("# NEER Control Room")
st.caption("SUSPECT → QUESTION → INVESTIGATE → ACT → VERIFY → REPLAN · never trusts 'job done' without proof. "
           "Simulated city: EPA Net3, 5 zones, 20 pressure sensors, 15 zone meters.")
w = current_world()
v = case_values()
k = w.kpi if w else {}
_ai, _fb, _veto = C.ai_stats(v.get("timeline", []))
if llm == "rules":
    brain_note.info("**Brain: rules only.** Every decision comes from the deterministic policy. No model is called.")
else:
    brain_note.info(f"**Brain: LLM chain** (Groq → Gemini → rules). Live models answered {_ai} decisions; "
                    f"{_fb} fell back to rules; {_veto} vetoed by a safety rule. Rules still own physics, "
                    "thresholds, the safety validator and the Auditor.")
cols = st.columns(9)
for col, (label, val) in zip(cols, [
        ("Cases", k.get("cases", 0)), ("False alarms avoided", k.get("false_alarms_avoided", 0)),
        ("Acoustic checks", k.get("acoustic_checks", 0)), ("Digs", k.get("digs", 0)),
        ("Wasted digs", k.get("wasted_digs", 0)), ("Repairs proven", k.get("repairs_verified", 0)),
        ("Crew-hours", f"{k.get('crew_hours', 0):.1f}"),
        ("AI decisions / fallbacks / vetoes", f"{_ai} / {_fb} / {_veto}"),
        ("Water saved", f"{k.get('litres_saved_per_day', 0) / 1000:,.0f} m³/d")]):
    col.markdown(f'<div class="kpi"><div class="v">{val}</div><div class="l">{label}</div></div>',
                 unsafe_allow_html=True)

if not w or not v:
    st.info("Choose a scenario in the sidebar and press **Start case**.")
    st.stop()

status = v.get("status", "open")
colour = {"closed": "#1a8a3c", "watch": "#b87800", "no_alarm": "#52514e", "escalated": "#c73636"}.get(status, "#1d5aa6")
st.markdown(f'<span class="badge" style="background:{colour};color:#fff">{status.upper()}</span>'
            f'<span class="badge" style="background:#eef3fb">Tier {v.get("tier")}</span>'
            f'<span class="badge" style="background:#eef3fb">Zone {v.get("zone") or "—"}</span>'
            f'<span class="badge" style="background:#eef3fb">Visits {v.get("visits", 0)} · re-plans {v.get("replans", 0)}</span>'
            + (f'<span class="badge" style="background:#e9f5ec">Verdict {v["verdict"]}</span>' if v.get("verdict") else ""),
            unsafe_allow_html=True)

left, mid, right = st.columns([1.25, 1.0, 1.05])

# ------------------------------------------------------------------ left: map
case = w.cases.get(v.get("case_id")) if w else None
with left:
    post = case.posterior if case is not None else None
    quiet = []
    if case is not None:
        quiet = [js for aid, js in case.areas.items()
                 if aid != v.get("current_area") and case.weights.w[[net.jindex[j] for j in js]].mean() < 0.5]
    cur = case.areas.get(v.get("current_area")) if case is not None and v.get("current_area") else None
    rep = case.areas.get(case.last_dig_area) if case is not None and case.last_dig_area else None
    leaks = [e.node for e in SCENARIOS[ss.scenario].events if getattr(e, "kind", "") == "leak"] if reveal else []
    st.plotly_chart(C.network_map(post, cur, quiet, rep if v.get("verdict") else None, leaks, v.get("zone")),
                    width="stretch", config={"displayModeBar": False})

# ------------------------------------------------------------------ middle: water bill, card, meter
with mid:
    zone = v.get("zone") or net.zone_names[0]
    zi = net.zone_names.index(zone)
    hist = w.city.history[-5:]
    st.plotly_chart(C.water_bill([d.zone_inflow[:, zi] for d in hist], w.baseline.zn[:, zi], w.baseline.zs[:, zi],
                                 zone, [f"Day {d.day}" for d in hist]), width="stretch",
                    config={"displayModeBar": False})
    if v.get("areas"):
        dips = []
        if hist:
            drop = w.baseline.pressure_residual(hist[-1:]).mean(0)
            dips = [(net.sensors[i], float(drop[i])) for i in np.argsort(-drop)[:2]]
        nxt = {"acoustic_check": f"acoustic loggers in {v.get('current_area')}",
               "request_dig": f"dig in {v.get('current_area')}"}.get(v.get("next_action"), v.get("next_action") or "—")
        if status == "closed":
            nxt = "case closed with proof"
        st.markdown(C.evidence_card(v["case_id"], v.get("tier", ""), zone,
                                    float(w.baseline.zone_excess(hist[-1:])[zi]) if status != "closed" else v.get("leak_size_lps", 0),
                                    dips, case.masked if case else [], v.get("skeptic_reason", "")[:90] or "—",
                                    v.get("areas", []), nxt), unsafe_allow_html=True)
    if v.get("llr_trace"):
        st.plotly_chart(C.auditor_meter(v["llr_trace"]), width="stretch", config={"displayModeBar": False})

# ------------------------------------------------------------------ right: approvals, timeline, trace
with right:
    req = ss.get("pending")
    if req:
        what = "Approve the search plan" if req["type"] == "approve_plan" else f"Approve a DIG in {req.get('area')}"
        st.markdown(f'<div class="approve"><b>🧑‍💼 Human decision needed: {what}</b><br>'
                    f'<span style="font-size:.85rem">{req.get("reason", "")}</span></div>', unsafe_allow_html=True)
        a, b = st.columns(2)
        if a.button("✅ Approve", type="primary", width="stretch"):
            answer(True)
            st.rerun()
        if b.button("✋ Reject", width="stretch"):
            answer(False)
            st.rerun()
    tab1, tab3, tab2 = st.tabs(["Agent timeline", "Evidence ledger", "Tool trace"])
    with tab3:
        led = v.get("ledger", [])
        if led:
            ldf = pd.DataFrame(led)[["when", "dimension", "finding", "supports", "reliability", "source"]]
            ldf["supports"] = ldf["supports"].map({"leak": "🔴 leak", "against": "🟢 against", "neutral": "⚪ neutral",
                                                   "fixed": "✅ fixed"}).fillna(ldf["supports"])
            st.dataframe(ldf, hide_index=True, width="stretch", height=420)
        else:
            st.caption("No evidence yet.")
        bi = w.baseline.info()
        st.caption(f"Baseline v{bi['version']} · {bi['clean_days']} certified-clean days · "
                   f"{bi['pending_certified_days']} pending (updates need ≥ {config.BASELINE_MIN_NEW_DAYS})")
    with tab1:
        st.markdown(C.timeline_html(v.get("timeline", [])), unsafe_allow_html=True)
    with tab2:
        rows = [r for r in read_trace(80) if r["agent"] != "mcp-server"]
        if rows:
            df = pd.DataFrame(rows)[["agent", "tool", "ok", "ms", "summary"]]
            df["ok"] = df["ok"].map({1: "✅", 0: "⚠️"})
            df["ms"] = df["ms"].round(0)
            st.dataframe(df, hide_index=True, width="stretch", height=480)
        else:
            st.caption("No tool calls yet.")
