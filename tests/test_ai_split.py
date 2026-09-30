"""Stage 8 tests: the AI owns interpretation and choice, rules own safety. A fake provider stands in for the LLM."""
import re

import pytest

from neer.agents import llm
from neer.agents.runner import run_case
from neer.tools.resilience import read_trace


@pytest.fixture
def fake_llm(monkeypatch):
    """Install a fake provider. handlers maps a schema name to fn(situation_text) -> answer (or raises = no answer)."""
    handlers: dict = {}
    seen: dict[str, list[str]] = {}

    class Fake:
        def __init__(self, schema):
            self.schema = schema.__name__

        def invoke(self, messages):
            text = messages[-1][1]
            seen.setdefault(self.schema, []).append(text)
            if self.schema not in handlers:
                raise RuntimeError("fake has no answer")
            return handlers[self.schema](text)

    monkeypatch.setenv("NEER_LLM_CHAIN", "groq:fake,rules")
    monkeypatch.setattr(llm, "_available", lambda p: True)
    monkeypatch.setattr(llm, "_model", lambda p, m, schema=llm.Decision: Fake(schema))
    llm.clear_decision_log()
    return handlers, seen


def _texts(s):
    return " ".join(e["text"] for e in s.timeline)


@pytest.mark.slow
def test_guard_vetoes_dismiss_of_a_real_leak(fake_llm):
    handlers, _ = fake_llm
    handlers["GateAnswer"] = lambda _: llm.GateAnswer(most_likely="operation", decision="dismiss",
                                                      reason="looks like a pump", cites=["pump"])
    s = run_case("leak_20", llm="chain")
    assert "Rule veto" in _texts(s)
    assert s.status == "closed" and s.verdict == "FIXED"               # the case was opened anyway
    veto = [r for r in s.ledger if r["dimension"] == "AI decision" and r["supports"] == "vetoed by rule"]
    assert veto and "dismiss" in veto[0]["finding"] and "rules default 'open_case'" in veto[0]["finding"]


@pytest.mark.slow
def test_valid_target_area_from_the_llm_is_used(fake_llm):
    handlers, _ = fake_llm
    picked = []

    def plan(text):
        if "nothing surveyed yet" not in text:
            raise RuntimeError("only the first plan is scripted")
        ids = re.findall(r"\('(A-\d+)'", text)
        picked.append(ids[1])                                        # the second candidate, not rules' first
        return llm.PlanAnswer(action="acoustic_check", target_area=ids[1], reason="cheaper survey", cites=[ids[1]])
    handlers["PlanAnswer"] = plan
    s = run_case("leak_20", llm="chain")
    assert s.area_history[0]["area"] == picked[0]
    first = next(e for e in s.timeline if e["agent"] == "Orchestrator")
    assert picked[0] in first["text"] and first["provider"].startswith("groq:fake")
    assert s.status == "closed" and s.verdict == "FIXED"


@pytest.mark.slow
def test_invalid_target_area_falls_back_to_rules(fake_llm):
    handlers, _ = fake_llm
    handlers["PlanAnswer"] = lambda _: llm.PlanAnswer(action="acoustic_check", target_area="A-999", reason="x")
    s = run_case("leak_20", llm="chain")
    recs = [r for r in llm.DECISION_LOG if r.agent == "Orchestrator"]
    assert recs and all(r.provider == "rules" and r.guard_rejections == 2 for r in recs)
    assert s.status == "closed" and s.verdict == "FIXED"


@pytest.mark.slow
def test_gather_more_runs_the_tool_then_decides(fake_llm):
    handlers, seen = fake_llm
    answers = iter([llm.GateAnswer(most_likely="sensor_fault", decision="gather_more",
                                   missing_evidence=["get_pressure"], reason="need the pressure picture"),
                    llm.GateAnswer(most_likely="leak", decision="open_case", reason="pressure confirms")])
    handlers["GateAnswer"] = lambda _: next(answers)
    s = run_case("leak_20", llm="chain")
    assert any(r["tool"] == "get_pressure" and r["agent"] == "Skeptic" for r in read_trace(2000))
    assert "Extra check - get_pressure" in _texts(s)
    assert len(seen["GateAnswer"]) == 2 and "get_pressure: anomaly score" in seen["GateAnswer"][1]
    assert s.status == "closed" and s.verdict == "FIXED"


def test_gather_more_without_naming_evidence_is_rejected(fake_llm):
    """Schema-level guard: gather_more must name the missing evidence, otherwise the chain ends in rules."""
    handlers, _ = fake_llm
    handlers["GateAnswer"] = lambda _: llm.GateAnswer(most_likely="leak", decision="gather_more", reason="?")
    from neer.agents.nodes import skeptic_gate
    from neer.agents.runner import start_case
    from neer.agents.state import CaseState
    from neer.agents.toolbox import call
    start_case("leak_20", 7, llm="chain")
    zf = call("Sentinel", "get_zone_flow", days=1)
    worst = max(zf["zones"], key=lambda z: z["t_score"])
    out = skeptic_gate(CaseState(case_id="C", zone=worst["zone"], tier="CONFIRMED", sim_day=zf["day"],
                                 alarm_excess_lps=worst["excess_lps"], alarm_t=worst["t_score"]))
    assert out.get("status") != "waiting"
    assert llm.DECISION_LOG[-1].provider == "rules" and llm.DECISION_LOG[-1].guard_rejections == 2
