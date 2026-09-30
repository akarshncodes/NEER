"""Run a NEER case end to end from the command line.

    uv run python -m neer.agents.runner --scenario leak_20 --auto-approve
    uv run python -m neer.agents.runner --scenario pump_trip --mode mcp
    uv run python -m neer.agents.runner --list
"""
from __future__ import annotations

import argparse
import os
import uuid
from typing import Callable, Iterator, Optional

from langgraph.types import Command
from rich.console import Console

from neer import store
from neer.agents.graph import build_graph
from neer.agents.state import CaseState, TimelineEntry
from neer.sim.scenarios import SCENARIOS
from neer.tools.resilience import clear_trace
from neer.tools.world import World, set_world

COLOURS = {"Sentinel": "cyan", "Skeptic": "red", "Detective": "blue", "Orchestrator": "bold blue",
           "Field Commander": "magenta", "Auditor": "green", "Supervisor": "yellow"}


def start_case(scenario: str, seed: int = 7, mode: str = "direct", llm: str = "rules"):
    """Create the world for a scenario and a fresh graph + thread. Returns (graph, config, initial_state)."""
    os.environ["NEER_TOOL_MODE"] = mode
    if mode == "mcp":
        os.environ["NEER_WORLD_SHARED"] = "1"          # 4 server processes share the world through the file
    else:
        os.environ.pop("NEER_WORLD_SHARED", None)       # in-process: one world in memory (never a stale file)
    if llm == "rules":
        os.environ["NEER_LLM_CHAIN"] = "rules"
    set_world(World.new(scenario, seed))
    clear_trace()
    graph = build_graph()
    case_id = f"CASE-{uuid.uuid4().hex[:6].upper()}"
    store.open_case(case_id, scenario, seed, llm, mode)          # the case database gets a row straight away
    cfg = {"configurable": {"thread_id": case_id}, "recursion_limit": 80}
    return graph, cfg, CaseState(case_id=case_id, scenario=scenario)


def step_events(graph, cfg, payload) -> Iterator[tuple[str, dict]]:
    """Stream node updates until the graph ends or pauses for a human. Yields (node, update)."""
    for chunk in graph.stream(payload, cfg, stream_mode="updates"):
        for node, update in chunk.items():
            if isinstance(update, dict):          # skip "__interrupt__" markers
                yield node, update


def pending_interrupt(graph, cfg) -> Optional[dict]:
    snap = graph.get_state(cfg)
    for task in snap.tasks:
        for it in task.interrupts:
            return it.value
    return None


def run_case(scenario: str, seed: int = 7, auto_approve: bool = True, mode: str = "direct", llm: str = "rules",
             on_entry: Callable[[TimelineEntry], None] | None = None, approver: str = "Supervisor",
             approver_role: str = "supervisor") -> CaseState:
    """Run a whole case; with auto_approve the supervisor says yes to every request."""
    graph, cfg, init = start_case(scenario, seed, mode, llm)
    payload = init
    while True:
        for _, update in step_events(graph, cfg, payload):
            for e in update.get("timeline", []) or []:
                if on_entry:
                    on_entry(e if isinstance(e, TimelineEntry) else TimelineEntry(**e))
        req = pending_interrupt(graph, cfg)
        if req is None:
            break
        if not auto_approve:
            raise RuntimeError(f"waiting for human approval: {req}")
        payload = Command(resume={"approved": True, "by": approver, "role": approver_role})
    return CaseState(**graph.get_state(cfg).values)


def main() -> None:
    ap = argparse.ArgumentParser(description="Run a NEER case")
    ap.add_argument("--scenario", default="leak_20")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--mode", choices=["direct", "mcp"], default=os.getenv("NEER_TOOL_MODE", "direct"))
    ap.add_argument("--llm", choices=["rules", "chain"], default="rules")
    ap.add_argument("--auto-approve", action="store_true", default=True)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    con = Console()
    if a.list:
        for s in SCENARIOS.values():
            con.print(f"[bold]{s.name:15}[/bold] {s.title}  (expect: {s.expect})")
        return
    con.rule(f"NEER - scenario [bold]{a.scenario}[/bold] (seed {a.seed}, tools via {a.mode}, llm {a.llm})")

    def show(e: TimelineEntry) -> None:
        c = COLOURS.get(e.agent, "white")
        prov = f" [dim]\\[{e.provider}][/dim]" if e.provider else ""
        con.print(f"[{c}]{e.agent:>15}[/{c}] | {e.text}{prov}")

    final = run_case(a.scenario, a.seed, mode=a.mode, llm=a.llm, on_entry=show)
    con.rule(f"status: [bold]{final.status}[/bold]  verdict: {final.verdict}  visits: {final.visits}  "
             f"re-plans: {final.replans}  contractor: {final.contractor}")


if __name__ == "__main__":
    main()
