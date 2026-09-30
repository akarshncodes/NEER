"""Twin sandbox (what-if): inject one hypothetical event into NEER's digital twin and see what it would do.

`run_whatif` calls the real `simulate` tool (max pressure drop, zone inflow change) and adds the per-junction pressure
change from the same twin hydraulics, for the map. Every number comes from the twin; the sentence is built from them.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

import numpy as np
from pydantic import TypeAdapter

from neer import config
from neer.agents.toolbox import call
from neer.engine.twin import _base
from neer.schemas import Event
from neer.sim.hydraulics import run_day
from neer.sim.network import get_network
from neer.tools import world as W
from neer.tools.resilience import is_error

CUSTOM_SCENARIO = "whatif"
DIP_M = 0.2                      # "noticeable" pressure drop used in the sentence
FLOW_LPS = 0.5                   # "noticeable" inflow change used in the sentence
_event = TypeAdapter(Event)


@dataclass
class WhatIf:
    event: dict
    max_drop_m: float                                   # from the `simulate` tool
    zone_inflow_lps: dict[str, float]                   # from the `simulate` tool
    junction_change_m: dict[str, float]                 # mean change while the event is active (negative = drop)
    sensor_change_m: dict[str, float] = field(default_factory=dict)
    active_hours: tuple[int, int] = (0, 24)
    sentence: str = ""


def build_event(kind: str, node: Optional[str] = None, lps: float = 20.0, pipe: Optional[str] = None,
                pump: str = "10", start_h: int = 8, end_h: int = 13) -> dict:
    """The event to inject, as a validated dict (the same shape the scenarios and the `simulate` tool use)."""
    raw = {"leak": {"kind": "leak", "node": node, "lps": float(lps)},
           "pump_trip": {"kind": "pump_trip", "pump": pump, "start_h": int(start_h), "end_h": int(end_h)},
           "valve_closure": {"kind": "valve_closure", "pipe": pipe}}[kind]
    return _event.validate_python(raw).model_dump()


def ensure_world(seed: int = 7) -> None:
    """The tools need a world. If no case has been started yet, make a quiet one (fast, no events)."""
    shared = os.getenv("NEER_WORLD_SHARED") == "1" and config.WORLD_FILE.exists()
    if W._world is None and not shared:
        W.set_world(W.World.new("quiet", seed))


@lru_cache(maxsize=64)
def _junction_delta(event_json: str) -> np.ndarray:
    """HOURS x junctions pressure change for one event: the twin's hydraulics with the event minus without."""
    import json
    return run_day([_event.validate_python(json.loads(event_json))]).pressure - _base()[0]


def incident_pipes(node: str) -> list[str]:
    """Pipes (not pumps) touching a junction: the candidates for a valve closure there."""
    wn = get_network().wn
    return [l for l in wn.get_links_for_node(node) if wn.get_link(l).link_type == "Pipe"]


def describe(event: dict, sensor_change: dict[str, float], junction_change: dict[str, float],
             zone_lps: dict[str, float]) -> str:
    """One plain sentence built only from the numbers above."""
    what = {"leak": f"A {event.get('lps', 0):g} L/s leak at junction {event.get('node')}",
            "pump_trip": f"Tripping pump {event.get('pump')} from {event.get('start_h', 0):02d}:00 to {event.get('end_h', 0):02d}:00",
            "valve_closure": f"Closing pipe {event.get('pipe')}"}[event["kind"]]
    low = {s: c for s, c in sensor_change.items() if c < -DIP_M}
    j_low = sum(c < -DIP_M for c in junction_change.values())
    if low:
        s, c = min(sensor_change.items(), key=lambda kv: kv[1])
        press = (f"lowers pressure at {len(low)} of {len(sensor_change)} sensors by more than {DIP_M:g} m "
                 f"(largest drop {-c:.2f} m at sensor {s}; {j_low} of {len(junction_change)} junctions)")
    else:
        press = f"barely changes pressure at the sensors (every change is under {DIP_M:g} m)"
    moved = {z: v for z, v in zone_lps.items() if abs(v) >= FLOW_LPS}
    if moved:
        flow = "and " + " and ".join(f"{'adds' if v > 0 else 'removes'} {abs(v):.1f} L/s {'to' if v > 0 else 'from'} {z}'s inflow"
                                     for z, v in moved.items())
    else:
        flow = "but changes no zone inflow"
    return f"{what} {press}, {flow}."


def run_whatif(event: dict, seed: int = 7) -> WhatIf:
    """Simulate one injected event. Raises RuntimeError with the tool's message if the tool is unavailable."""
    import json
    ensure_world(seed)
    net = get_network()
    out = call("Sandbox", "simulate", events=[event])
    if is_error(out):
        raise RuntimeError(out["message"])
    delta = _junction_delta(json.dumps(event, sort_keys=True))
    active = np.where(np.abs(delta).max(axis=1) > 1e-6)[0]
    h0, h1 = (int(active.min()), int(active.max()) + 1) if len(active) else (0, config.HOURS)
    mean = delta[h0:h1].mean(axis=0)
    junction = {j: round(float(mean[i]), 3) for i, j in enumerate(net.junctions)}
    sensors = {s: junction[s] for s in net.sensors}
    zones = out["zone_inflow_change_lps"]
    return WhatIf(event, out["max_pressure_drop_m"], zones, junction, sensors, (h0, h1),
                  describe(event, sensors, junction, zones))


def register_custom_scenario(event: dict) -> str:
    """Make a scenario with exactly this injected event, so the normal case runner can start it."""
    from neer.sim.scenarios import SCENARIOS, Scenario
    leak = event["kind"] == "leak"
    SCENARIOS[CUSTOM_SCENARIO] = Scenario(
        name=CUSTOM_SCENARIO, title=f"What-if: {event['kind'].replace('_', ' ')} (sandbox)", events=[event],
        expect="closed_fixed" if leak else "watch_or_no_alarm")
    return CUSTOM_SCENARIO


# ------------------------------------------------------------------ the Streamlit tab
def zone_bars(zone_lps: dict[str, float], height: int = 250):
    """Bar chart of the predicted change in each zone's inflow."""
    import plotly.graph_objects as go
    from neer.app.components import ZONE_COLOURS, _layout
    zones = list(zone_lps)
    fig = go.Figure(go.Bar(x=zones, y=[zone_lps[z] for z in zones], marker_color=ZONE_COLOURS[:len(zones)],
                           text=["0.0" if abs(zone_lps[z]) < 0.05 else f"{zone_lps[z]:+.1f}" for z in zones], textposition="outside", cliponaxis=False,
                           hovertemplate="%{x}: %{y:+.2f} L/s<extra></extra>"))
    fig.update_yaxes(title="L/s", gridcolor="#e8e7e2", zeroline=True, zerolinecolor="#8f8e87")
    fig = _layout(fig, height, "Predicted change in each zone's inflow (L/s)")
    fig.update_layout(showlegend=False)
    return fig


def _on_map_pick() -> None:
    """Chart callback: a clicked junction becomes the dropdown's value (runs before the widgets are created)."""
    import streamlit as st
    ss, net = st.session_state, get_network()
    selection = ss.get("sb_map")
    points = (selection.get("selection") or {}).get("points", []) if selection else []
    for p in points:
        k = p.get("point_index", p.get("point_number"))
        if p.get("curve_number") == ss.get("_sb_pick_idx") and k is not None:
            ss.sb_node = net.junctions[k]


def render_tab(seed: int, map_mode: str, run_case) -> None:
    """The "Twin sandbox (what-if)" tab. `run_case(scenario_name)` starts a normal NEER case."""
    import streamlit as st
    from neer.app import opsmap
    net, ss = get_network(), st.session_state
    ss.setdefault("sb_node", "239")
    st.caption("Inject one hypothetical event into NEER's digital twin and see what it would do. "
               "Nothing here touches the running case. Drag a small box around a junction on the map to pick it, or use the dropdown.")
    left, right = st.columns([1.5, 1])
    res: Optional[WhatIf] = ss.get("sb_result")
    with right:                                   # controls first, so the map (drawn after) already shows a new result
        kind = st.radio("Event", ["leak", "pump_trip", "valve_closure"], horizontal=True, key="sb_kind",
                        format_func=lambda k: {"leak": "Leak", "pump_trip": "Pump trip", "valve_closure": "Valve closure"}[k])
        kw: dict = {}
        if kind in ("leak", "valve_closure"):
            node = st.selectbox("Junction", net.junctions, key="sb_node",
                                format_func=lambda j: f"{j} · zone {net.zone_of(j)}")
            if kind == "leak":
                kw = dict(node=node, lps=st.slider("Leak size (L/s)", 5, 40, 20, key="sb_lps"))
            else:
                kw = dict(pipe=st.selectbox("Pipe to close", incident_pipes(node), key=f"sb_pipe_{node}"))
        else:
            pumps = list(net.wn.pump_name_list)
            hours = st.slider("Pump off between (hour of day)", 0, 24, (8, 13), key="sb_hours")
            kw = dict(pump=st.selectbox("Pump", pumps, index=pumps.index("10") if "10" in pumps else 0, key="sb_pump"),
                      start_h=hours[0], end_h=max(hours[1], hours[0] + 1))
        event_now = build_event(kind, **kw)
        b1, b2 = st.columns(2)
        if b1.button("Simulate", type="primary", width="stretch"):
            try:
                ss.sb_result = res = run_whatif(event_now, seed)
            except RuntimeError as e:
                st.error(f"Simulation unavailable: {e}")
        if b2.button("Clear", width="stretch"):
            ss.pop("sb_result", None)
            st.rerun()
        if res is None:
            st.info("Pick an event and press **Simulate**.")
        else:
            if res.event != event_now:
                st.caption("Showing the last result; the settings above changed. Press Simulate to update.")
            st.success(res.sentence)
            st.plotly_chart(zone_bars(res.zone_inflow_lps), width="stretch", config={"displayModeBar": False})
            st.caption(f"Pressure changes are averaged over the hours where the twin shows a change ({res.active_hours[0]:02d}:00 to "
                       f"{res.active_hours[1]:02d}:00); the `simulate` tool reports a worst sensor drop of {res.max_drop_m} m.")
            if st.button("Run a case on this", width="stretch", help="Starts a NEER case with exactly this event "
                         "(seed, tools and reasoning mode from the sidebar)."):
                run_case(register_custom_scenario(res.event))
    layers = opsmap.Layers()
    if res is not None:
        ev = res.event
        layers = opsmap.Layers(
            whatif_drop={j: -c for j, c in res.junction_change_m.items()},
            sensor_drop={s: -c for s, c in res.sensor_change_m.items()},
            whatif_at=("node", ev["node"], "leak") if ev["kind"] == "leak"
            else ("link", ev["pipe"], "valve") if ev["kind"] == "valve_closure" else ("link", ev["pump"], "pump"))
    with left:
        fig = opsmap.build_map(map_mode, layers, "full", uirevision="sandbox", height=560, width_px=560, selectable=True)
        ss._sb_pick_idx = next(i for i, t in enumerate(fig.data) if t.name == "junction-select")
        st.plotly_chart(fig, width="stretch", on_select=_on_map_pick, selection_mode="points", key="sb_map",
                        config={"displayModeBar": False})
        st.markdown(opsmap.legend_html(), unsafe_allow_html=True)
