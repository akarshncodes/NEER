"""Seeded benchmark of the physics engine (used by tests and scripts/engine_report.py).

Every function builds fresh simulated cities, injects events and checks what
the engine concludes. Numbers produced here are the only accuracy numbers we
are allowed to quote.
"""
from __future__ import annotations

import numpy as np

from neer import config
from neer.engine.acoustic import acoustic_check
from neer.engine.audit import sequential_verify
from neer.engine.baseline import Baseline
from neer.engine.detect import detect
from neer.engine.locate import locate
from neer.engine.plan import SearchWeights, plan_search_areas
from neer.engine.skeptic import skeptic_check
from neer.schemas import (AuditKind, FireDraw, Leak, PlannedWork, PumpTrip, SensorOffset, SkepticKind,
                          StuckSensor, ValveClosure)
from neer.sim.city import SimCity
from neer.sim.network import get_network


def _junction(rng) -> str:
    net = get_network()
    return net.junctions[rng.integers(len(net.junctions))]


def false_alarm_rate(n: int, seed0: int = 100) -> float:
    alarms = 0
    for k in range(n):
        c = SimCity(seed0 + k)
        b = Baseline(c.clean_history())
        alarms += detect(b, [c.advance_day()]).alarm
    return alarms / n


def detection_rate(n: int, lps: float, days: int = 1, seed0: int = 200) -> float:
    rng = np.random.default_rng(seed0)
    hits = 0
    for k in range(n):
        c = SimCity(seed0 + k)
        b = Baseline(c.clean_history())
        c.add_event(Leak(node=_junction(rng), lps=lps))
        hits += detect(b, [c.advance_day() for _ in range(days)]).alarm
    return hits / n


SKEPTIC_SCENARIOS = ["pump_trip", "valve_closure", "planned_work", "fire_draw", "stuck_sensor",
                     "sensor_offset", "leak", "leak_plus_pump_trip"]


def skeptic_accuracy(kind: str, n: int, seed0: int = 300) -> dict:
    """Share of days where the Skeptic's final call (leak vs not a leak) is right."""
    net = get_network()
    rng = np.random.default_rng(seed0 + hash(kind) % 1000)
    correct, verdicts = 0, {}
    for k in range(n):
        c = SimCity(seed0 + 17 * k + len(kind))
        b = Baseline(c.clean_history())
        is_leak = kind in ("leak", "leak_plus_pump_trip")
        if kind == "pump_trip":
            c.add_event(PumpTrip(start_h=8, end_h=13))
        elif kind == "valve_closure":
            c.add_event(ValveClosure(pipe=str(rng.choice(config.SAFE_VALVES))))
        elif kind == "planned_work":
            c.add_event(PlannedWork(node=_junction(rng), lps=30, h0=9, h1=15))
        elif kind == "fire_draw":
            c.add_event(FireDraw(node=_junction(rng), lps=40, h0=14, h1=16))
        elif kind == "stuck_sensor":
            c.add_event(StuckSensor(sensor=str(rng.choice(net.sensors)), from_h=6))
        elif kind == "sensor_offset":
            c.add_event(SensorOffset(sensor=str(rng.choice(net.sensors)), metres=-2.0))
        elif kind == "leak":
            c.add_event(Leak(node=_junction(rng), lps=20))
        elif kind == "leak_plus_pump_trip":
            c.add_event(Leak(node=_junction(rng), lps=20))
            c.add_event(PumpTrip(start_h=8, end_h=13))
        v = skeptic_check(b, c.advance_day()).verdict
        verdicts[v.value] = verdicts.get(v.value, 0) + 1
        correct += (v == SkepticKind.leak) == is_leak
    return {"correct": correct / n, "verdicts": verdicts}


def search_run(lps: float, n: int, days: int = 3, seed0: int = 400, max_visits: int = config.MAX_VISITS) -> dict:
    """Locate -> acoustic check -> dig only on 'yes' -> soft elimination, like the real agents will do."""
    net = get_network()
    rng = np.random.default_rng(seed0)
    zone_ok = found3 = found_any = wasted = 0
    visits_needed = []
    calib = []                                   # (top-area relative likelihood, leak really inside?)
    for k in range(n):
        c = SimCity(seed0 + k)
        b = Baseline(c.clean_history())
        leak = _junction(rng)
        c.add_event(Leak(node=leak, lps=lps))
        obs = [c.advance_day() for _ in range(days)]
        res, post = locate(b, obs)
        zone_ok += res.zone == net.zone_of(leak)
        w = SearchWeights()
        first = plan_search_areas(post, w, 1, order="likelihood")[0]
        calib.append((first.likelihood, leak in first.junctions))
        for v in range(1, max_visits + 1):
            area = plan_search_areas(post, w, 1)[0]
            ac = acoustic_check(area, [leak], rng)
            if ac.result == "inconclusive":
                continue                      # same area stays on top; the survey is repeated
            if ac.result == "yes":
                if leak in area.junctions:
                    found_any += 1
                    found3 += v <= 3
                    visits_needed.append(v)
                    break
                wasted += 1
                w.empty_dig(area.junctions)
            else:
                w.acoustic_no(area.junctions)
    return {"zone_correct": zone_ok / n, "found_within_3": found3 / n, "found_within_6": found_any / n,
            "wasted_digs_per_leak": wasted / n,
            "median_visits": float(np.median(visits_needed)) if visits_needed else None,
            "top_likelihood_mean": float(np.mean([c[0] for c in calib])),
            "top_area_hit_rate": float(np.mean([c[1] for c in calib]))}


def audit_run(lps: float, case: str, n: int, seed0: int = 500) -> dict:
    """case: 'fixed' (right pipe repaired), 'not_fixed' (wrong pipe), 'partly' (1 of 2 leaks repaired)."""
    net = get_network()
    rng = np.random.default_rng(seed0 + int(lps))
    expected = {"fixed": AuditKind.fixed, "not_fixed": AuditKind.not_fixed, "partly": AuditKind.partly_fixed}[case]
    correct, never_fixed_wrongly, hours = 0, 0, []
    for k in range(n):
        c = SimCity(seed0 + 31 * k + int(lps))
        b = Baseline(c.clean_history())
        zi = rng.integers(len(net.zone_names))
        zj = net.zone_junctions(net.zone_names[zi])
        l1, l2 = rng.choice(zj, 2, replace=False)
        c.add_event(Leak(node=str(l1), lps=lps))
        if case == "partly":
            c.add_event(Leak(node=str(l2), lps=lps))
        pre = b.zone_excess([c.advance_day()])[zi]
        if case in ("fixed", "partly"):
            c.remove_leak(str(l1))
        after = [c.advance_day() for _ in range(3)]
        v = sequential_verify(b, after, int(zi), float(pre))
        correct += v.verdict == expected
        never_fixed_wrongly += not (case != "fixed" and v.verdict == AuditKind.fixed)
        if v.verdict != AuditKind.inconclusive:
            hours.append(v.hours_used)
    return {"correct": correct / n, "never_wrongly_fixed": never_fixed_wrongly / n,
            "median_hours": float(np.median(hours)) if hours else None}
