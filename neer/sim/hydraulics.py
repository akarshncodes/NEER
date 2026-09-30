"""Run one simulated day of the network with a set of events.

This is the only place that talks to WNTR/EPANET. Both the "real" city
(sim/city.py) and the agents' digital twin (tools/twin) use it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

import numpy as np
import wntr
from wntr.network import LinkStatus
from wntr.network.controls import Control, ControlAction

from neer import config
from neer.schemas import FireDraw, Leak, PlannedWork, PumpTrip, ValveClosure
from neer.sim.network import emitter_coef, area_for_flow, get_network, load_model


@dataclass
class HydraulicResult:
    pressure: np.ndarray      # HOURS x n_junctions, metres
    meter_flow: np.ndarray    # HOURS x n_meters, L/s (signed along link direction)
    bulk_demand: np.ndarray   # HOURS x n_bulk, L/s


def _hourly_pattern(h0: int, h1: int) -> list[float]:
    p = [0.0] * config.HOURS
    for h in range(h0, h1):
        p[h] = 1.0
    return p


def run_day(
    events: Iterable = (),
    demand_mult: Optional[dict[str, float]] = None,
    hourly_mult: Optional[np.ndarray] = None,
) -> HydraulicResult:
    """Simulate 24 hours.

    events       hydraulic events (Leak, PumpTrip, ValveClosure, FireDraw, PlannedWork);
                 sensor faults are applied later, to readings, not here.
    demand_mult  per-junction multiplier on base demand (hidden city bias / daily variation)
    hourly_mult  24 city-wide multipliers on the demand pattern (weather etc.)
    """
    net = get_network()
    wn = load_model()

    if demand_mult:
        for j, m in demand_mult.items():
            for d in wn.get_node(j).demand_timeseries_list:
                d.base_value *= m
    if hourly_mult is not None:
        pats = {d.pattern_name for j in net.junctions for d in wn.get_node(j).demand_timeseries_list if d.pattern_name}
        for name in pats:
            pat = wn.get_pattern(name)
            pat.multipliers = np.asarray(pat.multipliers, dtype=float) * hourly_mult

    extra = 0
    for e in events:
        if isinstance(e, Leak):
            node = wn.get_node(e.node)
            node.emitter_coefficient = (node.emitter_coefficient or 0) + emitter_coef(area_for_flow(e.lps))
        elif isinstance(e, PumpTrip):
            pump = wn.get_link(e.pump)
            for t, status, name in ((e.start_h, LinkStatus.Closed, "off"), (e.end_h, LinkStatus.Open, "on")):
                ctl = Control._time_control(wn, t * 3600, "SIM_TIME", False, ControlAction(pump, "status", status))
                wn.add_control(f"trip_{name}_{extra}", ctl)
            extra += 1
        elif isinstance(e, ValveClosure):
            wn.get_link(e.pipe).initial_status = LinkStatus.Closed
        elif isinstance(e, (FireDraw, PlannedWork)):
            name = f"draw_{extra}"
            wn.add_pattern(name, _hourly_pattern(e.h0, e.h1))
            wn.get_node(e.node).add_demand(e.lps / 1000, name)
            extra += 1
        # StuckSensor / SensorOffset are reading faults, handled in city.py

    res = wntr.sim.EpanetSimulator(wn).run_sim()
    pressure = res.node["pressure"][net.junctions].values[: config.HOURS]
    flows = res.link["flowrate"][net.meters].values[: config.HOURS] * 1000
    bulk = res.node["demand"][net.bulk].values[: config.HOURS] * 1000
    return HydraulicResult(pressure=pressure, meter_flow=flows, bulk_demand=bulk)


def zone_net_inflow(meter_flow: np.ndarray, bulk_demand: np.ndarray) -> np.ndarray:
    """HOURS x zones: water entering each zone minus what bulk customers metered."""
    net = get_network()
    return meter_flow @ net.MZ.T - bulk_demand @ net.BZ.T
