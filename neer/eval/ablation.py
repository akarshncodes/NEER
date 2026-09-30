"""Ablation study: do the agents matter?  (Same simulated cases, five systems.)

    uv run python -m neer.eval.ablation [n_per_type]      -> docs/ABLATION.md

A  Threshold alarm -> crew digs where pressure dropped most -> closes on the crew's word
B  Leak model only  -> dig the most likely area (no listening, no Skeptic) -> closes on the crew's word
C  Leak model + Skeptic (look-alikes filtered)          -> closes on the crew's word
D  Leak model + Orchestrator (value-ranked listen-before-dig, soft elimination) -> closes on the crew's word
E  Full NEER: Skeptic + Orchestrator + independent Auditor (NOT FIXED -> re-plan)

Every system sees the same cities, the same leaks, the same look-alike events and the same
crews (25 % of leak cases: the first repair is done on the wrong pipe but reported as fixed).
"""
from __future__ import annotations

import copy
import sys

import numpy as np

from neer import config
from neer.engine.acoustic import acoustic_check
from neer.engine.audit import sequential_verify
from neer.engine.baseline import Baseline
from neer.engine.detect import detect
from neer.engine.locate import posterior
from neer.engine.plan import SearchWeights, plan_search_areas, survey_hours
from neer.engine.skeptic import skeptic_check
from neer.schemas import (AuditKind, FireDraw, Leak, PlannedWork, PumpTrip, SearchArea, SensorOffset,
                          SkepticKind, StuckSensor, ValveClosure)
from neer.sim.city import SimCity
from neer.sim.network import get_network

LOOKALIKES = ["pump_trip", "valve_closure", "fire_draw", "stuck_sensor", "sensor_offset", "planned_work"]


class Crew:
    """Digs an area. With `misfix` it fixes the wrong pipe the first time but still reports 'repaired'."""

    def __init__(self, city: SimCity, misfix: bool) -> None:
        self.city, self.misfix = city, misfix
        self.digs = self.wasted = 0
        self.hours = 0.0

    def dig(self, junctions: list[str]) -> bool:
        self.digs += 1
        self.hours += config.DIG_HOURS
        found = [l.node for l in self.city.truth() if l.node in junctions]
        if not found:
            self.wasted += 1
            return False
        if self.misfix:
            self.misfix = False
            return True                      # crew says "repaired" - but nothing changed
        for n in found:
            self.city.remove_leak(n)
        return True


def _event(kind: str, rng) -> object:
    net = get_network()
    j = net.junctions[rng.integers(len(net.junctions))]
    return {"pump_trip": PumpTrip(start_h=8, end_h=13),
            "valve_closure": ValveClosure(pipe=str(rng.choice(config.SAFE_VALVES))),
            "fire_draw": FireDraw(node=j, lps=40, h0=14, h1=16),
            "stuck_sensor": StuckSensor(sensor=str(rng.choice(net.sensors)), from_h=6),
            "sensor_offset": SensorOffset(sensor=str(rng.choice(net.sensors)), metres=-2.0),
            "planned_work": PlannedWork(node=j, lps=30, h0=9, h1=15)}[kind]


def run_system(system: str, city: SimCity, b: Baseline, days: list, misfix: bool, rng) -> dict:
    net = get_network()
    crew = Crew(city, misfix)
    out = {"dispatched": False, "closed": False, "surveys": 0}
    if not detect(b, days).alarm:
        return {**out, "digs": 0, "wasted": 0, "hours": 0.0, "fixed": not city.truth(), "caught_misfix": False}
    if system in ("C", "E") and skeptic_check(b, days).verdict != SkepticKind.leak:
        return {**out, "digs": 0, "wasted": 0, "hours": 0.0, "fixed": not city.truth(), "caught_misfix": False}
    out["dispatched"] = True
    caught = False

    if system == "A":                          # dig around the sensors with the biggest pressure drop
        drop = b.pressure_residual(days).mean(0)
        for k in np.argsort(-drop)[:3]:
            if crew.dig(net.area(net.sensors[k])):
                break
    elif system in ("B", "C"):                 # dig the most likely areas, no listening
        p, _ = posterior(b, days)
        for a in plan_search_areas(p, None, 3, order="likelihood"):
            if crew.dig(a.junctions):
                break
    else:                                      # D / E: value-ranked listen-before-dig with soft elimination
        p, _ = posterior(b, days)
        w = SearchWeights()
        rounds = 3 if system == "E" else 1
        area = None
        verified = False
        repaired = False
        for _ in range(rounds):
            repaired = False
            for _ in range(config.MAX_VISITS):
                if area is None:
                    area = plan_search_areas(p, w, 1)[0]
                out["surveys"] += 1
                crew.hours += survey_hours(area.pipe_km)
                r = acoustic_check(area, [l.node for l in city.truth()], rng).result
                if r == "inconclusive":
                    continue                   # repeat the same survey
                if r == "yes":
                    if crew.dig(area.junctions):
                        repaired = True
                        break
                    w.empty_dig(area.junctions)
                else:
                    w.acoustic_no(area.junctions)
                area = None
            if not repaired or system == "D":
                break
            # E only: independent Auditor on post-repair meter data
            before = days[-2:]
            t_pre, ex_pre = b.zone_t(before), b.zone_excess(before)
            zi = int(np.argmax(t_pre))
            after = [city.advance_day() for _ in range(2)]
            v = sequential_verify(b, after, zi, float(ex_pre[zi]))
            if v.verdict == AuditKind.fixed:
                verified = True
                break
            if v.verdict in (AuditKind.not_fixed, AuditKind.partly_fixed):
                caught = True
                days = after                   # re-plan on post-repair evidence; re-listen at the site first
                p, _ = posterior(b, days)
                continue
            break
        # D closes on the crew's word; E closes only on the Auditor's FIXED; otherwise escalate to a human
        out["closed"] = verified if system == "E" else repaired
        return {**out, "digs": crew.digs, "wasted": crew.wasted, "hours": crew.hours,
                "fixed": not city.truth(), "caught_misfix": caught}
    out["closed"] = True                       # A-C close the ticket after digging, found or not
    return {**out, "digs": crew.digs, "wasted": crew.wasted, "hours": crew.hours,
            "fixed": not city.truth(), "caught_misfix": caught}


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 24
    net = get_network()
    systems = ["A", "B", "C", "D", "E"]
    names = {"A": "Threshold alarm → dig at biggest pressure drop", "B": "Leak model only (dig most likely area)",
             "C": "Leak model + Skeptic", "D": "Leak model + Orchestrator (listen before dig)",
             "E": "Full NEER (+ independent Auditor, re-plan)"}
    res = {s: {"leak": [], "look": []} for s in systems}
    rng_case = np.random.default_rng(2026)
    for k in range(n):                                    # leak cases
        city = SimCity(7000 + k)
        b = Baseline(city.clean_history())
        city.add_event(Leak(node=net.junctions[rng_case.integers(92)], lps=[10, 20, 40][k % 3]))
        days = [city.advance_day() for _ in range(2)]
        misfix = k % 4 == 0
        for s in systems:
            res[s]["leak"].append({**run_system(s, copy.deepcopy(city), b, days, misfix, np.random.default_rng(k)),
                                   "misfix": misfix})
    for k in range(n):                                    # look-alike cases
        city = SimCity(8000 + k)
        b = Baseline(city.clean_history())
        city.add_event(_event(LOOKALIKES[k % len(LOOKALIKES)], rng_case))
        days = [city.advance_day()]
        for s in systems:
            res[s]["look"].append(run_system(s, copy.deepcopy(city), b, days, False, np.random.default_rng(k)))

    def pct(x):
        return f"{100 * np.mean(x):.0f}%" if len(x) else "-"

    lines = ["# Ablation study: do the agents matter?", "",
             f"Simulated EPA Net3 city, harsh noise. {n} leak cases (10/20/40 L/s; in 25 % the crew first fixes the "
             f"wrong pipe but reports success) + {n} look-alike cases (pump trip, valve, fire draw, stuck sensor, "
             "sensor offset, planned work). Same cases for every system.", "",
             "| System | Crews sent for look-alikes | Leaks really fixed | Tickets closed while still leaking | "
             "Wrong repairs caught | Digs / leak case | Wasted digs / leak case | Crew-hours / case |",
             "|---|---|---|---|---|---|---|---|"]
    for s in systems:
        L, K = res[s]["leak"], res[s]["look"]
        closed = [r for r in L if r["closed"]]
        misfixed = [r for r in L if r["misfix"] and r["digs"] > 0]
        lines.append(
            f"| **{s}** {names[s]} | {pct([r['dispatched'] for r in K])} | {pct([r['fixed'] for r in L])} | "
            f"{pct([not r['fixed'] for r in closed])} | {pct([r['caught_misfix'] for r in misfixed]) if s == 'E' else '0% (never checks)'} | "
            f"{np.mean([r['digs'] for r in L]):.2f} | {np.mean([r['wasted'] for r in L]):.2f} | "
            f"{np.mean([r['hours'] for r in L + K]):.1f} |")
    lines += ["", "How to read it: each added agent removes one failure mode - the Skeptic stops crews being sent for "
              "look-alikes, the Orchestrator's listen-before-dig removes wasted excavations, and only the independent "
              "Auditor catches repairs that did not work (every other system closes on the crew's word).",
              "", "Simulation only; numbers come from `uv run python -m neer.eval.ablation`."]
    out = config.ROOT / "docs" / "ABLATION.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
