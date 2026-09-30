"""Stage 2 tests: the physics engine gives the right conclusions on seeded cases."""
import numpy as np
import pytest

from neer import config
from neer.engine import bench as B
from neer.engine.acoustic import acoustic_check
from neer.engine.baseline import Baseline
from neer.engine.plan import SearchWeights, plan_search_areas
from neer.schemas import SearchArea
from neer.sim.city import SimCity
from neer.sim.network import get_network


# ---------------------------------------------------------------- unit tests
def test_common_mode_removed():
    """A city-wide +3 % swing in every zone must not look like a leak."""
    c = SimCity(21)
    b = Baseline(c.clean_history())
    d = c.advance_day()
    d.zone_inflow = d.zone_inflow * 1.03
    assert np.all(np.abs(b.zone_t([d])) < config.Z_THR)


def test_soft_elimination_never_zero():
    w = SearchWeights()
    area = get_network().area("239")
    w.acoustic_no(area)
    w.empty_dig(area)
    assert w.w.min() > 0
    assert np.isclose(w.w[get_network().jindex["239"]], config.SOFT_ACOUSTIC_NO * config.SOFT_EMPTY_DIG)


def test_areas_are_distinct_and_ordered():
    p = np.random.default_rng(0).random(92)
    areas = plan_search_areas(p / p.sum(), n=3)
    assert len({a.area_id for a in areas}) == 3
    assert areas[0].likelihood >= areas[1].likelihood >= areas[2].likelihood


def test_acoustic_rates():
    rng = np.random.default_rng(1)
    area = SearchArea(area_id="A-239", junctions=["239"], likelihood=1, pipe_km=1)
    res_in = [acoustic_check(area, ["239"], rng).result for _ in range(4000)]
    res_out = [acoustic_check(area, ["10"], rng).result for _ in range(4000)]
    inc = np.mean([r == "inconclusive" for r in res_in + res_out])
    hit = np.mean([r == "yes" for r in res_in if r != "inconclusive"])
    fp = np.mean([r == "yes" for r in res_out if r != "inconclusive"])
    assert abs(inc - config.ACOUSTIC_INCONCLUSIVE) < 0.02
    assert abs(hit - config.ACOUSTIC_SENSITIVITY) < 0.03 and abs(fp - config.ACOUSTIC_FPR) < 0.02
    assert acoustic_check(area, ["239"], rng, force_no=True).result == "no"


def test_next_best_action_scores():
    net = get_network()
    p = np.full(92, 1e-6)
    p[net.jindex["239"]] = 0.6                  # two suspects far apart: a survey near 239 is informative
    p[net.jindex["10"]] = 0.4
    top = plan_search_areas(p / p.sum(), n=1)[0]
    assert "239" in top.junctions and top.info_gain > 0 and top.cost_hours >= config.SURVEY_SETUP_H
    flat = plan_search_areas(np.full(92, 1 / 92), n=3)
    assert all(0 <= a.likelihood <= 1 for a in flat)


def test_baseline_needs_two_certified_days_and_versions():
    c = SimCity(31)
    b = Baseline(c.clean_history())
    d1, d2 = c.advance_day(), c.advance_day()
    assert b.add_certified_clean(d1) is False and b.info()["version"] == 1    # one clean day is not enough
    assert b.add_certified_clean(d1) is False                                  # duplicates ignored
    assert b.add_certified_clean(d2) is True and b.info()["version"] == 2
    assert b.info()["clean_days"] == config.HISTORY_DAYS + 2


# ---------------------------------------------------------------- statistical tests (seeded)
@pytest.mark.slow
def test_few_false_alarms():
    assert B.false_alarm_rate(10) <= 0.1


@pytest.mark.slow
def test_detects_20_lps():
    assert B.detection_rate(10, 20) >= 0.8


@pytest.mark.slow
@pytest.mark.parametrize("kind,minimum", [("pump_trip", 0.8), ("stuck_sensor", 0.8), ("planned_work", 0.8),
                                          ("valve_closure", 0.8), ("leak", 0.7)])
def test_skeptic(kind, minimum):
    assert B.skeptic_accuracy(kind, 10)["correct"] >= minimum


@pytest.mark.slow
def test_localisation_and_search():
    r = B.search_run(20, 15)
    assert r["zone_correct"] >= 0.85
    assert r["found_within_3"] >= 0.6
    assert r["wasted_digs_per_leak"] <= 0.3


@pytest.mark.slow
@pytest.mark.parametrize("case,minimum", [("fixed", 0.8), ("not_fixed", 0.8)])
def test_auditor(case, minimum):
    assert B.audit_run(20, case, 10)["correct"] >= minimum


@pytest.mark.slow
def test_auditor_never_closes_a_live_leak():
    for case in ("not_fixed", "partly"):
        assert B.audit_run(20, case, 10)["never_wrongly_fixed"] == 1.0
