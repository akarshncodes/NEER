"""The shared world: the simulated city + everything the field has done.

All 19 tools read and write this. In one process (dashboard, tests, CLI with
NEER_TOOL_MODE=direct) it is an in-memory singleton. The four MCP servers run as
separate processes, so they set NEER_WORLD_SHARED=1 and load/save it from
data/world.pkl under a file lock on every call.
"""
from __future__ import annotations

import fcntl
import os
import pickle
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from neer import config
from neer.engine.baseline import Baseline
from neer.engine.plan import SearchWeights
from neer.schemas import AuditVerdict, WorkOrder
from neer.sim.city import DayData, SimCity
from neer.sim.scenarios import SCENARIOS, Scenario
from neer.tools import chaos


@dataclass
class CaseRecord:
    case_id: str
    zone: Optional[str] = None
    zone_idx: Optional[int] = None
    pre_excess: float = 0.0
    posterior: Optional[np.ndarray] = None
    weights: SearchWeights = field(default_factory=SearchWeights)
    areas: dict[str, list[str]] = field(default_factory=dict)       # area_id -> junctions
    acoustic_yes: set[str] = field(default_factory=set)
    repair_day: Optional[int] = None
    last_verdict: Optional[AuditVerdict] = None
    masked: list[str] = field(default_factory=list)
    last_dig_area: Optional[str] = None
    audit_zone: Optional[str] = None


@dataclass
class World:
    city: SimCity
    baseline: Baseline
    scenario: Scenario
    seed: int
    rng: np.random.Generator
    case_start_day: int
    cases: dict[str, CaseRecord] = field(default_factory=dict)
    work_orders: dict[str, WorkOrder] = field(default_factory=dict)
    idempotency: dict[str, str] = field(default_factory=dict)
    memory: dict[str, str] = field(default_factory=dict)
    misfix_remaining: int = 0
    kpi: dict[str, float] = field(default_factory=lambda: {
        "cases": 0, "false_alarms_avoided": 0, "acoustic_checks": 0, "digs": 0, "wasted_digs": 0,
        "repairs_verified": 0, "repairs_rejected": 0, "litres_saved_per_day": 0.0, "contractors_held": 0,
        "crew_hours": 0.0, "baseline_updates": 0, "refused_actions": 0})

    # ------------------------------------------------------------ creation
    @classmethod
    def new(cls, scenario: str = "leak_20", seed: int = 7) -> "World":
        sc = SCENARIOS[scenario]
        city = SimCity(seed)
        base = Baseline(city.clean_history())
        chaos.reset()
        for k, v in sc.chaos.items():
            chaos.set_toggle(k, v)
        for e in sc.events:
            city.add_event(e)
        start = city.day
        for _ in range(sc.days_before_case):   # one-day events (pump trip etc.) only affect the first day
            city.advance_day()
        return cls(city=city, baseline=base, scenario=sc, seed=seed, rng=np.random.default_rng(seed + 1000),
                   case_start_day=start, misfix_remaining=1 if sc.misfix_first else 0)

    # ------------------------------------------------------------ what SCADA shows
    def days(self, n: int = 1) -> list[DayData]:
        """The last n observed days, with the 'sensor dies' chaos applied."""
        out = []
        dead = chaos.get().get("sensor_dies")
        for d in self.city.history[-n:]:
            if dead and dead in self.city.net.sensors:
                p = d.pressure.copy()
                p[:, self.city.net.sensors.index(dead)] = np.nan
                d = DayData(day=d.day, pressure=p, zone_inflow=d.zone_inflow, ops_log=d.ops_log,
                            calendar=d.calendar, certified_clean=d.certified_clean)
            out.append(d)
        return out

    def advance_day(self) -> DayData:
        """Next day of SCADA data. In the live city (neer/live.py) scheduled hidden events start first."""
        for item in getattr(self, "schedule", {}).pop(self.city.day, []):
            if item == "misfix":
                self.misfix_remaining += 1                 # the next repair is done on the wrong pipe
            elif isinstance(item, tuple) and item[0] == "fix_sensor":
                self.city.fix_sensor(item[1])              # maintenance repaired a faulty sensor
            else:
                self.city.add_event(item)
        return self.city.advance_day()

    def case(self, case_id: str) -> CaseRecord:
        if case_id not in self.cases:
            self.cases[case_id] = CaseRecord(case_id=case_id)
            self.kpi["cases"] += 1
        return self.cases[case_id]


# ------------------------------------------------------------ access
_world: Optional[World] = None


def set_world(w: World) -> None:
    global _world
    _world = w
    save(w)


def save(w: World) -> None:
    config.WORLD_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = config.WORLD_FILE.with_suffix(".tmp")
    with open(tmp, "wb") as f:
        pickle.dump(w, f)
    os.replace(tmp, config.WORLD_FILE)


def load() -> World:
    with open(config.WORLD_FILE, "rb") as f:
        return pickle.load(f)


@contextmanager
def session(write: bool = True):
    """Use the world inside a tool.  Shared mode: file-locked load -> use -> save."""
    global _world
    if os.getenv("NEER_WORLD_SHARED") != "1":
        if _world is None:
            _world = load() if config.WORLD_FILE.exists() else World.new()
        yield _world
        return
    config.WORLD_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(config.WORLD_FILE.with_suffix(".lock"), "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        try:
            w = load() if config.WORLD_FILE.exists() else World.new()
            yield w
            if write:
                save(w)
        finally:
            fcntl.flock(lk, fcntl.LOCK_UN)
