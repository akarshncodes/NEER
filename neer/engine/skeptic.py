"""The Skeptic's checks: try to explain an alarm away before anyone is sent.

Order: 1 sensor health -> 2 operations / planned-work replay in the twin -> 3 temporary -> 4 leak.
Key insight: a pump or valve change moves pressure but not how much water people use;
a leak changes both.
"""
from __future__ import annotations

import numpy as np

from neer import config
from neer.engine.baseline import Baseline
from neer.engine.detect import detect
from neer.engine.twin import event_delta
from neer.schemas import SensorHealth, SensorHealthItem, SensorStatus, SkepticKind, SkepticVerdict
from neer.sim.city import DayData
from neer.sim.network import get_network


def sensor_health(b: Baseline, day: DayData) -> SensorHealth:
    """Offline (no reading), frozen (flat line) or lone-wolf outlier (disagrees with every neighbour)."""
    net = get_network()
    P = day.pressure
    items = []
    z = np.abs(np.nan_to_num((b.pn - P) / b.ps)).mean(0)
    order = np.argsort(-z)
    zone_t = b.zone_t([day]).max()
    for k, s in enumerate(net.sensors):
        if np.isnan(P[:, k]).any():
            items.append(SensorHealthItem(sensor=s, status=SensorStatus.offline, reason="no readings"))
        elif P[6:, k].std() < config.FROZEN_SD:
            items.append(SensorHealthItem(sensor=s, status=SensorStatus.frozen, reason="flat line since 06:00"))
        elif (k == order[0] and z[k] > config.LONE_WOLF_Z and z[order[1]] < config.LONE_WOLF_SECOND
              and zone_t < 3):
            items.append(SensorHealthItem(sensor=s, status=SensorStatus.outlier,
                                          reason=f"off by {z[k]:.1f} sd while every other sensor and meter is normal"))
        else:
            items.append(SensorHealthItem(sensor=s, status=SensorStatus.ok))
    return SensorHealth(sensors=items)


def _subtract(day: DayData, dp: np.ndarray, dz: np.ndarray) -> DayData:
    return DayData(day=day.day, pressure=day.pressure - dp, zone_inflow=day.zone_inflow - dz)


def skeptic_check(b: Baseline, day: DayData) -> SkepticVerdict:
    net = get_network()
    det = detect(b, [day])
    if not det.alarm:
        return SkepticVerdict(verdict=SkepticKind.no_alarm, reason="Nothing unusual today.")

    # 1 --- sensor health
    health = sensor_health(b, day)
    bad = health.unhealthy
    masked = [net.sensors.index(s) for s in bad]
    if bad:
        det2 = detect(b, [day], masked)
        if not det2.alarm:
            return SkepticVerdict(
                verdict=SkepticKind.sensor_fault, masked_sensors=bad,
                reason=f"Sensor(s) {', '.join(bad)} faulty; with them masked, the network looks normal.",
                numbers={"pressure_score_masked": det2.pressure_score, "zone_t_max": max(det2.zone_t.values())})

    # 2 --- replay logged operations and planned work in the twin
    work = [(o.event, o.detail, SkepticKind.operation) for o in day.ops_log] + \
           [(c.event, c.detail, SkepticKind.planned_work) for c in day.calendar]
    current = day
    for event, detail, kind in work:
        dp, dz = event_delta(event)
        replayed = _subtract(current, dp, dz)
        t_after = float(b.zone_t([replayed]).max())
        if not detect(b, [replayed], masked).alarm or t_after < config.Z_THR:
            return SkepticVerdict(
                verdict=kind, masked_sensors=bad,
                reason=f"Explained by {detail}: after replaying it in the twin, no unexplained water loss remains "
                       f"(zone t {max(det.zone_t.values()):.1f} -> {t_after:.1f}).",
                numbers={"zone_t_before": max(det.zone_t.values()), "zone_t_after": t_after})
        current = replayed

    # 3 --- temporary event (fire-fighting, a burst of use) that is already over
    z = b.pressure_z([current], masked)
    zh = np.sqrt((z ** 2).mean(1))
    fh = ((current.zone_inflow - b.zn) / b.zs).max(1)
    hot = (zh > config.HOT_Z) | (fh > config.HOT_FLOW_T)
    late_t = float(b.zone_t([current], config.LATE_HOURS, widen=2.0).max())
    if (hot.sum() <= 4 and not hot[-6:].any()) or (late_t < config.LATE_T_THR and not (zh[-6:] > config.HOT_Z).any()):
        return SkepticVerdict(
            verdict=SkepticKind.temporary, masked_sensors=bad,
            reason=f"Short event ({int(hot.sum())} unusual hours) that has already ended; watching, not dispatching.",
            numbers={"hot_hours": float(hot.sum()), "late_zone_t": late_t})

    # 4 --- nothing explains it
    return SkepticVerdict(
        verdict=SkepticKind.leak, masked_sensors=bad,
        reason="Persistent water loss that no operation, planned work, sensor fault or short event explains.",
        numbers={"zone_t_max": max(det.zone_t.values()), "pressure_score": det.pressure_score})
