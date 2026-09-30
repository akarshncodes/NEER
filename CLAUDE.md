# CLAUDE.md: NEER (HackSprint'26, problem SC-02)

You are building **NEER**, an agentic AI system for water-network leak management. It is built live during a 24-hour hackathon, from **30 Sep 2026 9:00 AM to 1 Oct 7:30 AM IST**, judged on agentic AI.

## What NEER does (one paragraph)
Six LangGraph agents own a leak case from first signal to proven repair:
- **Sentinel** watches zone flow meters and pressure sensors.
- **Skeptic** (a critic) tries to explain every alarm away: pump trip, valve change, planned cut, broken sensor, fire-fighting.
- **Orchestrator** plans and chooses the next-best action.
- **Detective** turns evidence into a probability map of small search areas using a WNTR digital twin.
- **Field Commander** orders an acoustic check before any dig, creates work orders and texts residents.
- **Auditor** independently proves the repair from meter data hour by hour (sequential test). It returns FIXED / PARTLY FIXED / NOT FIXED / INCONCLUSIVE and releases or holds the contractor.

A human approves every dig, valve shut-off and case closure. Every failure triggers a re-plan.

## Judging (drives every design choice)
| Criterion | Weight |
|---|---|
| Planning | 30% |
| Tool execution & MCP | 25% |
| Self-correction & resilience | 20% |
| Feasibility & impact | 15% |
| Pitch & demo | 10% |

Reviews: **10 PM** progress, **3 AM** integrated prototype, **7:30 AM** final demo. Every team member must be able to explain the code, so keep it **readable**.

## Golden rules
1. **Physics and maths live in tested Python code. The LLM plans, critiques, chooses among allowed actions, and explains.** The LLM never produces a number that a tool did not return.
2. **Contracts first.** All tool inputs and outputs and the case state are Pydantic models in `neer/schemas.py`. Do not change a contract silently; if you must change one, update `docs/SPEC.md` too.
3. **Every stage ends green.** Write pytest tests, run `uv run pytest -q`, and fix until they pass. Then commit with the message `stage N: <summary>`, and push if a remote exists.
4. **Deterministic by default.** Every random process takes a `seed`. The demo scenarios must replay identically.
5. **Never block on the network.** Every LLM call has a timeout, retries, a fallback chain, and a final rule-based fallback (`rules` provider), so the system runs with no API keys at all.
6. **Small files, clear names, docstrings in plain English.** No clever one-liners. Type hints everywhere.
7. **Honesty.** Results are simulated (EPA Net3 network). Never write accuracy claims into the UI or README that the eval suite did not produce.
8. Only work on the stage you were asked for. At the end, print: what you built, how to run it, test results, and known gaps.

## Tech stack
- Python 3.11 managed with **uv** (`uv sync`, `uv run ...`)
- `wntr` (EPANET hydraulic simulator), numpy, pandas, networkx
- `pydantic` v2
- `mcp` (official Python SDK, FastMCP) for the 4 MCP servers, and `langchain-mcp-adapters` for agents to call them
- `langgraph` (+ `langgraph-checkpoint-sqlite`) for agents; `langchain-groq`, `langchain-google-genai` and `langchain-ollama` as LLM providers
- `streamlit` + `plotly` for the dashboard
- `pytest`

## Repository layout (target)
```
NEER/
  CLAUDE.md            ← this file
  docs/SPEC.md         ← the technical contract (read the section for your stage)
  docs/PLAN.md         ← stages and acceptance criteria
  prompts/             ← stage prompts
  reference/           ← tested research code from earlier today (algorithm reference only, do NOT import)
  neer/
    config.py  schemas.py  logging.py
    sim/       city.py  zones.py  events.py  library.py      (Stage 1)
    engine/    baseline.py  detect.py  skeptic.py  locate.py  plan.py  acoustic.py  audit.py   (Stage 2)
    tools/     scada.py  twin.py  field.py  audit.py  resilience.py  chaos.py   (Stage 3)
    mcp_servers/ scada_server.py twin_server.py field_server.py audit_server.py (Stage 3)
    agents/    state.py  llm.py  prompts.py  nodes.py  graph.py  runner.py   (Stage 4)
    app/       dashboard.py  components.py   (Stage 5)
    eval/      scenarios.yaml  run_eval.py   (Stage 6)
  tests/
  data/cache/          ← fingerprint library cache (gitignored)
```

## Commands
- `uv sync`: install
- `uv run pytest -q`: tests
- `uv run python -m neer.agents.runner --scenario leak_20`: CLI case run (Stage 4)
- `uv run streamlit run neer/app/dashboard.py`: dashboard (Stage 5)
- `uv run python -m neer.eval.run_eval`: evaluation (Stage 6)
