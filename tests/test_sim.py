"""Stage 1 tests: the simulated city behaves like a real metered network."""
import time

import numpy as np
import pytest

from neer import config
from neer.schemas import Leak, PlannedWork, PumpTrip, StuckSensor
from neer.sim.city import SimCity
from neer.sim.library import get_library
from neer.sim.network import get_network


def test_network_layout():
    net = get_network()
    assert len(net.zone_names) == 5
    assert len(net.meters) == 15
    assert all(s in net.jindex for s in config.PRESSURE_SENSORS)
    assert len(net.junctions) == 92


def test_search_area_contains_junction():
    net = get_network()
    a = net.area("239")
    assert "239" in a and len(a) >= 2
    assert net.area_pipe_km("239") > 0


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_leak_shows_in_its_own_zone(seed):
    net = get_network()
    city = SimCity(seed)
    normal = np.mean([d.zone_inflow.mean(0) for d in city.history], axis=0)
    node = net.junctions[np.random.default_rng(seed).integers(len(net.junctions))]
    city.add_event(Leak(node=node, lps=20))
    delta = city.advance_day().zone_inflow.mean(0) - normal
    z = net.zone_names.index(net.zone_of(node))
    assert 15 <= delta[z] <= 25, delta
    assert np.all(np.abs(np.delete(delta, z)) < 6), delta   # other zones only move by normal day-to-day noise


def test_same_seed_same_data():
    a, b, c = SimCity(7), SimCity(7), SimCity(8)
    assert np.allclose(a.history[-1].pressure, b.history[-1].pressure)
    assert not np.allclose(a.history[-1].pressure, c.history[-1].pressure)


def test_ops_log_and_calendar():
    city = SimCity(3)
    city.add_event(PumpTrip(start_h=8, end_h=13))
    city.add_event(PlannedWork(node="123", lps=15, h0=10, h1=12))
    d = city.advance_day()
    assert d.ops_log and d.ops_log[0].kind == "pump_trip"
    assert d.calendar and d.calendar[0].zone.startswith("Z")
    assert not city.advance_day().ops_log          # one-day events do not repeat


def test_stuck_sensor_and_repair():
    city = SimCity(4)
    s = config.PRESSURE_SENSORS[0]
    city.add_event(StuckSensor(sensor=s, from_h=6))
    d = city.advance_day()
    assert np.ptp(d.pressure[6:, 0]) == 0
    city.add_event(Leak(node="239", lps=10))
    assert city.remove_leak("239") and not city.remove_leak("239")
    assert city.truth() == []


def test_history_is_certified_clean():
    city = SimCity(5)
    assert len(city.clean_history()) == config.HISTORY_DAYS


def test_library_shape_and_cache():
    lib = get_library()
    assert lib.fp.shape == (3, 92, 24, 92)
    assert config.LIBRARY_CACHE.exists()
    get_library.cache_clear()
    t = time.time()
    lib2 = get_library()
    assert time.time() - t < 2
    assert np.allclose(lib.fp, lib2.fp)
    # a leak lowers pressure most at its own junction on average
    j = get_network().jindex["239"]
    assert lib.fp[1, j].mean(0).argmax() in {j} | {get_network().jindex[n] for n in get_network().area("239")}
