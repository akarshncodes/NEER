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
from neer.app import theme
from dataclasses import replace

from neer.app import board, city3d, datasetview, dbview, flowchart, geo, guided, nightwatch, opsmap, sandbox, wow
from neer.sim.network import get_network
from neer.sim.scenarios import SCENARIOS
from neer.tools import chaos
from neer.tools import world as W
from neer.tools.resilience import read_trace

st.set_page_config(page_title="NEER Control Room", page_icon=":material/water_drop:", layout="wide")
theme.set_theme(getattr(st.context.theme, "type", None) or "light")                   # follows Streamlit's light / dark setting
st.markdown(theme.css(), unsafe_allow_html=True)
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
        note = wow.toast_for(update) if ss.get("speed", 0.35) > 0 else None
        if note:
            st.toast(note[0], icon=note[1])
        if animate and update.get("timeline"):
            last = update["timeline"][-1]
            box.info(f"**{last['agent']}**: {last['text'][:160]}")
            time.sleep(ss.get("speed", 0.35))
    box.empty()
    ss.pending = pending_interrupt(ss.graph, ss.cfg)


def start(scenario: str, seed: int, mode: str, llm: str) -> None:
    ss.graph, ss.cfg, init = start_case(scenario, seed, mode, llm)
    ss.seed_used = seed
    ss.scenario = scenario
    ss.brain = llm
    ss.map_view = "full"                                  # whole city first; "Case zone" zooms in
    ss.pending = None
    run(init)
    st.toast(f"Case started: {scenario}. Follow it in the Control Room tab.", icon=":material/play_arrow:")


def answer(ok: bool) -> None:
    run(Command(resume={"approved": ok, "by": ss.get("approver", "Supervisor"), "role": ss.get("role", "supervisor")}))


def autopilot() -> None:
    while ss.get("pending"):
        answer(True)


def record_current() -> None:
    """Keep a snapshot of the active case for the operations board and the report (each case has its own world)."""
    if "graph" not in ss or not case_values().get("case_id"):
        return
    snap = ss.graph.get_state(ss.cfg)
    world = current_world()
    ss.setdefault("case_log", {})[snap.values["case_id"]] = board.make_record(
        snap.values, world.kpi if world else {}, bool(ss.get("pending")), snap.next, ss.get("seed_used"))


QUICK_DEMOS = [("Hidden leak", "leak_20", ":material/water_drop:", "A hidden 20 L/s leak: the full loop from alarm to proven repair."),
               ("Pump trip look-alike", "pump_trip", ":material/bolt:", "A logged pump trip that looks like a leak: the Skeptic should dismiss it."),
               ("Wrong repair", "wrong_repair", ":material/build:", "The crew fixes the wrong pipe first: the Auditor catches it and the case re-plans.")]


def quick_start(name: str) -> None:
    """Button callback (runs before the widgets are drawn): pick the scenario and ask for a start."""
    ss.scen_select = name
    ss.quick_go = True


# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.markdown('<div class="brand">NEER</div><div class="brand-sub">Leak investigation, verified</div>', unsafe_allow_html=True)
    st.markdown("#### Quick start")
    for label, name, icon, tip in QUICK_DEMOS:
        st.button(f"Demo: {label.lower()}", key=f"qs_{name}", width="stretch", icon=icon, help=tip,
                  on_click=quick_start, args=(name,))
    st.markdown("#### Case")
    names = list(SCENARIOS)
    ss.setdefault("scen_select", "leak_20")
    scen = st.selectbox("Scenario", names, key="scen_select", format_func=lambda n: f"{n}: {SCENARIOS[n].title}",
                        help="The simulated day the agents investigate. Some are real leaks, some are look-alikes.")
    seed = st.number_input("Seed", value=7, step=1, help="Same seed + same scenario = the exact same case every time.")
    st.markdown("#### Reasoning and tools")
    llm = st.radio("Reasoning", ["rules", "chain"], horizontal=True,
                   format_func=lambda x: "Rules only" if x == "rules" else "LLM chain",
                   help="Rules only: deterministic policy, no model called. LLM chain: Groq → Gemini → rules; "
                        "safety rules can still refuse an AI choice.")
    if llm == "chain":
        keys = {"Groq": bool(os.getenv("GROQ_API_KEY")), "Gemini": bool(os.getenv("GOOGLE_API_KEY")),
                "Ollama": os.getenv("NEER_USE_OLLAMA") == "1"}
        st.caption("Chain: " + " → ".join(f"{k} ({'key set' if v else 'off'})" for k, v in keys.items()) + " → rules")
    brain_note = st.empty()        # filled after the buttons have run, so its counts are current
    map_mode = st.radio("Map", ["schematic", "city"], horizontal=True,
                        format_func=lambda x: "City map" if x == "city" else "Schematic",
                        help="Schematic: the network drawing (always works). City map: the network on a Madurai street map (needs internet map tiles).")
    mode = st.radio("Tools via", ["direct", "mcp"], horizontal=True,
                    format_func=lambda x: "In-process" if x == "direct" else "4 MCP servers",
                    help="How agents call their 19 tools: direct Python calls, or through 4 MCP servers (falls back to direct).")
    st.markdown("#### Approval")
    ss.approver = st.text_input("Approver name", value=ss.get("approver", "Supervisor"),
                                help="Recorded on every approval in the audit trail.")
    ss.role = st.selectbox("Approver role (access control)", ["supervisor", "engineer", "field crew", "viewer"],
                           help="Only supervisor / engineer may approve a dig - the safety validator refuses others.")
    st.markdown("#### Run")
    ss.speed = st.slider("Animation (s per step)", 0.0, 1.5, 0.35, 0.05,
                         help="Pause between agent steps so you can read them. 0 = instant.")
    c1, c2 = st.columns(2)
    if c1.button("Start case", type="primary", width="stretch", help="Open a new case for the chosen scenario and seed."):
        start(scen, int(seed), mode, llm)
    if ss.pop("quick_go", False):                                                     # a Quick start button was pressed
        start(scen, int(seed), mode, llm)
    if c2.button("Autopilot", width="stretch", disabled=not ss.get("pending"), icon=":material/fast_forward:",
                 help="Approve every remaining decision automatically (as the approver above)."):
        autopilot()
    st.markdown("#### Chaos switches")
    st.caption("Break things on purpose and watch the agents recover.")
    if st.button("SCADA times out (x2)", width="stretch", icon=":material/wifi_off:"):
        chaos.set_toggle("scada_timeout", 2)
    if st.button("LLM returns broken JSON (x2)", width="stretch", icon=":material/data_object:"):
        chaos.set_toggle("llm_bad_json", 2)
    if st.button("Pressure sensor 241 dies", width="stretch", icon=":material/sensors_off:"):
        chaos.set_toggle("sensor_dies", "241")
    if st.button("Crew hears nothing (next check)", width="stretch", icon=":material/hearing_disabled:"):
        chaos.set_toggle("crew_finds_nothing", 1)
    if st.button("Reset chaos", width="stretch", icon=":material/restart_alt:"):
        chaos.reset()
    active = {k: v for k, v in chaos.get().items() if v}
    st.caption("Active: " + (", ".join(f"{k}={v}" for k, v in active.items()) if active else "none"))
    reveal = st.toggle("Reveal true leak (judges only)", value=False,
                       help="Show where the simulated leak really is, once the case is closed. The agents never see this.")

# ------------------------------------------------------------------ header + KPIs
w = current_world()
v = case_values()
record_current()
k = w.kpi if w else {}
st.markdown(wow.hero(k, max(len(ss.get("case_log", {})), int(k.get("cases", 0)))), unsafe_allow_html=True)
_ai, _fb, _veto = C.ai_stats(v.get("timeline", []))
if llm == "rules":
    brain_note.info("**Brain: rules only.** Every decision comes from the deterministic policy. No model is called.")
else:
    brain_note.info(f"**Brain: LLM chain** (Groq → Gemini → rules). Live models answered {_ai} decisions; "
                    f"{_fb} fell back to rules; {_veto} refused by safety rules. Rules still own physics, "
                    "thresholds, the safety validator and the Auditor.")
st.markdown(C.kpi_strip([
    ("Cases", k.get("cases", 0)), ("False alarms avoided", k.get("false_alarms_avoided", 0)),
    ("Acoustic checks", k.get("acoustic_checks", 0)), ("Digs", k.get("digs", 0)),
    ("Wasted digs", k.get("wasted_digs", 0)), ("Repairs proven", k.get("repairs_verified", 0)),
    ("Crew-hours", f"{k.get('crew_hours', 0):.1f}"),
    ("AI decisions · fallbacks · refused by safety rules", f"{_ai} · {_fb} · {_veto}"),
    ("Water saved", f"{k.get('litres_saved_per_day', 0) / 1000:,.0f} m³/d")], highlight=8, wide=(7,)), unsafe_allow_html=True)

eff_mode = map_mode
if map_mode == "city" and not geo.tiles_available():
    eff_mode = "schematic"                                                           # offline: no basemap tiles

def run_whatif_case(name: str) -> None:
    start(name, int(seed), mode, llm)
    st.toast("Case started with the injected event. Open the Control Room tab to follow it.", icon=":material/play_arrow:")
    st.rerun()                                                                       # the Control Room tab reads fresh state


def run_demo_suite() -> None:
    """Run the four demo scenarios on autopilot, one after another, recording each on the board."""
    bar = st.progress(0.0, text="Starting the demo scenarios")
    speed, ss.speed = ss.get("speed", 0.35), 0.0
    for i, name in enumerate(board.DEMO_SCENARIOS):
        bar.progress(i / len(board.DEMO_SCENARIOS), text=f"Running {name} ({i + 1}/{len(board.DEMO_SCENARIOS)})")
        start(name, int(seed), mode, llm)
        autopilot()
        record_current()
    ss.speed = speed
    bar.empty()
    st.rerun()                                                                       # the other tabs read fresh state


def render_city3d(layers: opsmap.Layers, case, v: dict, located: bool, blueprint: bool = False) -> None:
    """The 3D city view. It uses the 2D map's layers, but keeps the Detective's likelihood columns after closing,
    so the story (where it looked, where it dug) stays visible next to the green repaired ring."""
    if case is not None and case.posterior is not None and located:
        areas = case.areas
        layers = replace(layers, posterior=case.posterior,
                         top_areas=[(a["area_id"], areas[a["area_id"]]) for a in v.get("areas", []) if a["area_id"] in areas])
    target = city3d.focus_area(layers)
    c1, c2, c3 = st.columns([1.6, 1, 1], vertical_alignment="center")
    fly = c1.toggle("Fly to suspected area", key="fly3d", disabled=target is None,
                    help="Centre and zoom on the area being searched (or the top candidate / repaired area).")
    pitch = c2.slider("Tilt", 0, 75, 55, key="tilt3d", help="Camera tilt in degrees (0 = straight down).")
    bearing = c3.slider("Rotate", -180, 180, -25, 5, key="bearing3d", help="Compass rotation of the camera in degrees.")
    cam = city3d.Camera(pitch=pitch, bearing=bearing, fly_to=fly)
    deck = city3d.build_blueprint(layers, cam, width_px=520, height_px=600) if blueprint else \
        city3d.build_deck(layers, cam, width_px=520, height_px=600, basemap=os.getenv("NEER_3D_BASEMAP", "0") == "1")
    st.pydeck_chart(deck, width="stretch", height=600)
    st.caption(city3d.CAPTION + (f" Focus: {target[0]}." if fly and target else ""))
    st.markdown(city3d.legend_html(), unsafe_allow_html=True)


def render_ask(v: dict, brain: str) -> None:
    """Ask NEER: questions about this case, answered by the AI chain from the case record only (rules fallback)."""
    from neer.agents.explain import QUICK, timed_ask
    hist = ss.setdefault("ask_hist", {}).setdefault(v.get("case_id"), [])
    st.caption("Ask anything about this case. The AI (" + ("Groq → Gemini → rules" if brain == "chain" else
               "rules only - switch Reasoning to 'LLM chain' for the live AI") + ") answers only from this case's "
               "record: agent messages, evidence ledger, verdict. It never invents numbers.")
    asked = None
    for i in range(0, len(QUICK), 2):                      # two quick questions per row, so labels stay readable
        cols = st.columns(2)
        for c, q in zip(cols, QUICK[i:i + 2]):
            if c.button(q, key=f"ask_{q}_{v.get('case_id')}", width="stretch"):
                asked = q
    typed = st.chat_input("Ask NEER about this case…", key=f"ask_in_{v.get('case_id')}")
    asked = typed or asked
    if asked:
        with st.spinner("NEER is thinking…"):
            hist.append(timed_ask(asked, v, brain))
    for h in reversed(hist[-6:]):
        with st.chat_message("user"):
            st.write(h["q"])
        with st.chat_message("assistant", avatar=":material/water_drop:"):
            st.write(h["a"])
            st.caption(f"answered by {h['who']} · {h['ms']} ms")


def open_live_case(nw, case) -> None:
    """Show a case the night watch opened in the Control Room (same world, same graph)."""
    W.set_world(nw.world)
    ss.graph, ss.cfg = case.graph, case.cfg
    ss.scenario, ss.seed_used, ss.brain, ss.map_view = "live", nw.seed, nw.brain, "zone"
    ss.pending = pending_interrupt(case.graph, case.cfg)
    st.toast(f"{case.case_id} is now in the Control Room tab.", icon=":material/open_in_new:")
    st.rerun()


tab_guide, tab_room, tab_night, tab_board, tab_sandbox, tab_data, tab_db = st.tabs(
    ["▶ Guided demo", "Control Room", "Night watch (autonomous)", "Operations board", "Twin sandbox (what-if)", "Dataset",
     "Database & API"])
with tab_guide:
    guided.render(llm, dbview.API_URL)
with tab_data:
    datasetview.render(reveal)
with tab_night:
    nightwatch.render(ss.get("approver", "Supervisor"), ss.get("role", "supervisor"), int(seed), llm, reveal,
                      open_live_case)
with tab_db:
    dbview.render(scen, int(seed))
with tab_sandbox:
    sandbox.render_tab(int(seed), eff_mode, run_whatif_case)
with tab_board:
    board.render_tab(run_demo_suite, v.get("case_id"))

HOW_TO = """
1. **Pick a case.** Press one of the **Quick start** demos in the sidebar, or choose a scenario and press **Start case**.
2. **Watch the agents work.** The Sentinel raises the alarm, the Skeptic questions it, the Detective narrows down the area.
3. **Make the calls.** When a *Decision needed* box appears on the right, press **Approve** or **Reject**
   (or **Autopilot** to approve everything).
4. **See the proof.** After the repair, the Auditor measures the zone again and fills the proof meter: FIXED, PARTLY FIXED or NOT FIXED.
5. **Explore.** Switch the map to **3D city view**, read the evidence ledger, try the **Twin sandbox** or the chaos switches.
"""

with tab_room:
    with st.expander("How to use the Control Room", icon=":material/help:", expanded=False):
        st.markdown(HOW_TO)
    if not w or not v:
        st.info("Choose a scenario in the sidebar and press **Start case**.")
        st.stop()

    status = v.get("status", "open")
    colour = {"closed": "var(--good)", "watch": "var(--warn)", "no_alarm": "var(--faint)", "escalated": "var(--bad)"}.get(status, "var(--accent)")
    st.markdown(f'<div class="chips"><span class="badge state" style="background:{colour}">{status.upper()}</span>'
                f'<span class="badge soft">Tier {v.get("tier")}</span>'
                f'<span class="badge soft">Zone {v.get("zone") or "-"}</span>'
                f'<span class="badge soft">Visits {v.get("visits", 0)}, re-plans {v.get("replans", 0)}</span>'
                + (f'<span class="badge good">Verdict {v["verdict"].replace("_", " ")}</span>' if v.get("verdict") else "")
                + '</div>', unsafe_allow_html=True)
    st.markdown(wow.mission(v) + wow.outcome(v, k), unsafe_allow_html=True)

    left, mid, right = st.columns([1.55, 0.9, 1.0])

    # ------------------------------------------------------------------ left: map
    case = w.cases.get(v.get("case_id")) if w else None
    with left:
        areas = case.areas if case is not None else {}
        named = lambda aid: (aid, areas[aid]) if aid in areas else None                  # noqa: E731
        cur_id = v.get("current_area")
        quiet = [(aid, js) for aid, js in areas.items()
                 if aid != cur_id and case.weights.w[[net.jindex[j] for j in js]].mean() < 0.5]
        hist = w.city.history[-5:]
        drop = w.baseline.pressure_residual(hist[-1:])[:6].mean(0) if hist else np.zeros(len(net.sensors))   # night hours
        located = bool(v.get("areas"))                                                   # the Detective has run
        field_work = status == "open" and v.get("plan_approved") and v.get("next_action") in ("acoustic_check", "dig")
        done = status == "closed"                                                        # proven FIXED: show the outcome only
        layers = opsmap.Layers(
            posterior=case.posterior if case is not None and not done else None,
            top_areas=[] if done else [n for n in (named(a["area_id"]) for a in v.get("areas", [])) if n],
            current=named(cur_id) if cur_id and not done else None, quiet=[] if done else quiet,
            repaired=named(case.last_dig_area) if case is not None and case.last_dig_area and v.get("verdict") == "FIXED" else None,
            true_leaks=[e.node for e in (SCENARIOS[ss.scenario].events if ss.scenario in SCENARIOS else []) if getattr(e, "kind", "") == "leak"]
            if reveal and status == "closed" else [],
            case_zone=v.get("zone") if located else None,
            sensor_drop={s: float(d) for s, d in zip(net.sensors, drop)}, masked=list(case.masked) if case else [],
            crew=bool(field_work and cur_id))
        dim = st.segmented_control("Map view", ["2D ops map", "3D city view", "Blueprint 3D"], default="2D ops map", key="map_dim",
                                   label_visibility="collapsed") or "2D ops map"
        if dim in ("3D city view", "Blueprint 3D"):
            render_city3d(layers, case, v, located, blueprint=dim == "Blueprint 3D")
        else:
            if eff_mode != map_mode:
                st.caption("Basemap tiles unreachable (offline): showing the schematic map.")
            b1, b2, _ = st.columns([1, 1, 2.2])
            if b1.button("Full city", width="stretch"):
                ss.map_view = "full"
            if b2.button("Case zone", width="stretch", disabled=not located):
                ss.map_view = "zone"
            st.plotly_chart(opsmap.build_map(eff_mode, layers, ss.get("map_view", "zone"),
                                             uirevision=f"{v.get('case_id')}-{ss.get('map_view', 'zone')}-{eff_mode}-{located}",
                                             height=600, width_px=560),
                            width="stretch", config={"displayModeBar": False})
            st.markdown(opsmap.legend_html(), unsafe_allow_html=True)

    # ------------------------------------------------------------------ middle: water bill, card, meter
    with mid:
        zone = v.get("zone") or net.zone_names[0]
        zi = net.zone_names.index(zone)
        st.plotly_chart(C.water_bill([d.zone_inflow[:, zi] for d in hist], w.baseline.zn[:, zi], w.baseline.zs[:, zi],
                                     zone, [f"Day {d.day}" for d in hist]), width="stretch",
                        config={"displayModeBar": False})
        if v.get("areas"):
            dips = []
            if hist:
                drop = w.baseline.pressure_residual(hist[-1:]).mean(0)
                dips = [(net.sensors[i], float(drop[i])) for i in np.argsort(-drop)[:2]]
            nxt = {"acoustic_check": f"acoustic loggers in {v.get('current_area')}",
                   "request_dig": f"dig in {v.get('current_area')}"}.get(v.get("next_action"), v.get("next_action") or "-")
            if status == "closed":
                nxt = "case closed with proof"
            st.markdown(C.evidence_card(v["case_id"], v.get("tier", ""), zone,
                                        float(w.baseline.zone_excess(hist[-1:])[zi]) if status != "closed" else v.get("leak_size_lps", 0),
                                        dips, case.masked if case else [], v.get("skeptic_reason", "")[:90] or "-",
                                        v.get("areas", []), nxt), unsafe_allow_html=True)
        if v.get("llr_trace"):
            st.plotly_chart(C.auditor_meter(v["llr_trace"]), width="stretch", config={"displayModeBar": False})

    # ------------------------------------------------------------------ right: approvals, timeline, trace
    with right:
        req = ss.get("pending")
        if req:
            what = "Approve the search plan" if req["type"] == "approve_plan" else f"Approve a DIG in {req.get('area')}"
            st.markdown(f'<div class="approve"><b>Decision needed: {what}</b><br>'
                        f'<span style="font-size:.85rem">{req.get("reason", "")}</span></div>', unsafe_allow_html=True)
            a, b = st.columns(2)
            if a.button("Approve", type="primary", width="stretch", icon=":material/check:"):
                answer(True)
                st.rerun()
            if b.button("Reject", width="stretch", icon=":material/close:"):
                answer(False)
                st.rerun()
        tab_ask, tab_chat, tab1, tab3, tab2 = st.tabs(["Ask NEER (AI)", "Team chat", "Agent timeline", "Evidence ledger",
                                                       "Tool trace"])
        with tab_ask:
            render_ask(v, llm)
        with tab_chat:
            st.markdown(wow.chat_html(v.get("timeline", [])), unsafe_allow_html=True)
        with tab3:
            led = v.get("ledger", [])
            if led:
                dims = sorted({r["dimension"] for r in led})
                chosen = st.multiselect("Filter by dimension", dims, default=dims, key="ledger_dims")
                st.markdown(C.ledger_html([r for r in led if r["dimension"] in chosen]), unsafe_allow_html=True)
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
                df["ok"] = df["ok"].map({1: "ok", 0: "error"})
                df["ms"] = df["ms"].round(0)
                st.dataframe(df, hide_index=True, width="stretch", height=480)
            else:
                st.caption("No tool calls yet.")

    with st.expander("Agent flow and latest decisions", expanded=True):
        seq = [s.next for s in reversed(list(ss.graph.get_state_history(ss.cfg)))] if "graph" in ss else []
        done_order, running = flowchart.progress(seq, status)
        st.plotly_chart(flowchart.flow_figure(done_order, running), width="stretch", config={"displayModeBar": False})
        st.markdown(C.decision_cards(v.get("timeline", [])), unsafe_allow_html=True)
