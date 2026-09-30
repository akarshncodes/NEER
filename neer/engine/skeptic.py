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


def skeptic_check(b: Baseline, day) -> SkepticVerdict:
    """`day` is one DayData or a list of consecutive days (slow leaks show over several days)."""
    net = get_network()
    days = list(day) if isinstance(day, (list, tuple)) else [day]
    det = detect(b, days)
    if not det.alarm:
        return SkepticVerdict(verdict=SkepticKind.no_alarm, reason="Nothing unusual in this window.")

    # 1 --- sensor health (on the latest day)
    health = sensor_health(b, days[-1])
    bad = health.unhealthy
    masked = [net.sensors.index(s) for s in bad]
    if bad:
        det2 = detect(b, days, masked)
        if not det2.alarm:
            return SkepticVerdict(
                verdict=SkepticKind.sensor_fault, masked_sensors=bad,
                reason=f"Sensor(s) {', '.join(bad)} faulty; with them masked, the network looks normal.",
                numbers={"pressure_score_masked": det2.pressure_score, "zone_t_max": max(det2.zone_t.values())})

    # 2 --- replay logged operations and planned work in the twin (each on its own day)
    current = list(days)
    t_before = max(det.zone_t.values())
    for i, d in enumerate(days):
        work = [(o.event, o.detail, SkepticKind.operation) for o in d.ops_log] + \
               [(c.event, c.detail, SkepticKind.planned_work) for c in d.calendar]
        for event, detail, kind in work:
            dp, dz = event_delta(event)
            current[i] = _subtract(current[i], dp, dz)
            t_after = float(b.zone_t(current).max())
            if not detect(b, current, masked).alarm or t_after < config.Z_THR:
                return SkepticVerdict(
                    verdict=kind, masked_sensors=bad,
                    reason=f"Explained by {detail}: after replaying it in the twin, no unexplained water loss remains "
                           f"(zone t {t_before:.1f} -> {t_after:.1f}).",
                    numbers={"zone_t_before": t_before, "zone_t_after": t_after})

    # 3 --- temporary event (fire-fighting, a burst of use) that is already over (judged on the latest day)
    last = current[-1]
    z = b.pressure_z([last], masked)
    zh = np.sqrt((z ** 2).mean(1))
    fh = ((last.zone_inflow - b.zn) / b.zs).max(1)
    hot = (zh > config.HOT_Z) | (fh > config.HOT_FLOW_T)
    late_t = float(b.zone_t(current, config.LATE_HOURS, widen=2.0).max())
    single_day = len(days) == 1
    # minimum night flow (02:00-04:00): a short daytime event is over by then, a leak is not
    night_t = float(b.zone_t(current, config.NIGHT_HOURS, widen=2.0).max())
    if single_day and not det.persistence and night_t < config.LATE_T_THR and ((hot.sum() <= 4 and not hot[-6:].any())
                       or (late_t < config.LATE_T_THR and not (zh[-6:] > config.HOT_Z).any())):
        return SkepticVerdict(
            verdict=SkepticKind.temporary, masked_sensors=bad,
            reason=f"Short event ({int(hot.sum())} unusual hours) that has already ended; watching, not dispatching.",
            numbers={"hot_hours": float(hot.sum()), "late_zone_t": late_t})

    # 4 --- nothing explains it
    return SkepticVerdict(
        verdict=SkepticKind.leak, masked_sensors=bad,
        reason=(f"Persistent water loss over {len(days)} days" if not single_day else "Persistent water loss")
        + " that no operation, planned work, sensor fault or short event explains.",
        numbers={"zone_t_max": t_before, "pressure_score": det.pressure_score})
