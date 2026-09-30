"""Live city + autonomous night watch: no scenario picking - NEER finds problems by itself.

The live city runs day after day. Hidden events (leaks of different sizes, pump trips, planned work,
fire-fighting, a frozen sensor, a wrong repair) start on nights NEER does not know about.

Every night, in the 02:00-04:00 window (minimum night flow: people sleep, so extra water is suspicious),
the Sentinel scans ALL raw SCADA data - 15 zone meters, 4 bulk meters, 20 pressure sensors, sensor
health, the ops log and the calendar - and:
  * clean night        -> nothing to do
  * alarm              -> NEER opens a case BY ITSELF and investigates: the Skeptic questions it, the
                          Detective locates, the Orchestrator plans, and non-invasive listening surveys run
                          under the standing night policy (no digging, no one affected)
  * a dig is needed    -> the case waits in the inbox for a named supervisor / engineer (the safety
                          validator inside the tool still checks every dig)
  * an alarm in a zone that already has an open case is attached to that case, not opened twice.

Pure Python (no Streamlit) so it can be tested and reused by the API.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from langgraph.types import Command

from neer import config, store
from neer.agents.graph import build_graph
from neer.agents.runner import pending_interrupt, step_events
from neer.agents.state import CaseState
from neer.schemas import FireDraw, Leak, PlannedWork, PumpTrip, StuckSensor, ValveClosure
from neer.tools import world as W
from neer.tools.resilience import is_error
from neer.agents.toolbox import call

NIGHT_HOURS = config.NIGHT_HOURS                # 02:00, 03:00, 04:00
NIGHT_POLICY = ("NEER night policy (standing approval for listening surveys only)", "policy")
FINAL = ("closed", "watch", "no_alarm", "escalated")


# ------------------------------------------------------------------ the hidden event schedule
def make_schedule(seed: int) -> tuple[dict[int, list], list[dict]]:
    """What will happen in the live city, and on which night. Deterministic for a seed. Returns
    (schedule by night number, a readable list for the judges' 'reveal' view)."""
    from neer.sim.network import get_network
    net = get_network()
    rng = np.random.default_rng(seed + 777)
    pool = [j for j in net.junctions if j not in config.BULK_CUSTOMERS]
    plan = [(2, Leak(node=str(rng.choice(pool)), lps=20)),
            (4, PumpTrip(start_h=8, end_h=13)),
            (6, PlannedWork(node=str(rng.choice(pool)), lps=30, h0=9, h1=15)),
            (8, Leak(node=str(rng.choice(pool)), lps=12)),
            (10, FireDraw(node=str(rng.choice(pool)), lps=40, h0=14, h1=16)),
            (12, StuckSensor(sensor=str(rng.choice(net.sensors)), from_h=6)),
            (15, "misfix"),
            (15, Leak(node=str(rng.choice(pool)), lps=40)),
            (18, ValveClosure(pipe=str(rng.choice(config.SAFE_VALVES)))),
            (21, Leak(node=str(rng.choice(pool)), lps=15))]
    sched: dict[int, list] = {}
    reveal = []
    for night, item in plan:
        sched.setdefault(night, []).append(item)
        if isinstance(item, StuckSensor):                 # maintenance fixes the sensor two nights later
            sched.setdefault(night + 2, []).append(("fix_sensor", item.sensor))
        if item == "misfix":
            reveal.append(dict(night=night, event="The next repair will be done on the wrong pipe"))
        else:
            d = item.model_dump()
            kind = d.pop("kind")
            reveal.append(dict(night=night, event=f"{kind.replace('_', ' ')}: " +
                               ", ".join(f"{k} {v}" for k, v in d.items())))
    return sched, reveal


# ------------------------------------------------------------------ what the night scan reads
def night_scan(w: W.World) -> dict:
    """Raw-data check for the last night (02:00-04:00): per-zone minimum night flow vs normal, the most
    dipping pressure sensors, sensor health, and what the ops log / calendar say."""
    net, b = w.city.net, w.baseline
    d = w.days(1)[-1]
    obs = d.zone_inflow[NIGHT_HOURS].mean(0)
    normal = b.zn[NIGHT_HOURS].mean(0)
    ex = b.zone_excess([d], NIGHT_HOURS)
    t = b.zone_t([d], NIGHT_HOURS, widen=2.0)
    zones = [dict(zone=z, night_inflow_lps=round(float(obs[i]), 1), normal_night_lps=round(float(normal[i]), 1),
                  excess_lps=round(float(ex[i]), 1), t=round(float(t[i]), 1)) for i, z in enumerate(net.zone_names)]
    drop = np.nan_to_num(b.pressure_residual([d])[NIGHT_HOURS].mean(0))
    order = np.argsort(-drop)[:3]
    health = call("Sentinel", "sensor_health")
    bad = [x["sensor"] for x in health.get("sensors", []) if x["status"] != "ok"] if not is_error(health) else []
    return dict(day=d.day, zones=zones, top_dips=[(net.sensors[i], round(float(drop[i]), 2)) for i in order],
                unhealthy=bad, ops=[o.detail for o in d.ops_log], calendar=[c.detail for c in d.calendar],
                readings=int(d.pressure.size + d.zone_inflow.size))


# ------------------------------------------------------------------ the night watch
@dataclass
class LiveCase:
    case_id: str
    night: int
    graph: object
    cfg: dict
    zone: Optional[str] = None
    pending: Optional[dict] = None           # the interrupt waiting for a human (a dig), if any

    def state(self) -> dict:
        return self.graph.get_state(self.cfg).values

    @property
    def status(self) -> str:
        return "waiting for dig approval" if self.pending else self.state().get("status", "open")


@dataclass
class NightWatch:
    seed: int = 7
    brain: str = "rules"
    world: Optional[W.World] = None
    reveal: list[dict] = field(default_factory=list)
    nights: list[dict] = field(default_factory=list)
    cases: dict[str, LiveCase] = field(default_factory=dict)
    first_day: int = 0
    schedule: dict[int, list] = field(default_factory=dict)      # night number -> hidden events starting that night
    last_fix_day: Optional[int] = None                            # city day of the last proven repair
    fixed_seen: set = field(default_factory=set)

    @classmethod
    def start(cls, seed: int = 7, brain: str = "rules") -> "NightWatch":
        import os
        os.environ["NEER_TOOL_MODE"] = "direct"                  # the live city runs in-process
        if brain == "rules":
            os.environ["NEER_LLM_CHAIN"] = "rules"
        w = W.World.new("quiet", seed)
        schedule, reveal = make_schedule(seed)
        W.set_world(w)
        return cls(seed=seed, brain=brain, world=w, reveal=reveal, first_day=w.city.day, schedule=schedule)

    def _activate(self) -> None:
        W.set_world(self.world)                                  # other tabs may have switched worlds

    def active_zones(self) -> dict[str, str]:
        return {c.zone: cid for cid, c in self.cases.items() if c.zone and c.status not in FINAL}

    def night_number(self, day: int) -> int:
        return day - self.first_day + 1

    # -------------------------------------------------------------- one night
    def run_night(self) -> dict:
        """Advance to the next night, scan the raw data, and open / continue cases by itself."""
        self._activate()
        for cid, c in self.cases.items():                         # repairs approved from any screen count too
            if cid not in self.fixed_seen and c.state().get("verdict") == "FIXED":
                self.fixed_seen.add(cid)
                self.last_fix_day = self.world.city.day
        night = len(self.nights) + 1
        for item in self.schedule.pop(night, []):                 # hidden events NEER does not know about
            if item == "misfix":
                self.world.misfix_remaining += 1
            elif isinstance(item, tuple) and item[0] == "fix_sensor":
                self.world.city.fix_sensor(item[1])
            else:
                self.world.city.add_event(item)
        self.world.advance_day()
        scan = night_scan(self.world)
        entry = dict(night=night, day=scan["day"], scan=scan, outcome="clean", case_id=None, note="")
        zf = call("Sentinel", "get_zone_flow", days=1)
        alarm, zone, window = False, None, 0
        # multi-day (slow-leak) windows may not reach back past a proven repair: that water is already fixed
        fresh = scan["day"] - self.last_fix_day if self.last_fix_day is not None else 3
        if not is_error(zf):
            for days in (1, 2, 3)[:max(1, min(3, fresh))]:        # the Sentinel's slow-leak windows
                r = zf if days == 1 else call("Sentinel", "get_zone_flow", days=days)
                if not is_error(r) and r["detection"]["alarm"]:
                    alarm, zone, window = True, max(r["zones"], key=lambda z: z["t_score"])["zone"], days
                    break
        recent = [n for n in self.nights[-2:] if n["outcome"] == "dismissed"]
        if alarm and window > 1 and recent:
            entry.update(outcome="watch", case_id=recent[-1]["case_id"],
                         note="Only the 2-3 day window is still abnormal, and it contains a look-alike already "
                              f"explained in {recent[-1]['case_id']}; watching.")
        elif not alarm:
            entry["note"] = "All zones normal in the 02:00-04:00 window."
        elif zone in self.active_zones():
            cid = self.active_zones()[zone]
            entry.update(outcome="attached", case_id=cid, note=f"Zone {zone} still abnormal; already under {cid}.")
        else:
            case = self._open_case(night)
            st = case.state()
            entry["case_id"] = case.case_id
            status = case.status
            if st.get("status") == "no_alarm":
                entry.update(outcome="watch", note="Small signal: NEER waited a day for more data and it faded; watching.")
            elif st.get("status") == "watch":
                entry.update(outcome="dismissed", note=f"Look-alike explained: {st.get('skeptic_reason') or st.get('skeptic_verdict')}")
            else:
                entry.update(outcome="case", note=f"Case opened by NEER in zone {st.get('zone')}: {status}.")
        self.nights.append(entry)
        return entry

    def _open_case(self, night: int) -> LiveCase:
        case_id = f"CASE-{uuid.uuid4().hex[:6].upper()}"
        store.open_case(case_id, "live", self.seed, self.brain, "direct")
        graph = build_graph()
        cfg = {"configurable": {"thread_id": case_id}, "recursion_limit": 80}
        case = LiveCase(case_id, night, graph, cfg)
        self.cases[case_id] = case
        self._advance(case, CaseState(case_id=case_id, scenario="live"))
        return case

    def _advance(self, case: LiveCase, payload) -> None:
        """Run the agents until the case ends or needs a human. Plan approval for listening surveys is given
        by the standing night policy; digs always stop and wait for a person."""
        while True:
            for _ in step_events(case.graph, case.cfg, payload):
                pass
            case.zone = case.state().get("zone") or case.zone
            req = pending_interrupt(case.graph, case.cfg)
            if req is None:
                case.pending = None
                return
            if req.get("type") == "approve_plan":
                payload = Command(resume={"approved": True, "by": NIGHT_POLICY[0], "role": NIGHT_POLICY[1]})
                continue
            case.pending = req                                        # a dig: wait for the supervisor
            return

    # -------------------------------------------------------------- the human decides a dig
    def decide(self, case_id: str, approved: bool, by: str, role: str) -> str:
        self._activate()
        case = self.cases[case_id]
        if not case.pending:
            return case.status
        case.pending = None
        self._advance(case, Command(resume={"approved": approved, "by": by, "role": role}))
        if case.state().get("verdict") == "FIXED":
            self.last_fix_day = self.world.city.day
            self.fixed_seen.add(case_id)
        return case.status

    # -------------------------------------------------------------- summaries
    def kpis(self) -> dict:
        k = self.world.kpi if self.world else {}
        outcomes = [n["outcome"] for n in self.nights]
        return dict(nights=len(self.nights), clean=outcomes.count("clean"), cases=outcomes.count("case"),
                    dismissed=outcomes.count("dismissed"), watch=outcomes.count("watch"),
                    waiting=sum(1 for c in self.cases.values() if pending_interrupt(c.graph, c.cfg)),
                    proven=k.get("repairs_verified", 0), saved_m3=k.get("litres_saved_per_day", 0) / 1000,
                    readings=sum(n["scan"]["readings"] for n in self.nights))
