"""Leak fingerprint library: what a leak at each junction does to pressure.

For 3 leak sizes x 92 junctions we simulate the twin (no noise) and store
base pressure minus leak pressure (a positive number = pressure drop).
Built once (~15 s) and cached to data/cache/fingerprints.npz.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from neer import config
from neer.log import get_logger
from neer.schemas import Leak
from neer.sim.hydraulics import run_day
from neer.sim.network import emitter_coef, get_network

log = get_logger(__name__)


@dataclass
class Library:
    fp: np.ndarray       # sizes x junctions x HOURS x junctions (pressure drop, m)
    qref: np.ndarray     # sizes x junctions: leak flow (L/s) each fingerprint corresponds to
    base: np.ndarray     # HOURS x junctions: twin pressure with no leak
    sizes: tuple


def _build() -> Library:
    net = get_network()
    base = run_day().pressure
    fps, qref = [], []
    for a in config.LIB_SIZES_M2:
        c = emitter_coef(a)
        # a Leak event is expressed in L/s at REF_PRESSURE; convert the orifice area back
        lps_ref = 1000 * c * np.sqrt(config.REF_PRESSURE_M)
        rows = [base - run_day([Leak(node=j, lps=lps_ref)]).pressure for j in net.junctions]
        fps.append(np.stack(rows))
        qref.append([1000 * c * np.sqrt(max(base[:, net.jindex[j]].mean(), 1.0)) for j in net.junctions])
    return Library(fp=np.stack(fps).astype(np.float32), qref=np.array(qref), base=base,
                   sizes=tuple(config.LIB_SIZES_M2))


@lru_cache(maxsize=1)
def get_library() -> Library:
    """Load the cached library, building it the first time."""
    path = config.LIBRARY_CACHE
    if path.exists():
        z = np.load(path)
        return Library(fp=z["fp"], qref=z["qref"], base=z["base"], sizes=tuple(z["sizes"]))
    log.info("Building leak fingerprint library (one time, ~15-30 s)...")
    lib = _build()
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, fp=lib.fp, qref=lib.qref, base=lib.base, sizes=np.array(lib.sizes))
    return lib
