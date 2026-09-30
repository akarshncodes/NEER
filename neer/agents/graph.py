"""The NEER LangGraph: who runs after whom.

START -> sentinel -(no alarm)-> END
                  -> skeptic_gate -(dismiss)-> END (watch) | -(gather more: a day)-> wait_day
                                  -> detective -(gather more: a day)-> wait_day
                                  -> detective -> orchestrator -> skeptic_review -(send back)-> detective
                                                                                 -> approve_plan [HUMAN] -> field_commander
orchestrator (after the first plan) -> field_commander (acoustic) | approve_dig [HUMAN] -> field_commander (dig)
field_commander -> orchestrator (acoustic result / empty dig) | auditor (repaired)
auditor -FIXED-> END | -NOT_FIXED-> orchestrator | -PARTLY-> detective | -INCONCLUSIVE-> auditor (wait) / escalate
"""
from __future__ import annotations

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from neer.agents import nodes as N
from neer.agents.state import CaseState


def _after_sentinel(s: CaseState) -> str:
    return "skeptic_gate" if s.status == "open" else END


def _after_gate(s: CaseState) -> str:
    if s.status == "waiting":
        return "wait_day"
    return "detective" if s.status == "open" else END


def _after_detective(s: CaseState) -> str:
    if s.status == "waiting":
        return "wait_day"
    return "orchestrator" if s.last_event != "inconclusive" else "escalate"


def _after_orchestrator(s: CaseState) -> str:
    if s.next_action == "escalate":
        return "escalate"
    if s.next_action == "request_dig":
        return "approve_dig"
    if not s.plan_approved:
        return "skeptic_review"
    return "field_commander"


def _after_review(s: CaseState) -> str:
    return "approve_plan" if s.plan_reviewed else "detective"


def _after_plan_approval(s: CaseState) -> str:
    return "field_commander" if s.plan_approved else END


def _after_dig_approval(s: CaseState) -> str:
    return "field_commander" if s.next_action == "dig" else "escalate"


def _after_field(s: CaseState) -> str:
    return "auditor" if s.last_event == "repaired" else "orchestrator"


def _after_auditor(s: CaseState) -> str:
    if s.status == "closed":
        return END
    if s.last_event == "partly":
        return "detective"
    if s.last_event == "not_fixed":
        return "orchestrator"
    return "auditor" if s.inconclusive_waits < 2 else "escalate"


def build_graph(checkpointer=None):
    g = StateGraph(CaseState)
    for name in ("sentinel", "skeptic_gate", "detective", "orchestrator", "skeptic_review", "approve_plan",
                 "approve_dig", "field_commander", "auditor", "escalate", "wait_day"):
        g.add_node(name, getattr(N, name))
    g.add_edge(START, "sentinel")
    g.add_conditional_edges("sentinel", _after_sentinel)
    g.add_conditional_edges("skeptic_gate", _after_gate)
    g.add_conditional_edges("detective", _after_detective)
    g.add_conditional_edges("orchestrator", _after_orchestrator)
    g.add_conditional_edges("skeptic_review", _after_review)
    g.add_conditional_edges("approve_plan", _after_plan_approval)
    g.add_conditional_edges("approve_dig", _after_dig_approval)
    g.add_conditional_edges("field_commander", _after_field)
    g.add_conditional_edges("auditor", _after_auditor)
    g.add_edge("escalate", END)
    g.add_edge("wait_day", "sentinel")
    return g.compile(checkpointer=checkpointer or InMemorySaver())
