"""twin-mcp tools: the WNTR digital twin - NEER's sandbox for testing hypotheses."""
from __future__ import annotations

from typing import Optional

import numpy as np

from neer.engine.locate import locate
from neer.engine.plan import plan_search_areas as _plan
from neer.engine.skeptic import sensor_health as _health
from neer.engine.skeptic import skeptic_check
from neer.engine.twin import event_delta
from neer.schemas import Event, LocateResult, SearchArea, SkepticVerdict
from neer.sim.city import DayData
from neer.tools.resilience import resilient_tool
from neer.tools.world import session


@resilient_tool("twin")
def simulate(events: list[Event]) -> dict:
    """Run the twin with hypothetical events: how much would pressure and zone inflow change?"""
    with session(write=False) as w:
        net = w.city.net
        dp_tot, dz_tot = 0, 0
        for e in events:
            dp, dz = event_delta(e.model_dump())
            dp_tot, dz_tot = dp_tot + dp, dz_tot + dz
        return {"max_pressure_drop_m": round(float(-np.min(dp_tot)), 3) if len(events) else 0.0,
                "zone_inflow_change_lps": {z: round(float(np.mean(dz_tot[:, i])), 2) for i, z in enumerate(net.zone_names)}
                if len(events) else {}}


@resilient_tool("twin")
def replay_operation(op_id: Optional[str] = None) -> SkepticVerdict:
    """Skeptic's test: replay logged operations / planned work in the twin, check sensor health and
    short events. With op_id, only that operation is considered. Returns the verdict and a plain reason."""
    with session(write=False) as w:
        day = w.days(1)[0]
        if op_id is not None:
            ops = [o for o in day.ops_log if o.op_id == op_id]
            cal = [c for c in day.calendar if c.entry_id == op_id]
            if not ops and not cal:
                raise ValueError(f"unknown operation {op_id}")
            day = DayData(day=day.day, pressure=day.pressure, zone_inflow=day.zone_inflow, ops_log=ops, calendar=cal)
        return skeptic_check(w.baseline, day)


@resilient_tool("twin")
def locate_leak(case_id: str, days: int = 2) -> LocateResult:
    """Detective's map: which zone, how big (L/s), and the most likely small search areas with probabilities."""
    if not 1 <= days <= 7:
        raise ValueError("days must be between 1 and 7")
    with session() as w:
        net = w.city.net
        obs = w.days(days)
        c = w.case(case_id)
        c.masked = _health(w.baseline, obs[-1]).unhealthy
        masked = [net.sensors.index(s) for s in c.masked]
        res, post = locate(w.baseline, obs, masked, weights=c.weights)
        c.zone, c.zone_idx = res.zone, net.zone_names.index(res.zone)
        c.pre_excess, c.posterior = res.leak_size_lps, post
        for a in res.areas:
            c.areas[a.area_id] = a.junctions
        if c.masked:
            res.evidence.append(f"Sensor(s) {', '.join(c.masked)} masked as unhealthy.")
        return res


@resilient_tool("twin")
def estimate_leak_size(zone: str, days: int = 2) -> dict:
    """Leak size in a zone from the water balance: excess L/s and its uncertainty."""
    with session(write=False) as w:
        net, b = w.city.net, w.baseline
        if zone not in net.zone_names:
            raise ValueError(f"unknown zone {zone}")
        i = net.zone_names.index(zone)
        obs = w.days(days)
        return {"zone": zone, "lps": round(float(b.zone_excess(obs)[i]), 1),
                "plus_minus_lps": round(float(b.ex_se[i] / np.sqrt(days)), 1)}


@resilient_tool("twin")
def plan_search_areas(case_id: str, n: int = 3) -> list[SearchArea]:
    """Ordered search areas for a case, using its probability map and everything the field already ruled out."""
    with session() as w:
        if case_id not in w.cases or w.cases[case_id].posterior is None:
            raise ValueError(f"case {case_id} has no probability map yet - call locate_leak first")
        c = w.cases[case_id]
        areas = _plan(c.posterior, c.weights, n)
        for a in areas:
            c.areas[a.area_id] = a.junctions
        return areas
