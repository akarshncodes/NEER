"""Dashboard tab "Guided demo": the whole NEER story in six clicks, top to bottom.

1 Start the city  ->  2 Run the 02:00-04:00 scan (NEER opens a case by itself)  ->  3 Watch the agents
investigate (map + team chat)  ->  4 A person approves the dig (and the safety rule refuses a viewer)
->  5 Ask the AI about the case  ->  6 The data and the API behind it.

Every step shows what happened and a line to SAY. Only reliable views are used (the SVG schematic map,
HTML cards, Plotly charts), so it works offline and in any browser. Built on the same live city,
agents, tools, database and API as the rest of the app.
"""
from __future__ import annotations

import html

import httpx
import numpy as np
import streamlit as st

from neer.agents.runner import pending_interrupt
from neer.app import opsmap, wow
from neer.app import nightwatch as NWV
from neer.live import NightWatch

STEPS = ["Start the city", "2 AM scan", "AI investigates", "Human approves", "Ask the AI", "Data & API"]
SEED = 7

CSS = """<style>
.gd-steps{display:flex;gap:8px;margin:.2rem 0 1rem;flex-wrap:wrap}
.gd-step{flex:1;min-width:120px;border-radius:10px;padding:8px 10px;border:1px solid var(--line);background:var(--surface);
  font-size:.78rem;color:var(--muted);font-weight:650}
.gd-step b{display:block;font-size:1.05rem;color:var(--faint)}
.gd-step.done{background:var(--accent);border-color:var(--accent);color:#fff}.gd-step.done b{color:#fff}
.gd-step.now{border:2px solid var(--accent);color:var(--ink);animation:gdp 1.6s infinite}.gd-step.now b{color:var(--accent)}
@keyframes gdp{0%,100%{box-shadow:0 0 0 0 rgba(37,99,235,.45)}50%{box-shadow:0 0 0 7px rgba(37,99,235,0)}}
.gd-card{border:1px solid var(--line);border-radius:12px;padding:14px 16px;margin:.4rem 0 1rem;background:var(--surface)}
.gd-card h4{margin:0 0 .35rem 0}
.gd-say{border-left:4px solid #f59e0b;background:#fffbeb;color:#1f2937;border-radius:6px;padding:8px 12px;margin:.5rem 0;
  font-size:.86rem}
.gd-say b{color:#b45309}
.gd-big{font-size:1.25rem;font-weight:800;letter-spacing:-.01em}
</style>"""


def _say(text: str) -> None:
    st.markdown(f'<div class="gd-say"><b>SAY:</b> {text}</div>', unsafe_allow_html=True)


def _stepper(step: int) -> str:
    cells = []
    for i, name in enumerate(STEPS):
        cls = "done" if i < step else ("now" if i == step else "")
        cells.append(f'<div class="gd-step {cls}"><b>{"✓" if i < step else i + 1}</b>{name}</div>')
    return CSS + '<div class="gd-steps">' + "".join(cells) + "</div>"


def case_layers(w, v: dict) -> opsmap.Layers:
    """What the map shows for a case (same rules as the Control Room map)."""
    net = w.city.net
    case = w.cases.get(v.get("case_id"))
    areas = case.areas if case is not None else {}
    named = lambda aid: (aid, areas[aid]) if aid in areas else None                  # noqa: E731
    cur = v.get("current_area")
    done = v.get("status") == "closed"
    quiet = [(aid, js) for aid, js in areas.items()
             if case is not None and aid != cur and case.weights.w[[net.jindex[j] for j in js]].mean() < 0.5]
    drop = w.baseline.pressure_residual(w.city.history[-1:])[:6].mean(0)
    return opsmap.Layers(
        posterior=case.posterior if case is not None and not done else None,
        top_areas=[] if done else [n for n in (named(a["area_id"]) for a in v.get("areas", [])) if n],
        current=named(cur) if cur and not done else None, quiet=[] if done else quiet,
        repaired=named(case.last_dig_area) if case is not None and case.last_dig_area and v.get("verdict") == "FIXED" else None,
        case_zone=v.get("zone"), sensor_drop={s: float(d) for s, d in zip(net.sensors, np.nan_to_num(drop))},
        masked=list(case.masked) if case is not None else [])


def _map(w, v: dict, key: str) -> None:
    fig = opsmap.build_map("schematic", case_layers(w, v), "full", uirevision=key, height=480, width_px=620)
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False}, key=key)
    st.markdown(opsmap.legend_html(), unsafe_allow_html=True)


def _case(g: dict):
    nw: NightWatch = g["nw"]
    return nw.cases.get(g.get("case_id")) if g.get("case_id") else None


def render(brain: str, api_url: str) -> None:
    ss = st.session_state
    g = ss.setdefault("guided", {"step": 0})
    top1, top2 = st.columns([4, 1])
    top1.markdown(_stepper(g["step"]), unsafe_allow_html=True)
    if top2.button("Restart demo", width="stretch", icon=":material/restart_alt:"):
        ss.guided = {"step": 0}
        st.rerun()

    # ---------------------------------------------------------------- 1. start
    st.markdown('<div class="gd-card"><h4>1 · A city that nobody is watching</h4>'
                'A simulated city built on the US EPA\'s public <b>Net3</b> water network: 92 junctions, 5 zones, '
                '15 zone meters, 20 pressure sensors. Hidden events will start on nights NEER is not told about: '
                'leaks, a pump trip, planned flushing, fire-fighting, a frozen sensor.</div>', unsafe_allow_html=True)
    if g["step"] == 0:
        _say("Indian cities lose about 38% of treated water before it is billed. When a pipe is repaired, nobody "
             "checks. NEER investigates with evidence, acts only with human approval, and closes a case only on proof.")
        if st.button("▶  Start the city", type="primary", key="gd_start"):
            g.update(nw=NightWatch.start(SEED, brain), step=1)
            st.rerun()
        return
    nw: NightWatch = g["nw"]

    # ---------------------------------------------------------------- 2. night scan
    st.markdown('<div class="gd-card"><h4>2 · Every night at 02:00–04:00, the Sentinel reads all the raw data</h4>'
                'People are asleep, so extra water entering a zone at night is suspicious (<b>minimum night flow</b>). '
                'The Sentinel checks every meter and pressure sensor, the operations log and the calendar.</div>',
                unsafe_allow_html=True)
    if g["step"] == 1:
        _say("No one picks a scenario. Let's let the city run night by night.")
        if st.button("🌙  Run the 02:00–04:00 scan", type="primary", key="gd_scan"):
            with st.spinner("Scanning the night's raw data…"):
                for _ in range(5):
                    e = nw.run_night()
                    if e["outcome"] == "case":
                        g.update(case_id=e["case_id"], step=2)
                        break
            st.rerun()
        return
    st.markdown(NWV._calendar(nw, ahead=0), unsafe_allow_html=True)
    opened = next(n for n in nw.nights if n["case_id"] == g["case_id"])
    scan = opened["scan"]
    c1, c2 = st.columns([1, 1.3])
    with c1:
        st.markdown(NWV._zone_tiles(scan), unsafe_allow_html=True)
        st.markdown(f'<div class="gd-big">Night {opened["night"]}: case {html.escape(g["case_id"])} opened by NEER</div>'
                    f'{scan["readings"]} raw readings checked · night 1 was clean.', unsafe_allow_html=True)
    with c2:
        st.plotly_chart(NWV._zone_chart(scan), width="stretch", config={"displayModeBar": False}, key="gd_zone")
    z1 = max(scan["zones"], key=lambda z: z["excess_lps"])
    _say(f"Night 1 was clean. On night {opened['night']}, zone {z1['zone']} took {z1['night_inflow_lps']} L/s at night "
         f"against a normal {z1['normal_night_lps']} L/s. Nothing in the operations log explains it, so NEER opened "
         "the case itself - no human told it to.")

    case = _case(g)
    v = case.state()
    w = nw.world

    # ---------------------------------------------------------------- 3. investigation
    st.markdown('<div class="gd-card"><h4>3 · Six AI agents investigate</h4>'
                'Skeptic questions the alarm · Detective locates the leak · Orchestrator plans the next-best listening '
                'survey · Field crew listens overnight. Listening surveys run under a standing night policy; '
                '<b>digging always waits for a person.</b></div>', unsafe_allow_html=True)
    if g["step"] == 2:
        if st.button("🔎  Show the investigation", type="primary", key="gd_inv"):
            g["step"] = 3
            st.rerun()
        return
    st.markdown(wow.mission(v), unsafe_allow_html=True)
    m1, m2 = st.columns([1.25, 1])
    with m1:
        _map(w, v, "gd_map")
    with m2:
        st.markdown(wow.chat_html(v.get("timeline", [])), unsafe_allow_html=True)
    top = (v.get("areas") or [{}])[0]
    _say(f"The Skeptic could not explain the water away. The Detective ranked the areas; the top one is "
         f"{top.get('area_id', '-')} with {top.get('likelihood', 0):.0%} relative likelihood. The crew listened first, "
         "and now NEER asks a supervisor for permission to dig.")

    # ---------------------------------------------------------------- 4. human approval
    st.markdown('<div class="gd-card"><h4>4 · A person decides, and the rule is inside the tool</h4>'
                'Only a named <b>supervisor or engineer</b> can approve a dig. The check lives in the work-order tool '
                'itself, so the UI, the API and the AI are all blocked the same way.</div>', unsafe_allow_html=True)
    waiting = pending_interrupt(case.graph, case.cfg)
    if g["step"] == 3:
        if waiting:
            st.markdown(f"**NEER requests a dig in {waiting.get('area')}**: {waiting.get('reason', '')}")
        a1, a2, a3 = st.columns([1.1, 1.3, 1.6])
        name = a1.text_input("Approver name", "Ravi (Supervisor)", key="gd_name")
        if a2.button("Try as a *viewer* (safety test)", key="gd_viewer", width="stretch"):
            from neer.tools.safety import check_physical_action
            try:
                check_physical_action(w, case.case_id, waiting.get("area"), "dig", "Visitor", "viewer")
                g["viewer_msg"] = "Allowed?! (should not happen)"
            except Exception as e:  # noqa: BLE001 - show the refusal message
                g["viewer_msg"] = f"REFUSED by the safety validator: {e}"
        if a3.button("✔  Approve the dig as supervisor", type="primary", key="gd_ok", width="stretch"):
            with st.spinner("Crew digs, repairs, then the Auditor measures hour by hour…"):
                nw.decide(case.case_id, True, name, "supervisor")
                while pending_interrupt(case.graph, case.cfg):          # a wrong repair asks for a second dig
                    nw.decide(case.case_id, True, name, "supervisor")
            g["step"] = 4
            st.rerun()
        if g.get("viewer_msg"):
            st.error(g["viewer_msg"])
            _say("A viewer pressed Approve and the tool itself refused. No button can bypass it.")
        return
    v = case.state()
    st.markdown(wow.outcome(v, nw.world.kpi), unsafe_allow_html=True)
    f1, f2 = st.columns([1.25, 1])
    with f1:
        _map(w, v, "gd_map2")
    with f2:
        st.markdown(wow.chat_html(v.get("timeline", [])[-6:]), unsafe_allow_html=True)
    _say("The crew said 'repaired', but NEER does not trust that. The independent Auditor measured the zone's water "
         "itself, before and after, hour by hour, and only at 999-to-1 evidence called it FIXED and released the payment.")

    # ---------------------------------------------------------------- 5. ask the AI
    st.markdown('<div class="gd-card"><h4>5 · Ask the AI about this case</h4>'
                f'Answered by {"the live AI chain (Groq → Gemini → rules)" if brain == "chain" else "the rules explainer (switch Reasoning to LLM chain in the sidebar for Groq)"}, '
                'using <b>only this case\'s record</b>. It never invents numbers.</div>', unsafe_allow_html=True)
    from neer.agents.explain import timed_ask
    q1, q2, q3 = st.columns(3)
    asked = None
    for col, q in zip((q1, q2, q3), ("Explain this case simply", "Is the leak really fixed?", "Summarise in Tamil")):
        if col.button(q, key=f"gd_q_{q}", width="stretch"):
            asked = q
    if asked:
        with st.spinner("NEER is thinking…"):
            g.setdefault("answers", []).append(timed_ask(asked, v, brain))
        g["step"] = max(g["step"], 5)
    for a in reversed(g.get("answers", [])[-3:]):
        with st.chat_message("user"):
            st.write(a["q"])
        with st.chat_message("assistant", avatar=":material/water_drop:"):
            st.write(a["a"])
            st.caption(f"answered by {a['who']} · {a['ms']} ms")
    if g["step"] == 4:
        st.caption("Ask one question to continue.")
        return

    # ---------------------------------------------------------------- 6. data + API
    st.markdown('<div class="gd-card"><h4>6 · The data and the API behind it</h4>'
                'Network: EPA Net3 (real, public). Readings: simulated hour by hour by the EPA\'s hydraulic engine with '
                'realistic noise. Events: injected at known places and times, so every decision is scored against the '
                'truth. The same data is in <code>dataset/</code> (CSV) and served by the REST API.</div>',
                unsafe_allow_html=True)
    from neer.app.datasetview import night_chart
    zone = v.get("zone") or "Z1"
    st.plotly_chart(night_chart(zone, True), width="stretch", config={"displayModeBar": False}, key="gd_data")
    _say(f"This is zone {zone} in our dataset, night by night. The blue line is the water measured at 2 to 4 AM, the "
         "green dashed line is normal. It jumps when the hidden leak starts and stays up; the red line is the hidden "
         "truth that NEER never saw. All of it is CSV in dataset/ and served by the API.")
    try:
        r = httpx.get(f"{api_url}/api/cases/{case.case_id}", timeout=2)
        if r.status_code == 200:
            d = r.json()
            st.success(f"REST API live at {api_url} · GET /api/cases/{case.case_id} → status {d['status']}, verdict "
                       f"{d['verdict']}, {len(d['timeline'])} timeline rows, {len(d['approvals'])} approvals stored in SQLite.")
            st.markdown(f"Open **[{api_url}/docs]({api_url}/docs)** to show every endpoint.")
        else:
            st.warning(f"API answered HTTP {r.status_code}.")
    except httpx.HTTPError:
        st.info("Start the API in a second terminal to show it live: `uv run uvicorn neer.api.server:app --port 8000`.")
    st.balloons() if not g.get("done") else None
    g["done"] = True
