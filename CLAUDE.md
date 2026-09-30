# CLAUDE.md: NEER (HackSprint'26, problem SC-02)

NEER is an evidence-driven agentic system for closed-loop water leak investigation and repair verification (SUSPECT → QUESTION → INVESTIGATE → ACT → VERIFY → REPLAN). It was built during a 24-hour hackathon (30 Sep 2026 9:00 AM – 1 Oct 7:30 AM IST) that is judged on agentic AI.
**Status: stages 0–15 are built and tested (7 V2 upgrades · 8 AI owns the investigation · 9 pro Control Room · 10 database + REST API · 11–12 wow layer + 3D · 13 autonomous night watch · 14 fixes + UX · 15 dataset + Ask NEER).** Read `README.md` first, then the part of `docs/SPEC.md` you need.

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
   - Run `uv run pytest -q` (89 test runs; use `-m "not slow"` for a quick check).
   - Then commit as `stage/feature: summary`.
4. **Deterministic:** every random process takes a seed. Demo scenarios must replay identically (`neer/sim/scenarios.py`).
5. **Never block on the network.** The LLM chain ends in `rules`; the MCP transport falls back to direct calls.
6. **Safety gates live inside the tools as well as the graph.** `neer/tools/safety.py` requires an acoustic "yes", a named approver with role supervisor/engineer, and one open dig per case. SCADA is read-only. The contractor is released only on FIXED.
7. **Honesty:** only quote numbers produced by `neer/eval/run_eval.py`, `neer/eval/llm_eval.py`, `neer/eval/ablation.py`, `scripts/engine_report.py` or `scripts/search_bench.py`. Area scores are relative likelihoods, not calibrated probabilities. Do not claim "first agentic water system", that all NRW is leakage, or live SCADA.
8. Small files, plain-English docstrings, type hints.
9. **The Auditor stays independent:** it measures the pre-repair loss itself and never reads the crew's report or the Detective's result.
10. **Baseline memory is protected:** only Auditor-certified days, at least 2 before an update, and each update is versioned.

## Layout
- `neer/config.py`: every constant (tested values)
- `neer/schemas.py`: contracts
- `neer/log.py`: logger (stderr, because stdout belongs to MCP)
- `neer/sim/`: network.py (zones, meters, areas) · hydraulics.py (the only WNTR caller; unique temp files) · city.py (SimCity, DayData) · library.py (fingerprints, cached) · scenarios.py
- `neer/engine/`: baseline (versioned, protected) · detect (3 evidence dimensions) · skeptic · twin (event deltas) · locate · plan (next-best-action value, soft elimination) · acoustic (yes/no/inconclusive) · audit (independent 3-hypothesis sequential test) · bench
- `neer/tools/`: scada · twin · field · audit (19 tools) · safety (validator + RBAC) · resilience (validate/timeout/retry/breaker/trace) · chaos · world (shared state; file-locked when `NEER_WORLD_SHARED=1`) · registry
- `neer/mcp_servers/`: common.py builds FastMCP servers returning one JSON text per call · client.py gives the stdio connection settings
- `neer/agents/`:
  - state.py (CaseState)
  - llm.py (router + `rules`)
  - prompts.py
  - toolbox.py (MCP or direct)
  - nodes.py (the 6 agents + human gates + wait; every node writes timeline + evidence-ledger rows)
  - graph.py
  - runner.py (CLI)
- `neer/app/`: dashboard.py (Streamlit Control Room) · components.py (figures, CSS) · opsmap.py (city map on OpenStreetMap / schematic) · city3d.py (3D city view, pydeck; same layers as opsmap) · flowchart.py (live agent graph) · sandbox.py (twin what-if tab) · board.py (Kanban + impact strip) · report.py (case PDF) · geo.py (`to_latlon`, hulls, tile check) · theme.py (design tokens, light + dark, stylesheet) · static/ (self-hosted Geist fonts); theme also in `.streamlit/config.toml`
- `neer/live.py`: live city + autonomous night watch (hidden event schedule by night, 02:00–04:00 scan, opens/continues cases itself, standing policy approves listening surveys only, digs wait for a human). UI: `neer/app/nightwatch.py` (first tab). Tests: tests/test_live.py.
- `dataset/` (built by `scripts/build_dataset.py`): network CSVs, 37-day live city raw SCADA, night-scan summary, hidden truth, 16 scenario days. UI: `neer/app/datasetview.py` (Dataset tab); API: `GET /api/dataset[/file]`.
- `neer/agents/explain.py`: Ask NEER - questions about a case answered by the LLM chain from the case record only (rules explainer fallback). UI: Control Room "Ask NEER (AI)"; API: `POST /api/cases/{id}/ask`.
- `neer/store.py`: SQLite case database (data/neer.db; tables cases, timeline, ledger, approvals, work_orders). Written by graph.py (every node, via `_recorded`) and tools/field.py (work orders); read by the dashboard and the API.
- `neer/api/server.py`: FastAPI REST API (`uv run uvicorn neer.api.server:app --port 8000`, docs at /docs). `neer/app/dbview.py`: the "Database & API" tab.
- `neer/eval/run_eval.py`: writes docs/EVAL.md · `neer/eval/llm_eval.py`: docs/LLM_EVAL.md · `neer/eval/ablation.py`: docs/ABLATION.md. Each calls `config.use_private_runtime()` first, so it never shares chaos/world/trace files with a running dashboard.
- `neer/agents/llm.py`: a provider with `LLM_DOWN_AFTER` network failures in a row rests for `LLM_COOLDOWN_S`; wrong answers never rest a provider.

## Commands
```
uv sync
uv run pytest -q
uv run python -m neer.agents.runner --scenario leak_20 [--mode mcp] [--llm chain]
uv run streamlit run neer/app/dashboard.py
uv run python -m neer.eval.run_eval --seeds 41,42,43,44,45
uv run python -m neer.eval.ablation 36
uv run python scripts/engine_report.py 40
uv run python scripts/search_bench.py 120
```
