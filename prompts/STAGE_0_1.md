# Claude Code prompt: Stage 0 (foundation) + Stage 1 (simulated city)

Paste everything below the line into Claude Code, opened in the `NEER/` folder.

---

We are building NEER for a 24-hour agentic-AI hackathon. First read `CLAUDE.md`, `docs/PLAN.md` and sections 1 and 3.1 of `docs/SPEC.md`. `reference/twin.py` and `reference/sensors.py` contain earlier tested code for the city. Use them as an algorithm reference only: re-implement cleanly and do not import them.

Your job now is **Stage 0 + Stage 1 only**. Start by giving me a short plan (files, key classes, tests). Then implement without waiting for approval.

## Stage 0: foundation
1. Create a uv project (Python 3.11) named `neer`.
   - Dependencies: wntr, numpy, pandas, networkx, pydantic>=2, pyyaml, mcp, langgraph, langgraph-checkpoint-sqlite, langchain-core, langchain-mcp-adapters, langchain-groq, langchain-google-genai, langchain-ollama, streamlit, plotly, rich.
   - Dev: pytest.
   - If a package fails to resolve, pin a working version and note it.
2. Create the package layout from CLAUDE.md with empty `__init__.py` files. Also add `.gitignore` (`data/cache/`, `data/*.db`, `.env`, `__pycache__`, `.venv`) and `.env.example` listing `GROQ_API_KEY`, `GOOGLE_API_KEY`, `OLLAMA_BASE_URL`, `NEER_LLM_CHAIN`, `NEER_TOOL_MODE`.
3. `neer/config.py`: every constant from SPEC section 1 in one place (sensor list, bulk customers, safe valves, noise levels, library sizes, paths), plus the engine parameters from section 2 (z_thr, temper, soft-elimination factors, acoustic sensitivity and FPR, SPRT threshold and noise inflation).
4. `neer/schemas.py`: Pydantic v2 models for **all** contracts in SPEC:
   - events (Leak, PumpTrip, ValveClosure, FireDraw, PlannedCut, StuckSensor, SensorOffset, as a discriminated union)
   - DayData
   - ZoneFlowReport, PressureReport, SensorHealth
   - OpsEvent, CalendarEntry
   - SkepticVerdict
   - SearchArea, LocateResult
   - AcousticResult, WorkOrder, CrewStatus
   - AuditVerdict (FIXED / PARTLY_FIXED / NOT_FIXED / INCONCLUSIVE)
   - ToolError
   - EvidenceItem, PlanStep
   - CaseState (SPEC 4.1)

   Give every field a short description (it becomes the MCP tool schema later).
5. `neer/logging.py`: a rich-based logger helper.
6. `git init` if needed. If a remote is configured, push after each commit.

## Stage 1: simulated city (`neer/sim/`)
Implement SPEC section 1 exactly:
- `zones.py`
  - zones via modularity, with stable Z1..Z5 names
  - the 15 border meters and the signed incidence matrix
  - bulk matrix
  - `area(junction)` and `area_pipe_km(junction)`
- `events.py`: apply each event type to a fresh WNTR model (leak via emitter coefficient, pump-trip controls, valve closure, fire demand pattern, planned cut). Stuck sensor and offset are applied to readings after the simulation.
- `city.py`
  - `SimCity(seed)` with hidden demand bias and meter bias
  - 7 history days generated on creation
  - `add_event`, `remove_leak`, `advance_day() -> DayData` (pressure for the 20 sensors, zone net inflow, ops log, calendar)
  - `history`, and `truth()` for the hidden leaks
  - Keep one simulation to about 0.1 s: build the base WaterNetworkModel once and copy or modify it per day if WNTR allows; otherwise re-load it.
- `library.py`: the fingerprint library (3 sizes × 92 junctions), `QREF`, and a cache in `data/cache/fingerprints.npz` with `get_library()`.

## Tests (`tests/test_sim.py`)
- 5 zones; 15 meters; 20 sensors exist in the network
- a 20 L/s leak at a random junction (seeded) raises its own zone's net inflow day-mean by 15–25 L/s, while every other zone moves by less than 3 L/s. Check 5 seeds.
- the same seed gives the same DayData; a different seed gives different data
- a pump trip appears in `ops_log`, and a planned cut appears in the calendar
- the library shape is (3, 92, 24, 92); the cache round-trips; a second load takes under 2 s

Run `uv run pytest -q` until green, then commit `stage 0-1: foundation + simulated city`.

At the end, print:
- the file tree
- test results
- the zone sizes and meter list
- one example DayData summary (zone inflow means with and without a 20 L/s leak)
- known gaps

Stop after Stage 1; do not start Stage 2.
