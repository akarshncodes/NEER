"""Sentinel's rule: the three witnesses.

  water        a zone takes clearly more water than normal     (zone t > 4)
  pressure     sensors dip more than normal days ever do        (score > threshold)
  persistence  the anomaly is still there late in the day       (hours 18-23)

Alarm = water OR pressure.  Tier: CONFIRMED (all three) > PROBABLE (+persistence) > WATCH.
"""
from __future__ import annotations

import numpy as np

from neer import config
from neer.engine.baseline import Baseline
from neer.schemas import Detection, Tier
from neer.sim.city import DayData
from neer.sim.network import get_network


def detect(b: Baseline, days: list[DayData], masked: list[int] = ()) -> Detection:
    net = get_network()
    t = b.zone_t(days)
    ex = b.zone_excess(days)
    score = b.pressure_score(days, masked)
    water = bool(t.max() > config.Z_THR)
    pressure = bool(score > b.p_thr)

    late_t = b.zone_t(days, config.LATE_HOURS, widen=2.0).max()
    late_z = np.sqrt((b.pressure_z(days, masked)[config.LATE_HOURS] ** 2).mean())
    persistence = bool(late_t > config.LATE_T_THR or late_z > config.HOT_Z)

    alarm = water or pressure
    if not alarm:
        tier = Tier.none
    elif water and pressure and persistence:
        tier = Tier.confirmed
    elif persistence:
        tier = Tier.probable
    else:
        tier = Tier.watch

    drop = b.pressure_residual(days, masked).mean(0)
    order = np.argsort(-drop)[:3]
    return Detection(
        alarm=alarm, tier=tier, water=water, pressure=pressure, persistence=persistence,
        zone_t={z: round(float(v), 2) for z, v in zip(net.zone_names, t)},
        zone_excess_lps={z: round(float(v), 2) for z, v in zip(net.zone_names, ex)},
        pressure_score=round(score, 3),
        top_dips=[(net.sensors[i], round(float(drop[i]), 3)) for i in order],
    )
