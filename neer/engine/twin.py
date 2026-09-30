"""The digital twin: NEER's own copy of the network (no noise, no hidden truth).

Agents use it as a sandbox: "what would this pump trip / valve / planned work
do to pressure and zone flow?"
"""
from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
from pydantic import TypeAdapter

from neer.schemas import Event
from neer.sim.hydraulics import run_day, zone_net_inflow
from neer.sim.network import get_network

_event = TypeAdapter(Event)


@lru_cache(maxsize=1)
def _base():
    r = run_day()
    return r.pressure, zone_net_inflow(r.meter_flow, r.bulk_demand)


@lru_cache(maxsize=256)
def _delta_cached(event_json: str):
    e = _event.validate_json(event_json)
    r = run_day([e])
    p0, z0 = _base()
    net = get_network()
    dp = (r.pressure - p0)[:, net.sensor_index]
    dz = zone_net_inflow(r.meter_flow, r.bulk_demand) - z0
    return dp, dz


def event_delta(event: dict) -> tuple[np.ndarray, np.ndarray]:
    """(pressure change at the 20 sensors, zone inflow change) caused by one event, per hour."""
    return _delta_cached(json.dumps(event, sort_keys=True))
