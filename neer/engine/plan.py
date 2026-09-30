"""Planner maths: from a probability map to an ordered list of small search areas.

A search area = a junction + its neighbouring junctions (about 1 km of pipe).
Soft elimination: a clean area is not set to zero, because listening devices
sometimes miss a leak - its weight is multiplied down instead.
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


def plan_search_areas(post: np.ndarray, weights: SearchWeights | None = None, n: int = 3) -> list[SearchArea]:
    """Greedy: repeatedly take the area holding the most remaining probability."""
    net = get_network()
    p = post * (weights.w if weights is not None else 1.0)
    p = p / p.sum()
    taken = np.zeros(len(net.junctions), dtype=bool)
    out: list[SearchArea] = []
    for _ in range(n):
        best = None
        for j in net.junctions:
            area = net.area(j)
            idx = [net.jindex[x] for x in area]
            mass = float(p[idx][~taken[idx]].sum())
            if best is None or mass > best[0]:
                best = (mass, j, area, idx)
        mass, j, area, idx = best
        taken[idx] = True
        out.append(SearchArea(area_id=f"A-{j}", junctions=area, probability=round(mass, 3),
                              pipe_km=net.area_pipe_km(j)))
    return out
