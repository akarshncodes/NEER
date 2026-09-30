"""Detective's maths: turn evidence into a probability for every junction.

Flow says WHICH zone (and how big the leak is); pressure fingerprints say WHERE
inside it. Each junction's fingerprint must match the observed pressure drop
at the leak size the zone meter measured.
"""
from __future__ import annotations

from typing import Optional

import numpy as np

from neer import config
from neer.engine.baseline import Baseline
from neer.sim.city import DayData
from neer.sim.library import get_library
from neer.sim.network import get_network


def posterior(b: Baseline, days: list[DayData], masked: list[int] = (),
              prior: Optional[np.ndarray] = None) -> tuple[np.ndarray, dict]:
    """Probability of the leak being at each junction, plus the numbers behind it."""
    net, lib = get_network(), get_library()
    si = net.sensor_index
    w = 1.0 / b.ps
    if len(masked):
        w = w.copy()
        w[:, list(masked)] = 0.0
    a = (b.pressure_residual(days, masked) * w).ravel()

    ex = b.zone_excess(days)
    t = ex / (b.ex_se / np.sqrt(len(days)))
    q_j = np.clip(ex[net.junction_zone], 0.5, None)          # leak size suggested by each junction's zone

    loglik = np.full(len(net.junctions), -np.inf)
    for s in range(len(lib.sizes)):
        F = (lib.fp[s][:, :, si] * w).reshape(len(net.junctions), -1)
        k_free = np.clip((F @ a) / ((F * F).sum(1) + 1e-12), 0, None)
        k = np.sqrt((q_j / lib.qref[s]) * np.maximum(k_free, 1e-6))   # blend meter size with pressure fit
        err = ((a[None, :] - k[:, None] * F) ** 2).sum(1)
        loglik = np.maximum(loglik, -0.5 * err / config.HOURS)
    loglik = loglik * config.TEMPER + 0.5 * np.clip(t, 0, None)[net.junction_zone] ** 2
    if prior is not None:
        loglik = loglik + np.log(prior + 1e-12)
    p = np.exp(loglik - loglik.max())
    p /= p.sum()
    info = {"zone_excess": ex, "zone_t": t}
    return p, info


def locate(b: Baseline, days: list[DayData], masked: list[int] = (), prior: Optional[np.ndarray] = None,
           weights=None, n_areas: int = 3):
    """Full Detective result: zone, leak size, ordered search areas and plain-English evidence."""
    from neer.engine.plan import plan_search_areas
    from neer.schemas import LocateResult

    net = get_network()
    p, info = posterior(b, days, masked, prior)
    t, ex = info["zone_t"], info["zone_excess"]
    zi = int(np.argmax(t))
    areas = plan_search_areas(p, weights, n_areas)
    evidence = [
        f"Zone {net.zone_names[zi]} takes {ex[zi]:+.1f} L/s more water than normal (t = {t[zi]:.1f}).",
        f"Pressure fingerprints matched at ~{max(ex[zi], 0):.0f} L/s; most likely area {areas[0].area_id} "
        f"({areas[0].likelihood:.0%}).",
    ]
    return LocateResult(zone=net.zone_names[zi], leak_size_lps=round(float(max(ex[zi], 0)), 1),
                        zone_t={z: round(float(v), 2) for z, v in zip(net.zone_names, t)},
                        areas=areas, evidence=evidence), p
