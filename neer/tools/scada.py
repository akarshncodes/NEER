"""scada-mcp tools: what the city's SCADA system knows (sensors, meters, ops log, calendar)."""
from __future__ import annotations

from typing import Optional

import numpy as np

from neer.engine.detect import detect
from neer.engine.skeptic import sensor_health as _sensor_health
from neer.schemas import (CalendarEntry, OpsEvent, PressureReport, SensorHealth, SensorPressure, ZoneFlow,
                          ZoneFlowReport)
from neer.tools import chaos
from neer.tools.resilience import resilient_tool
from neer.tools.world import session


def _scada_chaos() -> None:
    if chaos.consume("scada_timeout"):
        raise TimeoutError("SCADA did not answer")


@resilient_tool("scada", chaos_hook=_scada_chaos)
def get_zone_flow(zone: Optional[str] = None, days: int = 1) -> ZoneFlowReport:
    """Water entering each zone (net of bulk customers) vs normal, the unexplained excess (L/s),
    its t-score, and the three-witness detection summary for the last `days` days."""
    if not 1 <= days <= 7:
        raise ValueError("days must be between 1 and 7")
    with session(write=False) as w:
        net, b = w.city.net, w.baseline
        obs = w.days(days)
        if zone is not None and zone not in net.zone_names:
            raise ValueError(f"unknown zone {zone}; use one of {net.zone_names}")
        ex, t = b.zone_excess(obs), b.zone_t(obs)
        mean_inflow = np.mean([d.zone_inflow for d in obs], axis=0)
        zones = [ZoneFlow(zone=z, inflow_lps=np.round(mean_inflow[:, i], 2).tolist(),
                          normal_lps=np.round(b.zn[:, i], 2).tolist(),
                          excess_lps=round(float(ex[i]), 2), t_score=round(float(t[i]), 2))
                 for i, z in enumerate(net.zone_names) if zone in (None, z)]
        masked = [net.sensors.index(s) for s in _sensor_health(b, obs[-1]).unhealthy]
        return ZoneFlowReport(day=obs[-1].day, zones=zones, detection=detect(b, obs, masked))


@resilient_tool("scada", chaos_hook=_scada_chaos)
def get_pressure(sensors: Optional[list[str]] = None, days: int = 1) -> PressureReport:
    """Pressure drop (normal minus observed, metres) per sensor and hour, and the overall anomaly score."""
    with session(write=False) as w:
        net, b = w.city.net, w.baseline
        obs = w.days(days)
        r = b.pressure_residual(obs)
        z = b.pressure_z(obs)
        chosen = sensors or net.sensors
        bad = [s for s in chosen if s not in net.sensors]
        if bad:
            raise ValueError(f"unknown sensors {bad}")
        items = [SensorPressure(sensor=s, residual_m=np.round(r[:, net.sensors.index(s)], 3).tolist(),
                                z_rms=round(float(np.sqrt((z[:, net.sensors.index(s)] ** 2).mean())), 2))
                 for s in chosen]
        return PressureReport(day=obs[-1].day, score=round(b.pressure_score(obs), 3),
                              threshold=round(b.p_thr, 3), sensors=items)


@resilient_tool("scada", chaos_hook=_scada_chaos)
def sensor_health() -> SensorHealth:
    """Health of every pressure sensor today: ok / frozen / outlier / offline, with a reason."""
    with session(write=False) as w:
        return _sensor_health(w.baseline, w.days(1)[0])


@resilient_tool("scada", chaos_hook=_scada_chaos)
def get_ops_log(days: int = 1) -> list[OpsEvent]:
    """Operator actions SCADA recorded (pump trips, valve closures) in the last `days` days."""
    with session(write=False) as w:
        return [o for d in w.days(days) for o in d.ops_log]


@resilient_tool("scada", chaos_hook=_scada_chaos)
def get_supply_calendar(days: int = 1) -> list[CalendarEntry]:
    """Planned work from the water board's calendar (flushing, tanker filling) in the last `days` days."""
    with session(write=False) as w:
        return [c for d in w.days(days) for c in d.calendar]
