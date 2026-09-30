"""The "real" simulated city: hidden truth + noisy SCADA readings, one day at a time.

NEER never sees the hidden truth (true demand bias, where the leaks are).
It only sees DayData: sensor readings, zone meters, the ops log and the calendar.
Field tools (acoustic check, dig) are the only things allowed to peek at truth().
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

import numpy as np

from neer import config
from neer.schemas import (CalendarEntry, FireDraw, Leak, OpsEvent, PlannedWork, PumpTrip,
                          SensorOffset, StuckSensor, ValveClosure)
from neer.sim.hydraulics import run_day, zone_net_inflow
from neer.sim.network import get_network

AnyEvent = Union[Leak, PumpTrip, ValveClosure, FireDraw, PlannedWork, StuckSensor, SensorOffset]


@dataclass
class DayData:
    """What SCADA shows NEER for one day."""
    day: int
    pressure: np.ndarray               # HOURS x 20 sensors (m); NaN = no reading
    zone_inflow: np.ndarray            # HOURS x 5 zones (L/s), net of bulk meters
    ops_log: list[OpsEvent] = field(default_factory=list)
    calendar: list[CalendarEntry] = field(default_factory=list)
    certified_clean: bool = False      # True only for history days or days the Auditor certified


class SimCity:
    """A city with hidden demand bias, noisy meters, and events you can inject."""

    def __init__(self, seed: int = 0, history_days: int = config.HISTORY_DAYS) -> None:
        self.seed = seed
        self.rng = np.random.default_rng(seed)
        # hidden truth that NEER cannot see
        self._bias = {j: self.rng.normal(1, config.DEMAND_BIAS_SD) for j in self.net.junctions}
        self._meter_bias = self.rng.normal(1, config.METER_BIAS_SD, len(self.net.meters))
        self._leaks: dict[str, float] = {}              # node -> L/s (persistent until repaired)
        self._sensor_faults: dict[str, AnyEvent] = {}   # sensor -> StuckSensor / SensorOffset
        self._today: list[AnyEvent] = []                # one-day events for the next advance_day()
        self.day = 0
        self.history: list[DayData] = []
        for _ in range(history_days):
            d = self.advance_day()
            d.certified_clean = True

    @property
    def net(self):
        """The fixed network (not stored, so a city pickles small)."""
        return get_network()

    # ------------------------------------------------------------ events
    def add_event(self, e: AnyEvent) -> None:
        """Leaks and sensor faults persist; operations/draws apply to the next day only."""
        if isinstance(e, Leak):
            self._leaks[e.node] = self._leaks.get(e.node, 0) + e.lps
        elif isinstance(e, (StuckSensor, SensorOffset)):
            self._sensor_faults[e.sensor] = e
        else:
            self._today.append(e)

    def remove_leak(self, node: str) -> bool:
        """Repair: returns True if there really was a leak at that node."""
        return self._leaks.pop(node, None) is not None

    def fix_sensor(self, sensor: str) -> None:
        self._sensor_faults.pop(sensor, None)

    def truth(self) -> list[Leak]:
        """Hidden truth - only field tools and the evaluation may call this."""
        return [Leak(node=n, lps=q) for n, q in self._leaks.items()]

    # ------------------------------------------------------------ the clock
    def advance_day(self) -> DayData:
        """Simulate the next day and return what SCADA records."""
        r = self.rng
        demand = {j: self._bias[j] * r.normal(1, config.DEMAND_DAILY_SD) for j in self.net.junctions}
        hourly = r.normal(1, config.DEMAND_HOURLY_SD, config.HOURS)
        events = [Leak(node=n, lps=q) for n, q in self._leaks.items()] + list(self._today)
        hyd = run_day(events, demand, hourly)

        pressure = hyd.pressure[:, self.net.sensor_index] + r.normal(0, config.PRESSURE_NOISE_M, (config.HOURS, len(self.net.sensors)))
        flows = hyd.meter_flow * self._meter_bias * r.normal(1, config.METER_NOISE_SD, hyd.meter_flow.shape)
        bulk = hyd.bulk_demand * r.normal(1, config.BULK_NOISE_SD, hyd.bulk_demand.shape)
        inflow = zone_net_inflow(flows, bulk)

        for s, fault in self._sensor_faults.items():
            k = self.net.sensors.index(s)
            if isinstance(fault, StuckSensor):
                pressure[fault.from_h:, k] = pressure[fault.from_h, k]
            elif isinstance(fault, SensorOffset):
                pressure[:, k] += fault.metres

        ops, cal = [], []
        for i, e in enumerate(self._today):
            if isinstance(e, PumpTrip):
                ops.append(OpsEvent(op_id=f"OP-{self.day}-{i}", day=self.day, kind="pump_trip",
                                    detail=f"Pump {e.pump} off {e.start_h:02d}:00-{e.end_h:02d}:00",
                                    event=e.model_dump()))
            elif isinstance(e, ValveClosure):
                ops.append(OpsEvent(op_id=f"OP-{self.day}-{i}", day=self.day, kind="valve_closure",
                                    detail=f"Valve on pipe {e.pipe} closed", event=e.model_dump()))
            elif isinstance(e, PlannedWork):
                cal.append(CalendarEntry(entry_id=f"CAL-{self.day}-{i}", day=self.day,
                                         zone=self.net.zone_of(e.node), h0=e.h0, h1=e.h1,
                                         detail=f"Planned flushing / tanker filling at {e.node}, {e.lps:.0f} L/s",
                                         event=e.model_dump()))
        self._today = []
        d = DayData(day=self.day, pressure=pressure, zone_inflow=inflow, ops_log=ops, calendar=cal)
        self.history.append(d)
        self.day += 1
        return d

    def clean_history(self) -> list[DayData]:
        return [d for d in self.history if d.certified_clean]
