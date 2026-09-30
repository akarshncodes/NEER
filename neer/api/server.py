"""NEER REST API: the backend over HTTP, for the dashboard, a city system or any client.

    uv run uvicorn neer.api.server:app --port 8000          # then open http://localhost:8000/docs

Endpoints (all JSON; interactive documentation is generated automatically at /docs):
    GET  /api/health             is the backend up? database, tool mode, which AI providers have keys
    GET  /api/scenarios          the 16 scripted scenarios
    GET  /api/tools              the 19 agent tools, grouped by MCP server, with their descriptions
    POST /api/cases              run a whole case (agents + tools + human approvals) and store it
    GET  /api/cases              all stored cases (from the SQLite case database)
    GET  /api/cases/{case_id}    one case: timeline, evidence ledger, approvals, work orders
    GET  /api/kpi                totals across all stored cases
    GET  /api/trace              the latest tool calls (the SQLite trace)

Every request is validated by Pydantic (a bad body returns HTTP 422 with the reason). Cases run one at a time
(a lock), because the simulated city is one shared object. Human approvals: a POST gives the approver's
name and role once, and the safety validator still checks every dig - a "viewer" is refused.
"""
from __future__ import annotations

import os
import threading
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from neer import config, store
from neer.agents.runner import run_case
from neer.sim.scenarios import SCENARIOS
from neer.tools.registry import SERVERS
from neer.tools.resilience import read_trace

app = FastAPI(title="NEER API", version="1.0",
              description="Evidence-driven agentic leak investigation and repair verification (HackSprint'26, SC-02). "
                          "Simulated city (EPA Net3) - not field data.")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"])
_run_lock = threading.Lock()


class CaseRequest(BaseModel):
    scenario: str = Field("leak_20", description="One of GET /api/scenarios")
    seed: int = Field(7, ge=0, le=100000, description="Same scenario + seed = same result")
    brain: Literal["rules", "chain"] = Field("rules", description="rules, or the live AI chain (needs API keys)")
    tool_mode: Literal["direct", "mcp"] = Field("direct", description="in-process tools, or the 4 MCP servers")
    approver: str = Field("Supervisor", max_length=60, description="Name recorded on every human approval")
    approver_role: Literal["supervisor", "engineer", "field crew", "viewer"] = "supervisor"


class CaseSummary(BaseModel):
    case_id: str
    scenario: str
    status: str
    verdict: str | None
    zone: str | None
    leak_lps: float | None
    visits: int
    replans: int
    contractor: str | None


@app.get("/api/health")
def health() -> dict:
    store.init()
    return {"status": "ok", "database": str(config.CASE_DB), "tables": store.counts(),
            "tool_mode_default": config.TOOL_MODE,
            "ai_providers_with_keys": {"groq": bool(os.getenv("GROQ_API_KEY")),
                                       "gemini": bool(os.getenv("GOOGLE_API_KEY")),
                                       "ollama": os.getenv("NEER_USE_OLLAMA", "0") == "1", "rules": True}}


@app.get("/api/scenarios")
def scenarios() -> list[dict]:
    return [{"name": n, "title": s.title, "expect": s.expect} for n, s in SCENARIOS.items()]


@app.get("/api/tools")
def tools() -> dict:
    return {f"{srv}-mcp": [{"name": fn.__name__, "description": (fn.__doc__ or "").strip().split("\n")[0]}
                           for fn in fns] for srv, fns in SERVERS.items()}


@app.post("/api/cases", response_model=CaseSummary)
def create_case(req: CaseRequest) -> CaseSummary:
    if req.scenario not in SCENARIOS:
        raise HTTPException(404, f"unknown scenario {req.scenario!r}; see GET /api/scenarios")
    with _run_lock:                                   # one simulated city at a time
        s = run_case(req.scenario, req.seed, mode=req.tool_mode, llm=req.brain, approver=req.approver,
                     approver_role=req.approver_role)
    return CaseSummary(case_id=s.case_id, scenario=req.scenario, status=s.status, verdict=s.verdict, zone=s.zone,
                       leak_lps=s.leak_size_lps or None, visits=s.visits, replans=s.replans, contractor=s.contractor)


@app.get("/api/cases")
def list_cases(limit: int = 100) -> list[dict]:
    return store.list_cases(min(max(limit, 1), 500))


@app.get("/api/cases/{case_id}")
def get_case(case_id: str) -> dict:
    c = store.get_case(case_id)
    if c is None:
        raise HTTPException(404, f"case {case_id} not found")
    return c


@app.get("/api/kpi")
def kpi() -> dict:
    return store.summary()


@app.get("/api/trace")
def trace(limit: int = 50) -> list[dict]:
    return read_trace(min(max(limit, 1), 500))
