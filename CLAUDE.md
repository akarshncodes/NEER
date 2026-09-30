# CLAUDE.md: NEER (HackSprint'26, problem SC-02)

NEER is an agentic AI system for water-network leak management, built during a 24-hour hackathon (30 Sep 2026 9:00 AM – 1 Oct 7:30 AM IST) that is judged on agentic AI.
**Status: stages 0–6 are built and tested.** Read `README.md` first, then the part of `docs/SPEC.md` you need.

## Judging
| Criterion | Weight |
|---|---|
| Planning | 30% |
| Tool execution & MCP | 25% |
| Self-correction & resilience | 20% |
| Feasibility & impact | 15% |
| Pitch & demo | 10% |

Reviews are at **10 PM**, **3 AM** and the **7:30 AM** final. Every team member must be able to explain the code, so keep it readable.

## Golden rules (keep them when changing anything)
1. **Physics and maths live in tested code** (`neer/engine`). The LLM only plans, critiques, chooses from an allowed set, and explains. It never produces a number that a tool did not return.
2. **Contracts are in `neer/schemas.py`.** If you change one, update `docs/SPEC.md`.
3. **Tests must stay green.**
   - Run `uv run pytest -q` (51 tests; use `-m "not slow"` for a quick check).
   - Then commit as `stage/feature: summary`.
4. **Deterministic:** every random process takes a seed. Demo scenarios must replay identically (`neer/sim/scenarios.py`).
5. **Never block on the network.** The LLM chain ends in `rules`; the MCP transport falls back to direct calls.
6. **Safety gates live inside the tools as well as the graph.** A dig needs an acoustic "yes" and a named approver. The contractor is released only on FIXED.
7. **Honesty:** only quote numbers produced by `neer/eval/run_eval.py` or `scripts/engine_report.py`.
8. Small files, plain-English docstrings, type hints.

## Layout
- `neer/config.py`: every constant (tested values)
- `neer/schemas.py`: contracts
- `neer/log.py`: logger (stderr, because stdout belongs to MCP)
- `neer/sim/`: network.py (zones, meters, areas) · hydraulics.py (the only WNTR caller; unique temp files) · city.py (SimCity, DayData) · library.py (fingerprints, cached) · scenarios.py
- `neer/engine/`: baseline · detect (3 witnesses) · skeptic · twin (event deltas) · locate · plan (soft elimination) · acoustic · audit (3-hypothesis sequential test) · bench
- `neer/tools/`: scada · twin · field · audit (19 tools) · resilience (validate/timeout/retry/breaker/trace) · chaos · world (shared state; file-locked when `NEER_WORLD_SHARED=1`) · registry
- `neer/mcp_servers/`: common.py builds FastMCP servers returning one JSON text per call · client.py gives the stdio connection settings
- `neer/agents/`:
  - state.py (CaseState)
  - llm.py (router + `rules`)
  - prompts.py
  - toolbox.py (MCP or direct)
  - nodes.py (the 6 agents + human gates + wait)
  - graph.py
  - runner.py (CLI)
- `neer/app/`: dashboard.py (Streamlit Control Room) · components.py (figures, CSS)
- `neer/eval/run_eval.py`: writes docs/EVAL.md

## Commands
```
uv sync
uv run pytest -q
uv run python -m neer.agents.runner --scenario leak_20 [--mode mcp] [--llm chain]
uv run streamlit run neer/app/dashboard.py
uv run python -m neer.eval.run_eval --seeds 21,22,23,24,25
uv run python scripts/engine_report.py 40
```
