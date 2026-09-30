"""Simulated acoustic leak check (overnight logger / correlator in a search area).

Real devices are good but not perfect: they hear a leak 85 % of the time,
give a false "yes" 5 % of the time, and 5 % of surveys are INCONCLUSIVE
(traffic noise, plastic pipe) - a field result can be positive, negative or inconclusive. Only this module (and the dig) may look at
the hidden truth.
"""
from __future__ import annotations

import numpy as np

from neer import config
from neer.schemas import AcousticResult, SearchArea


def acoustic_check(area: SearchArea, true_leak_nodes: list[str], rng: np.random.Generator,
                   force_no: bool = False) -> AcousticResult:
    inside = any(n in area.junctions for n in true_leak_nodes)
    if not force_no and rng.random() < config.ACOUSTIC_INCONCLUSIVE:
        return AcousticResult(area_id=area.area_id, result="inconclusive", confidence=0.0)
    if force_no:
        hit = False
    elif inside:
        hit = rng.random() < config.ACOUSTIC_SENSITIVITY
    else:
        hit = rng.random() < config.ACOUSTIC_FPR
    return AcousticResult(area_id=area.area_id, result="yes" if hit else "no",
                          confidence=config.ACOUSTIC_SENSITIVITY)
