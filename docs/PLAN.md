# NEER build plan: 7 stages

The work goes one stage at a time. After each stage the tests must pass and the code is committed. Then Cowork reviews it before the next prompt goes out.

| Stage | What gets built | Time | Done when | Review |
|---|---|---|---|---|
| **0 · Foundation** | uv project, folder layout, `schemas.py` (all Pydantic contracts), config, logging, pytest setup | 20 min | `uv run pytest` passes; schemas import | |
| **1 · Simulated city** | Net3 + 5 zones + 15 meters + bulk meters + noise + events + city clock + cached fingerprint library | 1 h | Leak shows in the right zone's inflow; seeded runs repeat | |
| **2 · Physics engine** | Baseline, 3 witnesses, Skeptic checks, localisation, search areas, acoustic sim, sequential Auditor | 1.5 h | Statistical tests pass (zone accuracy, pump-trip dismissal, auditor accuracy) | |
| **3 · Tools + MCP** | 19 typed tools, resilience wrapper (validate, timeout, retry, circuit breaker, trace), chaos toggles, 4 FastMCP servers | 1.5 h | MCP client lists 19 tools; chaos tests pass | **10 PM review**: show stages 0–3 plus an MCP tool demo from the CLI |
| **4 · Agents** | Case state, LLM router with fallback to `rules`, 6 LangGraph agents, interrupts, checkpointing, CLI runner | 2.5 h | 4 scenarios end correctly with `rules` and with chaos | |
| **5 · Dashboard** | Streamlit Control Room: map, water bill, auditor meter, evidence card, approve buttons, trace, chaos panel | 2 h | Full demo runs in the browser | **3 AM review**: integrated prototype |
| **6 · Eval + polish** | 20-scenario eval → `docs/EVAL.md` ("passed N/20"), README, rehearsal, backup video | 1.5 h | Eval report generated; demo runs 3× in a row | **7:30 AM final** |

## How we work together
1. Paste the stage prompt from `prompts/` into Claude Code, opened in the `NEER/` folder.
2. Claude Code plans, builds, tests and commits.
3. Tell Cowork "Stage N done". Cowork runs the tests, reads the code, and sends fixes and the next prompt.
4. Keep the tested reference code in `reference/` for algorithms only; it is never imported.

## Team roles
| Member | Stages owned | Explains at review |
|---|---|---|
| 1 | Stage 1 simulator, scenarios | the city and events |
| 2 | Stages 2–3 engine and MCP tools | the physics and the 19 tools |
| 3 | Stage 4 agents | the LangGraph graph, the Skeptic and the fallback |
| 4 | Stages 5–6 dashboard and eval | the UI, eval score and pitch |
