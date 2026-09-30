"""Autonomous night watch: NEER scans the live city every night and opens cases by itself."""
from neer.live import NightWatch


def _run(nw, nights, role="engineer"):
    for _ in range(nights):
        nw.run_night()
        for cid, c in nw.cases.items():
            if c.pending:
                nw.decide(cid, True, "Ravi", role)


def test_night_watch_opens_and_closes_cases_by_itself():
    nw = NightWatch.start(7)
    _run(nw, 10)
    outcomes = [n["outcome"] for n in nw.nights]
    assert outcomes[0] == "clean"                                  # nothing hidden on night 1
    assert "case" in outcomes and "dismissed" in outcomes          # a leak found, a pump trip explained
    fixed = [c for c in nw.cases.values() if c.state().get("verdict") == "FIXED"]
    assert len(fixed) >= 2
    assert all(n["scan"]["readings"] == 600 for n in nw.nights)    # every raw reading of the day was read
    assert not nw.world.city.truth()                               # the leaks so far really were repaired


def test_night_watch_never_digs_without_a_valid_approver():
    nw = NightWatch.start(7)
    _run(nw, 3, role="viewer")
    assert nw.world.kpi["digs"] == 0
    assert any(c.state().get("status") == "escalated" for c in nw.cases.values())


def test_in_process_runs_never_reuse_the_mcp_world_file():
    import os
    from neer.agents.runner import start_case
    start_case("quiet", 7, mode="mcp")
    assert os.environ.get("NEER_WORLD_SHARED") == "1"
    start_case("quiet", 7, mode="direct")
    assert "NEER_WORLD_SHARED" not in os.environ
    os.environ["NEER_WORLD_SHARED"] = "1"
    NightWatch.start(7).run_night()                                # the live city switches back to in-memory
    assert "NEER_WORLD_SHARED" not in os.environ
