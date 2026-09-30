"""Stage 4 tests: the six agents run whole cases correctly, with and without chaos."""
import pytest

from neer.agents import llm
from neer.agents.runner import pending_interrupt, run_case, start_case, step_events
from neer.tools import chaos
from langgraph.types import Command


def _texts(state):
    return " ".join(e["text"] for e in state.timeline)


@pytest.mark.slow
def test_leak_case_closes_fixed():
    s = run_case("leak_20")
    assert s.status == "closed" and s.verdict == "FIXED" and s.contractor == "released"
    agents = {e["agent"] for e in s.timeline}
    assert {"Sentinel", "Skeptic", "Detective", "Orchestrator", "Field Commander", "Auditor", "Supervisor"} <= agents


@pytest.mark.slow
def test_pump_trip_is_dismissed():
    s = run_case("pump_trip")
    assert s.status in ("watch", "no_alarm") and s.visits == 0


@pytest.mark.slow
def test_wrong_repair_reopens_then_fixes():
    s = run_case("wrong_repair")
    assert "NOT FIXED" in _texts(s) and "held" in _texts(s)
    assert s.status == "closed" and s.verdict == "FIXED"


@pytest.mark.slow
def test_two_leaks_partly_then_fixed():
    s = run_case("two_leaks")
    assert "PARTLY FIXED" in _texts(s)
    assert s.status == "closed" and s.verdict == "FIXED"


@pytest.mark.slow
@pytest.mark.parametrize("scenario", ["chaos_scada", "chaos_llm", "chaos_sensor", "chaos_crew"])
def test_chaos_scenarios_still_close(scenario):
    s = run_case(scenario)
    assert s.status == "closed" and s.verdict == "FIXED"


def test_llm_bad_json_falls_back_to_rules():
    chaos.set_toggle("llm_bad_json", 1)
    d = llm.decide("Test", "sys", "situation", ["a", "b"], rules=lambda: ("a", "rule reason"))
    assert d.choice == "a" and d.provider == "rules" and d.fallbacks


def test_invalid_llm_choice_is_rejected(monkeypatch):
    class Fake:
        def invoke(self, _):
            return llm.Decision(choice="launch_rocket", reason="nope")
    monkeypatch.setenv("NEER_LLM_CHAIN", "groq:fake,rules")
    monkeypatch.setattr(llm, "_available", lambda p: True)
    monkeypatch.setattr(llm, "_model", lambda p, m: Fake())
    d = llm.decide("Test", "sys", "situation", ["dismiss", "open_case"], rules=lambda: ("open_case", "r"))
    assert d.choice == "open_case" and d.provider == "rules" and len(d.fallbacks) == 2


def test_valid_llm_choice_is_used(monkeypatch):
    class Fake:
        def invoke(self, _):
            return llm.Decision(choice="dismiss", reason="pump trip explains it")
    monkeypatch.setenv("NEER_LLM_CHAIN", "groq:fake,rules")
    monkeypatch.setattr(llm, "_available", lambda p: True)
    monkeypatch.setattr(llm, "_model", lambda p, m: Fake())
    d = llm.decide("Test", "sys", "s", ["dismiss", "open_case"], rules=lambda: ("open_case", "r"))
    assert d.choice == "dismiss" and d.provider == "groq:fake"


@pytest.mark.slow
def test_human_can_reject_the_plan():
    graph, cfg, init = start_case("leak_20")
    list(step_events(graph, cfg, init))
    req = pending_interrupt(graph, cfg)
    assert req and req["type"] == "approve_plan"
    list(step_events(graph, cfg, Command(resume={"approved": False, "by": "tester"})))
    assert graph.get_state(cfg).values["status"] == "escalated"


@pytest.mark.slow
def test_case_through_mcp_servers():
    s = run_case("leak_20", mode="mcp")
    assert s.status == "closed" and s.verdict == "FIXED"
