"""Planner maths: from a relative-likelihood map to the next-best search actions.

A search area = a junction + its neighbouring junctions (about 1 km of pipe).

Next-best action (not simply "the most likely area"):
    value = (chance this survey finds the leak + IG_WEIGHT x expected information gain)
            / (1 + COST_WEIGHT x crew-hours)
We tested it (90 leaks, Net3): putting crew-hours in the denominator (COST_WEIGHT 0.2) cut
crew-hours ~20 % but added ~0.4 extra nights per leak. Every night a 20 L/s leak wastes
~1,700 m3, so the default ("fast" mode) is COST_WEIGHT = 0: find the leak soonest, with
information gain as the tie-breaker. A utility short of crews can switch to "cheap" mode.

Soft elimination: a clean area is not set to zero, because listening devices
sometimes miss a leak - its weight is multiplied down instead.
Scores are RELATIVE likelihoods over the network, not calibrated probabilities.
"""
from __future__ import annotations

import numpy as np

from neer import config
from neer.schemas import SearchArea
from neer.sim.network import get_network


class SearchWeights:
    """Per-junction weights that record what the field has already ruled (softly) out."""

    def __init__(self) -> None:
        self.w = np.ones(len(get_network().junctions))

    def downweight(self, junctions: list[str], factor: float) -> None:
        net = get_network()
        for j in junctions:
            self.w[net.jindex[j]] *= factor

    def acoustic_no(self, junctions: list[str]) -> None:
        self.downweight(junctions, config.SOFT_ACOUSTIC_NO)

    def empty_dig(self, junctions: list[str]) -> None:
        self.downweight(junctions, config.SOFT_EMPTY_DIG)


def _entropy(p: np.ndarray) -> float:
    q = p[p > 0]
    return float(-(q * np.log(q)).sum())


def survey_hours(pipe_km: float) -> float:
    """Crew-hours for an overnight acoustic survey: set-up + walking the pipe."""
    return config.SURVEY_SETUP_H + config.SURVEY_H_PER_KM * pipe_km


def acoustic_value(p: np.ndarray, idx: list[int], pipe_km: float) -> tuple[float, float, float]:
    """(information gain in nats, chance of finding the leak, crew-hours) for an acoustic check."""
    s, f = config.ACOUSTIC_SENSITIVITY, config.ACOUSTIC_FPR
    inside = np.zeros(len(p), dtype=bool)
    inside[idx] = True
    py, pn = p * np.where(inside, s, f), p * np.where(inside, 1 - s, 1 - f)
    Py, Pn = py.sum(), pn.sum()
    ig = _entropy(p) - (Py * _entropy(py / Py) + Pn * _entropy(pn / Pn))
    return float(ig), float(p[idx].sum() * s), survey_hours(pipe_km)


def plan_search_areas(post: np.ndarray, weights: SearchWeights | None = None, n: int = 3,
                      order: str = "value") -> list[SearchArea]:
    """Top-n distinct search areas, ordered by next-best-action value (default) or by relative likelihood."""
    net = get_network()
    p = post * (weights.w if weights is not None else 1.0)
    p = p / p.sum()
    cands = []
    for j in net.junctions:
        area = net.area(j)
        idx = [net.jindex[x] for x in area]
        km = net.area_pipe_km(j)
        ig, find, hours = acoustic_value(p, idx, km)
        value = (find + config.IG_WEIGHT * ig) / (1 + config.COST_WEIGHT * hours)
        cands.append((j, area, idx, float(p[idx].sum()), km, ig, hours, value))
    key = 7 if order == "value" else 3
    cands.sort(key=lambda c: -c[key])
    taken = np.zeros(len(net.junctions), dtype=bool)
    out: list[SearchArea] = []
    for j, area, idx, mass, km, ig, hours, value in cands:
        if taken[idx].any():
            continue                          # keep areas distinct
        taken[idx] = True
        out.append(SearchArea(area_id=f"A-{j}", junctions=area, likelihood=round(mass, 3), pipe_km=km,
                              info_gain=round(ig, 3), cost_hours=round(hours, 2), action_value=round(value, 3)))
        if len(out) == n:
            break
    return out
