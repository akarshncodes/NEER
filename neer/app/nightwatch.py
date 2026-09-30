"""Dashboard tab "Night watch": the autonomous mode. No scenario picking - NEER scans the live city every
night at 02:00-04:00, opens cases by itself, and asks a human only for digs."""
from __future__ import annotations

import html

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from neer import config
from neer.agents.runner import pending_interrupt
from neer.app import components as C
from neer.app import wow
from neer.live import NightWatch

OUT = {"clean": ("#16a34a", "Clean night"), "dismissed": ("#d97706", "Look-alike explained, no crew"),
       "watch": ("#64748b", "Watching"), "case": ("#dc2626", "Case opened by NEER"),
       "attached": ("#7c3aed", "Added to an open case")}

CSS = """<style>
.nw-intro{border-radius:12px;padding:14px 18px;margin:.2rem 0 .8rem;color:#e6f0fa;
  background:radial-gradient(circle at 85% 20%,#1e3a8a 0,#0b1b33 55%,#050d1a 100%);position:relative;overflow:hidden}
.nw-intro b{color:#fff}.nw-intro .moon{position:absolute;right:26px;top:14px;width:46px;height:46px;border-radius:50%;
  box-shadow:-12px 6px 0 0 #fde68a;transform:rotate(-20deg);opacity:.9}
.nw-intro .star{position:absolute;width:3px;height:3px;border-radius:50%;background:#fff;animation:tw 2.4s infinite}
@keyframes tw{0%,100%{opacity:.2}50%{opacity:1}}
.nw-clock{font-family:var(--mono);font-size:1.05rem;font-weight:700;color:#fff;margin-top:6px}
.nw-cal{display:flex;flex-wrap:wrap;gap:6px;margin:.3rem 0 1rem}
.nw-night{width:44px;height:52px;border-radius:8px;color:#fff;display:flex;flex-direction:column;align-items:center;
  justify-content:center;font-size:.62rem;font-weight:700;line-height:1.1;cursor:default}
.nw-night .n{font-size:1rem;font-family:var(--mono)}
.nw-night.last{outline:3px solid var(--accent);outline-offset:2px;animation:nwpulse 1.6s infinite}
@keyframes nwpulse{0%,100%{box-shadow:0 0 0 0 rgba(37,99,235,.5)}50%{box-shadow:0 0 0 8px rgba(37,99,235,0)}}
.nw-night.future{background:var(--surface2);color:var(--faint);border:1px dashed var(--line2)}
.nw-legend{display:flex;gap:14px;flex-wrap:wrap;font-size:.72rem;color:var(--muted);margin-top:-.4rem;margin-bottom:.8rem}
.nw-legend i{display:inline-block;width:10px;height:10px;border-radius:3px;margin-right:4px;vertical-align:-1px}
.nw-card{border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin-bottom:8px;background:var(--surface)}
.nw-card.pending{border:2px solid #d97706;background:var(--warn-soft)}
.nw-card .h{display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-weight:700}
.nw-card .s{font-size:.8rem;color:var(--muted);margin-top:3px}
.nw-pill{border-radius:999px;padding:1px 9px;font-size:.68rem;font-weight:700;color:#fff}
.nw-brief{border-radius:12px;padding:14px 18px;margin:.2rem 0 .9rem;border:1px solid var(--line);background:var(--surface);
  display:flex;gap:16px;align-items:flex-start;animation:nwrise .6s cubic-bezier(.2,.8,.2,1) both}
.nw-brief .sun{width:44px;height:44px;border-radius:50%;flex:none;background:radial-gradient(circle,#fde68a 0,#f59e0b 70%);
  box-shadow:0 0 0 6px rgba(245,158,11,.15),0 0 22px rgba(245,158,11,.55);animation:sunrise 1.4s ease-out both}
@keyframes sunrise{from{transform:translateY(18px);opacity:0}to{transform:none;opacity:1}}
@keyframes nwrise{from{transform:translateY(8px);opacity:0}to{transform:none;opacity:1}}
.nw-brief h4{margin:0 0 4px 0;font-size:1.02rem}
.nw-brief ul{margin:.2rem 0 0 1rem;padding:0;font-size:.86rem}
.nw-brief.alert{border:2px solid #d97706;background:var(--warn-soft)}
.nw-ticker{overflow:hidden;white-space:nowrap;border-radius:8px;background:#0b1b33;color:#cfe3ff;font-family:var(--mono);
  font-size:.74rem;padding:6px 0;margin:-.3rem 0 .8rem;position:relative}
.nw-ticker span{display:inline-block;padding-left:100%;animation:tick 38s linear infinite}
.nw-ticker b{color:#fde68a}
@keyframes tick{from{transform:translateX(0)}to{transform:translateX(-100%)}}
.nw-zones{display:flex;gap:10px;flex-wrap:wrap;margin:.2rem 0 .6rem}
.nw-zone{border-radius:10px;padding:7px 10px;min-width:74px;color:#fff;font-weight:700;font-size:.8rem;position:relative}
.nw-zone small{display:block;font-weight:500;opacity:.9;font-family:var(--mono)}
.nw-zone.alarm{animation:zpulse 1.2s ease-in-out infinite}
@keyframes zpulse{0%,100%{box-shadow:0 0 0 0 rgba(220,38,38,.6)}50%{box-shadow:0 0 0 9px rgba(220,38,38,0)}}
</style>"""


def _intro(nw: NightWatch | None) -> str:
    stars = "".join(f'<span class="star" style="left:{x}%;top:{y}%;animation-delay:{d}s"></span>'
                    for x, y, d in [(62, 20, 0), (70, 60, .6), (78, 35, 1.2), (55, 70, 1.8), (88, 75, .3), (48, 30, 1.5)])
    clock = (f'Night {len(nw.nights)} scanned · city day {nw.world.city.day - 1} · next scan tonight 02:00–04:00'
             if nw else "Press “Start the live city” to begin")
    return (CSS + f'<div class="nw-intro">{stars}<div class="moon"></div>'
            '<b>Autonomous night watch.</b> No scenario to pick. Every night from <b>02:00 to 04:00</b>, when people '
            'sleep and any extra water is suspicious (minimum night flow), the Sentinel reads <b>all raw SCADA data</b>: '
            '15 zone meters, 4 bulk meters, 20 pressure sensors, sensor health, the ops log and the calendar. '
            'If something is wrong, NEER <b>opens the case itself</b>, questions it, locates it and sends listening '
            'surveys under the standing night policy. A person is asked only before anyone digs.'
            f'<div class="nw-clock">{clock}</div></div>')


def _briefing(nw: NightWatch, approver: str, role: str) -> str:
    """Plain-English morning briefing: what happened last night and what needs a person."""
    last = nw.nights[-1]
    waiting = [(cid, c) for cid, c in nw.cases.items() if pending_interrupt(c.graph, c.cfg)]
    colour, label = OUT[last["outcome"]]
    items = [f"<li><b>Night {last['night']}:</b> {html.escape(last['note'])}</li>",
             f"<li>{last['scan']['readings']:,} raw readings checked between 02:00 and 04:00; "
             f"{len(last['scan']['unhealthy']) or 'no'} unhealthy sensor(s).</li>"]
    k = nw.kpis()
    items.append(f"<li>So far: {k['nights']} nights, {k['cases']} case(s) opened by NEER, {k['dismissed']} look-alike(s) "
                 f"explained without a crew, {k['proven']} repair(s) proven.</li>")
    if waiting:
        names = ", ".join(f"<b>{cid}</b> (dig in {html.escape(str(pending_interrupt(c.graph, c.cfg).get('area')))})"
                          for cid, c in waiting)
        items.append(f"<li><b>Needs you:</b> {names}. Approve or reject in the inbox below "
                     f"(as {html.escape(approver)}, {html.escape(role)}).</li>")
    title = "Good morning. NEER needs a decision." if waiting else "Good morning. Nothing needs you right now."
    return (f'<div class="nw-brief{" alert" if waiting else ""}"><div class="sun"></div><div><h4>{title}</h4>'
            f'<ul>{"".join(items)}</ul></div></div>')


def _ticker(nw: NightWatch) -> str:
    bits = []
    for n in nw.nights[-8:]:
        bits.append(f"<b>NIGHT {n['night']}</b> {html.escape(OUT[n['outcome']][1].upper())}"
                    + (f" · {html.escape(n['case_id'])}" if n["case_id"] else "")
                    + f" · {html.escape(n['note'][:90])}")
    return f'<div class="nw-ticker"><span>{"   ◆   ".join(bits)}</span></div>'


def _zone_tiles(scan: dict) -> str:
    cells = []
    for z in scan["zones"]:
        t = z["t"]
        colour = "#dc2626" if t > config.Z_THR else ("#d97706" if t > 2 else "#16a34a")
        cells.append(f'<div class="nw-zone{" alarm" if t > config.Z_THR else ""}" style="background:{colour}">'
                     f'Zone {z["zone"]}<small>{z["excess_lps"]:+.1f} L/s · t {t:.1f}</small></div>')
    return '<div class="nw-zones">' + "".join(cells) + "</div>"


def _gauge(scan: dict):
    extra = sum(max(z["excess_lps"], 0.0) for z in scan["zones"])
    fig = go.Figure(go.Indicator(
        mode="gauge+number", value=round(extra, 1), number={"suffix": " L/s", "font": {"size": 34}},
        title={"text": "Extra night water", "font": {"size": 13}},
        gauge={"axis": {"range": [0, 60]}, "bar": {"color": "#0b3a66", "thickness": 0.28},
               "steps": [{"range": [0, 5], "color": "#bbf7d0"}, {"range": [5, 15], "color": "#fde68a"},
                         {"range": [15, 60], "color": "#fecaca"}],
               "threshold": {"line": {"color": "#dc2626", "width": 3}, "thickness": 0.8, "value": 15}}))
    fig.update_layout(height=210, margin=dict(l=20, r=20, t=40, b=0), paper_bgcolor="rgba(0,0,0,0)")
    return fig


def play_week(nw: NightWatch, nights: int = 7) -> str:
    """Cinematic auto-play: one night at a time with the calendar redrawn live. Stops when a dig needs a person."""
    import time
    box = st.empty()
    for _ in range(nights):
        e = nw.run_night()
        box.markdown(_calendar(nw) + f"<div style='font-size:.9rem'><b>Night {e['night']}</b>: "
                     f"{html.escape(OUT[e['outcome']][1])}. {html.escape(e['note'])}</div>", unsafe_allow_html=True)
        time.sleep(0.9)
        if any(pending_interrupt(c.graph, c.cfg) for c in nw.cases.values()):
            box.empty()
            return f"Paused on night {e['night']}: NEER needs a person to approve a dig."
    box.empty()
    return f"Played {nights} nights."


def _calendar(nw: NightWatch, ahead: int = 6) -> str:
    cells = []
    for i, n in enumerate(nw.nights):
        colour, label = OUT[n["outcome"]]
        last = " last" if i == len(nw.nights) - 1 else ""
        tip = html.escape(f"Night {n['night']}: {label}. {n['note']}")
        cells.append(f'<div class="nw-night{last}" style="background:{colour}" title="{tip}">'
                     f'<span class="n">{n["night"]}</span>{label.split()[0]}</div>')
    for k in range(ahead):
        cells.append(f'<div class="nw-night future"><span class="n">{len(nw.nights) + k + 1}</span>next</div>')
    legend = "".join(f'<span><i style="background:{c}"></i>{l}</span>' for c, l in OUT.values())
    return f'<div class="nw-cal">{"".join(cells)}</div><div class="nw-legend">{legend}</div>'


def _zone_chart(scan: dict):
    zones = [z["zone"] for z in scan["zones"]]
    t = [z["t"] for z in scan["zones"]]
    colours = ["#dc2626" if v > config.Z_THR else ("#d97706" if v > 2 else "#16a34a") for v in t]
    fig = go.Figure(go.Bar(x=zones, y=t, marker_color=colours, text=[f"{z['excess_lps']:+.1f} L/s" for z in scan["zones"]],
                           textposition="outside", cliponaxis=False,
                           customdata=[[z["night_inflow_lps"], z["normal_night_lps"]] for z in scan["zones"]],
                           hovertemplate="%{x}: night inflow %{customdata[0]} L/s vs normal %{customdata[1]} L/s"
                                         "<br>t = %{y}<extra></extra>"))
    fig.add_hline(y=config.Z_THR, line_dash="dash", line_color="#dc2626",
                  annotation_text=f"alarm line (t = {config.Z_THR:g})", annotation_position="top right")
    fig.update_yaxes(title="t-score (night)", gridcolor="#e8e7e2", rangemode="tozero")
    fig = C._layout(fig, 260, "02:00–04:00 minimum night flow: extra water per zone")
    fig.update_layout(showlegend=False)
    return fig


def render(approver: str, role: str, seed: int, brain: str, reveal: bool, open_in_room) -> None:
    ss = st.session_state
    nw: NightWatch | None = ss.get("nightwatch")
    st.markdown(_intro(nw), unsafe_allow_html=True)

    b1, b2, b5, b3, b4 = st.columns([1.3, 1.1, 1.1, 0.8, 1.3])
    if nw is None:
        if b1.button("Start the live city", type="primary", width="stretch", icon=":material/nightlight:",
                     help="Create a fresh simulated city (seed from the sidebar) with hidden events NEER doesn't know about."):
            ss.nightwatch = NightWatch.start(int(seed), brain)
            st.rerun()
        st.info("The live city is a continuous simulation. Leaks, pump trips, planned work, fire-fighting, a frozen sensor, "
                "a valve closure and a wrong repair start on nights NEER is not told about.")
        return
    if b1.button("Run tonight's 02:00–04:00 scan", type="primary", width="stretch", icon=":material/bedtime:"):
        with st.spinner("Sentinel scanning all raw data for 02:00–04:00 ..."):
            e = nw.run_night()
        colour, label = OUT[e["outcome"]]
        ss.nw_msg = f"Night {e['night']}: {label}. {e['note']}"
        st.rerun()                                                   # the header KPIs read the fresh world
    if b2.button("Fast-forward 7 nights", width="stretch", icon=":material/fast_forward:",
                 help="Seven scans in a row. Cases that need a dig wait in the inbox, as they would overnight."):
        bar = st.progress(0.0, text="Fast-forwarding")
        for i in range(7):
            bar.progress(i / 7, text=f"Night {len(nw.nights) + 1}: scanning 02:00–04:00")
            nw.run_night()
        bar.empty()
        ss.nw_msg = f"Fast-forwarded to night {len(nw.nights)}."
        st.rerun()
    if b5.button("Play the week", width="stretch", icon=":material/play_circle:",
                 help="Watch the nights go by one at a time. It pauses by itself when a dig needs your approval."):
        ss.nw_msg = play_week(nw)
        st.rerun()
    if b3.button("New city", width="stretch", icon=":material/restart_alt:"):
        ss.nightwatch = NightWatch.start(int(seed), brain)
        st.rerun()
    b4.caption(f"Approvals are given by **{approver}** ({role}) from the sidebar. "
               "Only a supervisor or engineer can approve a dig.")

    if ss.get("nw_msg"):
        st.success(ss.pop("nw_msg"), icon=":material/nightlight:")
    k = nw.kpis()
    st.markdown(C.kpi_strip([
        ("Nights scanned", k["nights"]), ("Raw readings checked", f"{k['readings']:,}"), ("Clean nights", k["clean"]),
        ("Cases opened by NEER", k["cases"]), ("Look-alikes explained", k["dismissed"]),
        ("Waiting for a dig approval", k["waiting"]), ("Repairs proven", k["proven"]),
        ("Water saved", f"{k['saved_m3']:,.0f} m³/d")], highlight=3), unsafe_allow_html=True)
    if nw.nights:
        st.markdown(_briefing(nw, approver, role) + _ticker(nw), unsafe_allow_html=True)
    st.markdown(_calendar(nw), unsafe_allow_html=True)

    left, right = st.columns([1.05, 1], gap="large")
    with left:
        if nw.nights:
            last = nw.nights[-1]
            scan = last["scan"]
            colour, label = OUT[last["outcome"]]
            st.markdown(f"#### Night {last['night']}: what the Sentinel read")
            st.markdown(f'<span class="nw-pill" style="background:{colour}">{label}</span> {html.escape(last["note"])}',
                        unsafe_allow_html=True)
            st.markdown(_zone_tiles(scan), unsafe_allow_html=True)
            g1, g2 = st.columns([1, 1.35])
            g1.plotly_chart(_gauge(scan), width="stretch", config={"displayModeBar": False})
            g2.plotly_chart(_zone_chart(scan), width="stretch", config={"displayModeBar": False})
            dips = ", ".join(f"S{s} {d:+.2f} m" for s, d in scan["top_dips"])
            st.markdown(f"- **Pressure (02:00–04:00), biggest drops:** {dips}\n"
                        f"- **Sensor health:** {', '.join(scan['unhealthy']) + ' unhealthy (masked)' if scan['unhealthy'] else 'all 20 sensors OK'}\n"
                        f"- **Ops log:** {'; '.join(scan['ops']) or 'no pump / valve action'}\n"
                        f"- **Calendar:** {'; '.join(scan['calendar']) or 'no planned work'}\n"
                        f"- **Readings checked:** {scan['readings']:,} (24 h × 20 sensors + 24 h × 5 zones)")
        else:
            st.info("Press **Run tonight's 02:00–04:00 scan**.")

    with right:
        st.markdown("#### Inbox: cases NEER opened by itself")
        if not nw.cases:
            st.caption("No cases yet.")
        for cid, case in reversed(list(nw.cases.items())):
            v = case.state()
            waiting = pending_interrupt(case.graph, case.cfg)
            status = "waiting for dig approval" if waiting else v.get("status", "open")
            pill = {"closed": "#16a34a", "watch": "#d97706", "no_alarm": "#64748b", "escalated": "#b45309"}.get(
                v.get("status"), "#dc2626")
            if waiting:
                pill = "#d97706"
            summary = (f"Night {case.night} · zone {v.get('zone') or '-'} · leak ≈ {v.get('leak_size_lps') or 0:.1f} L/s · "
                       f"visits {v.get('visits', 0)} · verdict {v.get('verdict') or '-'}")
            st.markdown(f'<div class="nw-card{" pending" if waiting else ""}"><div class="h">{cid}'
                        f'<span class="nw-pill" style="background:{pill}">{status.upper()}</span></div>'
                        f'<div class="s">{html.escape(summary)}</div>'
                        + (f'<div class="s"><b>Dig requested in {html.escape(str(waiting.get("area")))}</b>: '
                           f'{html.escape(str(waiting.get("reason", ""))[:180])}</div>' if waiting else "")
                        + '</div>', unsafe_allow_html=True)
            c1, c2, c3 = st.columns(3)
            if waiting:
                if c1.button("Approve dig", key=f"nwok_{cid}", type="primary", width="stretch"):
                    ss.nw_msg = f"{cid}: dig decision recorded ({approver}, {role}) - now {nw.decide(cid, True, approver, role)}."
                    st.rerun()
                if c2.button("Reject", key=f"nwno_{cid}", width="stretch"):
                    nw.decide(cid, False, approver, role)
                    st.rerun()
            if c3.button("Show on map", key=f"nwopen_{cid}", width="stretch",
                         help="Show this case with the map, 3D views, Auditor meter and ledger."):
                open_in_room(nw, case)
            with st.expander(f"{cid}: the agents' conversation ({len(v.get('timeline', []))} messages)"):
                st.markdown(wow.chat_html(v.get("timeline", [])), unsafe_allow_html=True)

    if nw.nights:
        with st.expander("Night log (every scan)"):
            st.dataframe(pd.DataFrame([dict(night=n["night"], city_day=n["day"], outcome=OUT[n["outcome"]][1],
                                            case=n["case_id"] or "", note=n["note"]) for n in nw.nights]),
                         hide_index=True, width="stretch")
    if reveal:
        with st.expander("Judges only: the hidden event schedule NEER was never told", expanded=True):
            st.dataframe(pd.DataFrame(nw.reveal), hide_index=True, width="stretch")
