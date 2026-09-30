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
    dims = {row["dimension"] for row in s.ledger}
    assert {"Mass balance", "Operational context", "Hydraulic localisation", "Field evidence",
            "Independent audit"} <= dims
    assert all(row["source"] for row in s.ledger)
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


@pytest.mark.slow
def test_unauthorised_role_cannot_dig():
    s = run_case("leak_40", approver="Visitor", approver_role="viewer")
    assert s.status == "escalated" and s.verdict is None
    assert "Dig refused" in _texts(s)


def test_invalid_llm_choice_falls_through_to_rules(monkeypatch):
    """Fake providers (no network) that answer outside the allowed set are rejected, then `rules` answers."""
    calls = []

    class FakeModel:
        def __init__(self, name):
            self.name = name

        def invoke(self, _messages):
            calls.append(self.name)
            return llm.Decision(choice="launch_rockets", reason="not allowed")

    monkeypatch.setenv("NEER_LLM_CHAIN", "groq:fake1,gemini:fake2,rules")
    monkeypatch.setenv("GROQ_API_KEY", "x")
    monkeypatch.setenv("GOOGLE_API_KEY", "x")
    monkeypatch.setattr(llm, "_model", lambda provider, model: FakeModel(provider))
    llm.clear_decision_log()

    d = llm.decide("Orchestrator", "sys", "situation", ["acoustic_check", "escalate"],
                   lambda: ("acoustic_check", "rules pick"))

    assert d.provider == "rules" and d.choice == "acoustic_check"
    assert calls == ["groq", "groq", "gemini", "gemini"]          # each provider: first try + one retry
    assert sum("not in allowed set" in f for f in d.fallbacks) == 4
    rec = llm.DECISION_LOG[-1]
    assert rec.guard_rejections == 4 and rec.rules_choice == "acoustic_check"
