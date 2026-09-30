# NEER build plan: status

| Stage | What | Status | Tests |
|---|---|---|---|
| 0 · Foundation | uv project, config, Pydantic contracts, logger | ✅ | – |
| 1 · Simulated city | Net3, 5 DMAs, 15 meters, bulk meters, noise, events, scenarios, fingerprint library | ✅ | test_sim.py (12) |
| 2 · Physics engine | baseline, 3 evidence dimensions, Skeptic checks (multi-day), localisation, soft search, acoustic, 3-hypothesis sequential Auditor | ✅ | test_engine.py (17) |
| 3 · Tools + MCP | 19 tools, resilience (validate/timeout/retry/breaker/trace), chaos, 4 FastMCP servers | ✅ | test_tools.py (10) |
| 4 · Agents | 6 LangGraph agents, human interrupts, LLM chain → rules, MCP toolbox → direct fallback, wait-for-data, budget per round | ✅ | test_agents.py (13) |
| 5 · Dashboard | Streamlit Control Room: map, water bill, evidence card, Auditor meter, approvals, timeline, trace, chaos | ✅ | test_dashboard.py (1) |
| 6 · Evaluation | 16 scenarios × 5 fresh seeds → docs/EVAL.md; ablation (5 systems) → docs/ABLATION.md; engine benchmark + calibration → docs/ENGINE_REPORT.txt; README; uv.lock | ✅ | – |
| 7 · V2 upgrades | evidence ledger, next-best-action value, inconclusive field results, independent Auditor, protected versioned baseline, safety validator with roles, honest claims, new metrics | ✅ | +5 tests (56 total) |

## What each review should show
- **10 PM (progress):**
  - `uv run pytest -q` passing
  - the CLI case run in `--mode mcp`
  - MCP servers listing 19 tools
  - the engine benchmark table and the ablation table (docs/ABLATION.md)
  - a list of "challenges faced" (see below)
- **3 AM (integrated):** the Control Room running `leak_20`, `pump_trip`, `wrong_repair` and `two_leaks`, and chaos buttons pressed live.
- **7:30 AM (final):** the 7-minute pitch, the live demo (docs/DEMO.md), the eval score (docs/EVAL.md) and the ablation table.

## Challenges faced and how we solved them (for the 10 PM review)
1. **Our first accuracy claim was on unrealistically big leaks (60–170 L/s).** We re-tested on 5–40 L/s and redesigned: zone meters, bulk meters, quiet-hour weighting and size-aware fingerprints.
2. **Parallel EPANET runs overwrote each other's temp files and crashed.** Fixed with unique temp file names per run.
3. **MCP stdio got corrupted by log lines on stdout.** All logs now go to stderr.
4. **Lists and errors over MCP were ambiguous.** Every tool now returns one JSON text, and a ToolError is readable by the agent.
5. **A wrong repair made the agents search everywhere else.** The Orchestrator now re-listens at the repair site first.
6. **After a partial fix, old data pointed at the repaired leak.** The Detective now uses post-repair data only.
7. **Small leaks and false alarms on one day of data.** The Skeptic now waits for another day of data before sending anyone for signals under 6 L/s.
8. **Closing a case wrongly is the worst error.** FIXED now needs 999:1 evidence and at least 3 hours of data.
9. **The Auditor was not truly independent: it used the Detective's zone and leak size.** It now measures the pre-repair loss itself from SCADA.
10. **The baseline could learn from one lucky clean day.** It now needs at least 2 certified days, uses a rolling 14-day window, and versions every update.
11. **We called area scores "probabilities".** They are relative likelihoods, and a calibration check now shows the gap.
12. **We tested cost-aware planning.** It saved about 20% of crew-hours but added about 0.4 nights per leak, so the default finds the leak soonest (information gain breaks ties), and "cheap" mode is a switch.
13. **Our 40-case search numbers were lucky.** "Found within 3 visits" read 78–82% on one sample. A 120-leak re-run gives 58–75% (86–94% within 8 visits), and that is the number we now quote.

## Team roles
| Member | Owns | Explains |
|---|---|---|
| 1 | `neer/sim` | the city, zones, meters, events, scenarios |
| 2 | `neer/engine`, `neer/tools`, `neer/mcp_servers` | the physics, the 19 tools, resilience, chaos |
| 3 | `neer/agents` | the graph, the 6 agents, the Skeptic, the LLM fallback, human gates |
| 4 | `neer/app`, `neer/eval`, pitch | the Control Room, the eval score, the demo |
