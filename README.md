# NEER (நீர்): agentic AI leak detective for city water networks

**HackSprint'26 · VCET Madurai · Problem SC-02 · Team Vector Zero**

> Doesn't panic. Doesn't guess. Never trusts "job done" without proof.

Six LangGraph agents own a leak case from the first signal to a proven repair. They use **19 tools on 4 MCP servers**, a **WNTR hydraulic digital twin**, and a human who approves every dig.

![architecture](docs/architecture.png)

## The agents
| Agent | Job | Hard limit |
|---|---|---|
| **Sentinel** | Watches every zone's water bill (flow meters) and pressure; three witnesses; 2–3-day slow-leak check | Cannot dispatch |
| **Skeptic** (critic) | Tries to explain every alarm away: replays pump/valve actions and planned work in the twin, checks sensor health and short events. Asks to **wait for more data** when a signal is small. Reviews the plan. | Cannot approve its own plan |
| **Detective** | Flow picks the zone, pressure fingerprints pick the area; leak size ± uncertainty | Numbers only from tools |
| **Orchestrator** (planner) | Next-best action; re-plans after every acoustic "no", NOT FIXED or PARTLY FIXED; re-listens at a failed repair site; budget per search round, then escalates | Cannot skip a human gate |
| **Field Commander** | Acoustic check before any dig, work orders, Tamil/English SMS, slow-refill instruction | No dig without an acoustic "yes" **and** a named approver (enforced inside the tool) |
| **Auditor** | Independent, hour-by-hour sequential test on meter data only: FIXED / PARTLY FIXED / NOT FIXED / INCONCLUSIVE; releases or holds the contractor | Never reads the crew's claim; FIXED needs 999:1 evidence |

**Three self-correction loops:**
- **Tool:** validation, timeout, retry, circuit breaker, MCP → direct fallback.
- **Reasoning:** Skeptic gate and plan review; the LLM chain falls back to `rules`.
- **Reality:** acoustic "no", NOT FIXED and PARTLY FIXED each trigger a re-plan.

## Run it
```bash
cd NEER
uv sync                                    # installs everything from uv.lock (Python 3.11)
cp .env.example .env                       # optional: add GROQ_API_KEY / GOOGLE_API_KEY for the LLM chain
uv run pytest -q                           # 51 tests (~1-2 min; first run builds the leak library ~20 s)
uv run python -m neer.agents.runner --list                     # all scenarios
uv run python -m neer.agents.runner --scenario leak_20         # a whole case in the terminal
uv run python -m neer.agents.runner --scenario leak_20 --mode mcp   # same, through the 4 MCP servers
uv run streamlit run neer/app/dashboard.py                     # the Control Room
uv run python -m neer.eval.run_eval --seeds 21,22,23,24,25     # evaluation -> docs/EVAL.md
uv run python scripts/engine_report.py 40                      # physics-engine benchmark
```
NEER runs with **no API keys**: the `rules` brain is the last link of the LLM chain (Groq → Gemini → Ollama → rules). With keys in `.env`, choose "LLM chain" in the dashboard or pass `--llm chain`.

Each MCP server can also run on its own, e.g. `uv run python -m neer.mcp_servers.scada_server` (stdio).

## Results (simulated, EPA Net3 network, harsh noise)
- **Agent evaluation on 5 held-out seeds: passed 76/80 runs.**
  - 0 cases wrongly closed while a leak was still running.
  - All 4 non-passing runs ended safely (escalated to a human, or on watch).
  - 20/20 chaos runs recovered and closed FIXED.
  - 5/5 wrong repairs were caught, with the contractor held.
  - Look-alike events sent a crew 1 time out of 35.
  - Full table: [`docs/EVAL.md`](docs/EVAL.md).
- **Physics engine benchmark (40 cases per row):** see [`docs/ENGINE_REPORT.txt`](docs/ENGINE_REPORT.txt), covering detection, Skeptic accuracy per event type, zone accuracy, leaks found within 3 visits, wasted digs, and Auditor accuracy and speed.

## Honest limits
- This is a simulated city (the EPA Net3 benchmark), not field data. The next steps are the BattLeDIM L-Town dataset, then one Madurai DMA.
- Very small leaks (≤ 5–10 L/s) can take several days to show. NEER waits for more data instead of guessing.
- NEER promises an **area** (~1 km of pipe), not a GPS point; the acoustic check pinpoints within it.
- A rare persistent meter bias can open a false case. NEER searches, finds nothing, and escalates to a human, costing field visits but never closing a case wrongly.
- Intermittent (few-hours-a-day) supply needs a "supply-window mode". It is designed but not built.

## Repository map
```
neer/sim/          simulated city: Net3, 5 DMAs, 15 meters, noise, events, scenarios, fingerprint library
neer/engine/       physics & statistics: baseline, 3 witnesses, Skeptic checks, localisation, search, acoustic, Auditor
neer/tools/        19 tools + resilience layer + chaos switches + shared world
neer/mcp_servers/  scada-mcp, twin-mcp, field-mcp, audit-mcp (FastMCP, stdio)
neer/agents/       LangGraph graph, 6 agents, LLM router, MCP toolbox, CLI runner
neer/app/          Streamlit Control Room
neer/eval/         end-to-end evaluation
tests/             51 tests (sim, engine, tools/MCP, agents, dashboard)
reference/         research code from earlier (algorithm reference only)
```
