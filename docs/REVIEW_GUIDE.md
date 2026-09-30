# NEER review guide: UI ↔ backend, API integration, database

This guide is for the 2:30 AM review. The judges will ask about three things:

1. how the UI is connected to the backend
2. the API integration
3. the database

Read it top to bottom once. Then practise the **demo script (section 8)** and the **judge questions (section 9)**.

Every fact here is true for the code in this repository. If you don't know an answer, say "let me show you" and open the file named here.

---

## 0. The whole system in 30 seconds (learn this by heart)

> "NEER has three layers.
> **The UI** is a Streamlit Control Room.
> **The backend** is six LangGraph agents. They work only through 19 typed tools, served by 4 MCP servers, on a WNTR hydraulic digital twin. The agents are also exposed as a **FastAPI REST API**.
> **The data layer** is a SQLite case database. It stores every case, every agent message, every piece of evidence, every human approval and every work order. A second SQLite file stores the trace of every tool call.
> The UI and the API run the same agents and read and write the same database. So a case started from the API appears in the dashboard, and the other way round."

```
 ┌───────────────────────── UI ─────────────────────────┐      ┌────────── other clients ───────────┐
 │ Streamlit Control Room (neer/app/dashboard.py)       │      │ curl / Swagger /docs / city system │
 │ tabs: Control Room · Ops board · Sandbox · DB & API  │      └───────────────┬────────────────────┘
 └───────────────┬──────────────────────────────────────┘                      │ HTTP + JSON
                 │ Python call                                   ┌────────────▼────────────────┐
                 │                                               │ FastAPI REST API :8000      │
                 │                                               │ neer/api/server.py          │
                 ▼                                               └────────────┬────────────────┘
 ┌──────────────────────────── BACKEND: agents ─────────────────────────────────▼──────────────┐
 │ LangGraph state machine (neer/agents/graph.py): Sentinel → Skeptic → Detective →           │
 │ Orchestrator → Skeptic review → [HUMAN] → Field Commander → [HUMAN] → Auditor               │
 │ AI brain: Groq → Gemini → Ollama → rules (neer/agents/llm.py)   ◄── external LLM APIs       │
 └───────────────┬─────────────────────────────────────────────────────────────────────────────┘
                 │ toolbox.call()  (neer/agents/toolbox.py)
         ┌───────┴────────┐
   in-process        MCP over stdio (JSON-RPC) → 4 server processes
         └───────┬────────┘
 ┌───────────────▼──────────── 19 TOOLS (neer/tools/) ──────────────────────────────────────┐
 │ scada-mcp · twin-mcp · field-mcp · audit-mcp  + resilience + safety validator             │
 └───────────────┬───────────────────────────────────────────────────────────────────────────┘
                 ▼
 ┌──────────────────────────── DATA ────────────────────────────────────────────────────────┐
 │ data/neer.db   SQLite case database: cases, timeline, ledger, approvals, work_orders       │
 │ data/trace.db  SQLite: every tool and AI call (agent, tool, args, ok, ms)                  │
 │ data/world.pkl the live simulated city + open cases (shared by MCP processes, file lock)   │
 │ data/chaos.json chaos switches · data/cache/fingerprints.npz leak fingerprint library      │
 └───────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. How to run it (on the Mac)

### 1.1 First time only
1. Open **Terminal**. Then run `cd ~/Desktop/HACKSPRINT/NEER`.
2. Run `uv sync`. This installs Python 3.11 and every library listed in `uv.lock` into `.venv/`. It needs internet the first time, because it now also installs FastAPI and Uvicorn.
3. **Optional, for live AI:** `.env` must contain `GROQ_API_KEY=...` and `GOOGLE_API_KEY=...`. It already does. NEER works without keys too.

### 1.2 For the review: two terminals
**Terminal 1, the backend API:**
```
cd ~/Desktop/HACKSPRINT/NEER
uv run uvicorn neer.api.server:app --port 8000
```
Leave it running. It prints `Uvicorn running on http://127.0.0.1:8000`.
Open **http://localhost:8000/docs** in the browser. This is the Swagger page: every endpoint, and you can press "Try it out".

**Terminal 2, the UI:**
```
cd ~/Desktop/HACKSPRINT/NEER
uv run streamlit run neer/app/dashboard.py
```
It opens **http://localhost:8501**.

### 1.3 Quick checks before the review (5 minutes)
| Command | What you should see |
|---|---|
| `uv run pytest -q` | only dots, no F (82 test runs, 2–3 minutes) |
| `curl localhost:8000/api/health` | `{"status":"ok", ... "tables": {...}}` |
| `uv run python -m neer.agents.runner --scenario leak_20` | ends with `status: closed verdict: FIXED` |
| `uv run python -m neer.agents.runner --scenario leak_20 --mode mcp` | the same result, through the 4 MCP servers |

### 1.4 If something breaks
- **"Address already in use":** another copy is running. Use another port (`--port 8001`, or `--server.port 8502` for Streamlit), or close the old terminal.
- **Dashboard says "API not running":** Terminal 1 isn't running, or it uses a different port. You can set `NEER_API_URL=http://localhost:8001` before starting Streamlit.
- **No internet:** everything still works. Set Reasoning to "Rules only". The map switches to the schematic automatically.
- **Want a clean database for the demo:** stop both servers and delete `data/neer.db`. It is recreated automatically on the next write.

---

## 2. UI ↔ backend: how a click becomes agent work

### 2.1 What Streamlit is (they may ask)
- Streamlit is a Python web framework. You write a Python script, and Streamlit turns it into a web page (React in the browser, Streamlit's own web server in Python).
- **Every click re-runs the whole script from top to bottom.** Values that must survive a rerun live in `st.session_state` (we call it `ss`). That's where we keep the running graph, the case config and the pending approval.
- The browser and the Python server talk over a **WebSocket**. There is no page reload; only the parts that changed are redrawn.

### 2.2 The path of one click: "Start case"
File `neer/app/dashboard.py`:
1. The sidebar button `Start case` calls `start(scenario, seed, mode, llm)`.
2. `start()` calls `start_case()` in `neer/agents/runner.py`. That function:
   - sets the tool mode (`direct` or `mcp`) and the AI mode (`rules` or `chain`)
   - `World.new(scenario, seed)` builds the simulated city (EPA Net3 + 5 zones + noise), adds the scenario's hidden leak or event, and runs the days before the case
   - `build_graph()` builds the LangGraph state machine
   - creates a case id like `CASE-1EF69F` and **inserts the case row into the database** (`store.open_case`)
3. `run(init)` calls `graph.stream(...)`. LangGraph runs node after node (Sentinel, Skeptic, ...). Each node returns an **update** (new timeline lines, ledger rows, status). The UI shows each line in a live box with a 0.35 s animation.
4. **Every node is wrapped** (`_recorded` in `graph.py`). After it runs, its update is written to SQLite: the timeline, the ledger, the approvals and the case row.
5. The graph **pauses at a human gate** using LangGraph's `interrupt()`, for plan approval and dig approval. `pending_interrupt()` finds the pause, and the UI shows the yellow "Decision needed" card with **Approve / Reject**.
6. Pressing **Approve** calls `answer(True)`, which sends `Command(resume={"approved": True, "by": name, "role": role})`. The graph continues exactly where it stopped. The checkpointer (`InMemorySaver`) remembers the paused state.
7. At the end, the UI reads the final state (`graph.get_state`) and the world (KPIs, map layers) and draws everything.

### 2.3 How each part of the screen gets its data
| On screen | Where the data comes from |
|---|---|
| KPI strip (cases, digs, crew-hours, water saved, AI decisions) | `world.kpi`, kept up to date by the tools, plus the AI decision log |
| Map (heat, search areas, crew, repaired area) | the case's `areas`/`current_area` in the graph state + the world's network |
| "Water nobody paid for" chart | SCADA zone inflow from the world vs the learned baseline |
| Evidence card | graph state (zone, leak size, areas) + tool results |
| Auditor meter | `llr_trace` returned by the `verify_repair` tool |
| Agent timeline / Evidence ledger tabs | graph state `timeline` / `ledger` (the same rows are stored in `neer.db`) |
| Tool trace tab | `data/trace.db` (SQLite) |
| Live agent flowchart | the checkpoint history: which nodes ran, which is next |
| Operations board | a snapshot record of each case run in this session |
| **Database & API tab** | **`data/neer.db` directly (SQL), plus HTTP calls to the FastAPI backend** |

### 2.4 The two tool modes (a strong answer on "backend")
- **In-process (`direct`):** the agents call the tool functions in the same Python process. This is the fastest and safest mode for demos.
- **4 MCP servers:** the dashboard starts **4 separate backend processes** (scada, twin, field, audit). Every tool call travels as an MCP message over stdio. The processes share the simulated world through `data/world.pkl` under a file lock, and share the case database.
- If the MCP transport fails, `toolbox.call()` **falls back** to the direct call, and the trace records it.
- Switch mode in the sidebar with "Tools via".

### 2.5 Human approval and roles (they love this)
- The approver name and role come from the sidebar: supervisor, engineer, field crew or viewer.
- The **safety validator** (`neer/tools/safety.py`) runs **inside the tool** `create_work_order`, not only in the UI. A dig needs:
  - an acoustic "yes" in that area
  - a named approver
  - a role of supervisor or engineer
  - no other open dig on the case
- A viewer's approval is **refused**. The Orchestrator escalates to a human instead of working around the refusal, and the refusal is traced and counted.
- **Why inside the tool?** Because anything can call a tool: the UI, the API or an MCP client. The rule must hold for every caller.

---

## 3. API integration (four kinds of API, know all four)

### 3.1 Our own REST API (FastAPI): `neer/api/server.py`
**What:** a web API. Any program can use NEER over HTTP with JSON, for example a city's complaint system, a mobile app, or `curl`.
**Why FastAPI:**
- It is fast and asynchronous.
- It uses **Pydantic** for request validation, the same models as our tools.
- It generates **OpenAPI/Swagger docs** automatically at `/docs`.
- Uvicorn is the ASGI server that runs it.

| Method | Path | What it does | Example |
|---|---|---|---|
| GET | `/api/health` | backend up? database file, row counts, which AI providers have keys | `curl localhost:8000/api/health` |
| GET | `/api/scenarios` | the 16 scenarios | |
| GET | `/api/tools` | the 19 tools grouped by MCP server | |
| POST | `/api/cases` | **runs a whole case** (agents + tools + approvals) and stores it | body `{"scenario":"leak_20","seed":7,"approver":"Ravi","approver_role":"engineer"}` |
| GET | `/api/cases` | all stored cases (from SQLite) | |
| GET | `/api/cases/{case_id}` | one case: timeline, ledger, approvals, work orders | |
| GET | `/api/kpi` | totals across stored cases | |
| GET | `/api/trace?limit=50` | the latest tool calls | |

Small details they may probe:
- **Validation:** request bodies are Pydantic models (`CaseRequest`).
  - A wrong role such as `"admin"`, or a seed below 0, returns **HTTP 422** with the exact reason.
  - An unknown scenario or case returns **404**.
  - Success returns **200**.
- **Response model:** `POST /api/cases` returns a `CaseSummary`: case_id, status, verdict, zone, leak_lps, visits, replans, contractor.
- **Concurrency:** cases run **one at a time** (`threading.Lock`), because the simulated city is one shared object. Read endpoints are not locked.
- **CORS** is enabled (`CORSMiddleware`), so a browser front end on another port could call it.
- **Human approval over the API:** the POST carries the approver's name and role once. The safety validator still checks every dig, so a viewer is refused and the case is escalated.
- **Security (be honest):** there is no login or API key yet, because it runs on localhost in the demo. Next steps: an API key or OAuth2/JWT with roles, HTTPS, and rate limiting.
- **Tests:** `tests/test_api_db.py` uses FastAPI's `TestClient` to call every endpoint, including the 404 and 422 cases.

### 3.2 MCP: how the agents call their tools (the "Tools/MCP" score)
- **MCP (Model Context Protocol)** is an open standard (from Anthropic) for giving AI agents tools. It is like USB for AI tools: a server lists its tools with JSON schemas, and a client calls them.
- **Transport:** stdio. The client starts each server as a child process and exchanges **JSON-RPC** messages over stdin/stdout. That's why our logs go to **stderr**: a log line on stdout would corrupt the messages. That was challenge 3.
- **Servers** (`neer/mcp_servers/`), built with **FastMCP** from the official MCP Python SDK:

  | Server | Tools |
  |---|---|
  | `scada-mcp` (read-only) | get_zone_flow, get_pressure, sensor_health, get_ops_log, get_supply_calendar |
  | `twin-mcp` | simulate, replay_operation, locate_leak, estimate_leak_size, plan_search_areas |
  | `field-mcp` | acoustic_check, create_work_order, crew_status, notify_residents, slow_refill_instruction |
  | `audit-mcp` | verify_repair, release_contractor, case_memory, kpi_report |

- **Each tool:**
  - a Python function with type hints and a docstring; FastMCP turns them into the tool's JSON schema and description
  - returns **one JSON text** (we chose this because lists and errors were ambiguous; challenge 4)
- **Client:** `langchain-mcp-adapters` (`MultiServerMCPClient`). `toolbox.py` keeps **one long-lived session per server** on a background event loop, so there's no process start per call.
- **Every tool call passes the resilience layer** (`neer/tools/resilience.py`):
  1. Pydantic validation
  2. 10 s timeout
  3. 2 retries with back-off (0.5 s, 1 s)
  4. a **circuit breaker** per server (3 failures, then open for 60 s)
  5. failures become a readable `ToolError` instead of a crash
  6. every call is written to `trace.db`
- **Run one server alone:** `uv run python -m neer.mcp_servers.scada_server`. The test `test_mcp_servers_list_19_tools` checks that the servers list 19 tools.

### 3.3 LLM APIs: Groq, Gemini, Ollama (the AI brain)
- **Where:** `neer/agents/llm.py`. The keys are in `.env` (`GROQ_API_KEY`, `GOOGLE_API_KEY`), loaded at start-up. They are never in the code or in git (`.env` is in `.gitignore`).
- **Chain:** `groq:openai/gpt-oss-120b → gemini:gemini-3.5-flash → ollama:qwen2.5:7b → rules`. It is set by `NEER_LLM_CHAIN`, and `rules` is always last.
- **Libraries:** `langchain-groq`, `langchain-google-genai`, `langchain-ollama`, with `.with_structured_output(Schema)`. The model must answer in our Pydantic schema, for example `PlanAnswer{action, target_area, reason, cites}`.
- **Each call:**
  - a 20 s timeout (a thread pool future)
  - the answer must be **inside the allowed set** and pass the agent's **guard** (e.g. a dig only after an acoustic yes in that area)
  - on a bad answer, one retry, then the next provider, and finally `rules`
- **Rate limits:**
  - Free tiers return **HTTP 429**. `NEER_LLM_MIN_INTERVAL_S` spaces calls out.
  - A provider that fails on the **network 2 times in a row rests for 60 s**. Bad Wi-Fi never makes the demo slow.
- **Audit:** every AI decision is logged with the provider, its choice, what `rules()` would have chosen, the guard result and the evidence cited. These show as badges on the timeline and as ledger rows.
- **Rule veto:** the AI may never dismiss a clear leak (engine says leak and zone t > 4). If it tries, the rule overrides it and the veto is recorded.

### 3.4 Other external APIs
- **OpenStreetMap tiles**, for the city map (Plotly `Scattermap`). If the tiles can't load, the map automatically switches to the schematic.
- **SMS gateway** (`notify_residents`, Tamil and English) and **crew system**: these are **simulated endpoints** in field-mcp. In a real city they would point at the utility's SMS provider and work-order system. The agents wouldn't change, only the tool body.
- **SCADA:** simulated by WNTR/EPANET. In a real city, scada-mcp would read the utility's SCADA historian export, read-only.

---

## 4. Database: what is stored, where, and why

### 4.1 The case database: `data/neer.db` (SQLite), code in `neer/store.py`
**Why SQLite?**
- one file, with no server to install
- **ACID** transactions
- built into Python (`sqlite3`)
- **WAL mode** (write-ahead log), so readers don't block the writer
- several processes (dashboard, API, 4 MCP servers) can use it safely

**In production:** the same schema moves to **PostgreSQL**. For time series we would add TimescaleDB.

**Tables (the schema is in `store.py`, `SCHEMA`):**

| Table | One row per | Columns |
|---|---|---|
| `cases` | case | **case_id (PK)**, scenario, seed, brain (rules/chain), tool_mode (direct/mcp), status, tier, zone, leak_lps, verdict, visits, replans, contractor, created_at, updated_at |
| `timeline` | agent message | id (PK autoincrement), **case_id (FK → cases)**, ts, node, agent, kind, provider, text |
| `ledger` | piece of evidence | id, case_id, sim_when, dimension, finding, supports, reliability, source (tool) |
| `approvals` | human decision | id, case_id, ts, gate (plan/dig), approved (0/1), by_name, role, area |
| `work_orders` | crew order | **PK (case_id, work_order_id)**, area_id, action (acoustic/dig), status (open/done), result (yes/no/inconclusive/repaired/nothing_found), approved_by, approver_role, updated_at |

- **Indexes:** `ix_timeline_case`, `ix_ledger_case` and `ix_approvals_case` on `case_id`, so opening one case is fast.
- **Relationships:** one case has many timeline, ledger, approval and work-order rows (one-to-many). Work order ids restart per case, so the key is **composite**: (case_id, work_order_id).

**Who writes:**
1. `store.open_case()` when a case starts (runner.py)
2. `store.record_step()` **after every agent step**. The graph wraps each node in `_recorded`, which writes that step's timeline lines, ledger rows, approvals, and the case's latest status.
3. `store.save_work_order()` from the field tools, when an order is created, a survey finishes, or a dig ends. In MCP mode this write happens **inside the field-mcp server process**. It shows two processes writing one database.

**Who reads:**
- the dashboard's **Database & API** tab: counts, cases table, one case's four tables, read-only SQL box
- the REST API (`/api/cases`, `/api/cases/{id}`, `/api/kpi`)

**Safety details (they may probe):**
- **Parameterised queries** (`?` placeholders) everywhere, so values can never become SQL. This prevents SQL injection.
- **One short connection per operation** (a context manager): commit on success, **rollback** on error, always close.
- The SQL box uses a **read-only connection** (`file:neer.db?mode=ro`) and accepts one SELECT only, with a row limit. Even a sneaky `DELETE` is refused by SQLite itself (tested).
- A database error is **logged and never stops a case**. The agents keep running (golden rule: never block).
- `busy timeout = 5 s`, so a writer waits instead of failing when another process is writing.
- **Evaluations use a private copy** (`data/runs/<name>/neer.db`), so test runs don't pollute the demo database.

### 4.2 The trace database: `data/trace.db` (SQLite), code in `neer/tools/resilience.py`
- one row per tool or AI call: ts, agent, tool, args, ok, summary, ms
- used for the Tool trace tab, `/api/trace`, and the evaluation's counts (invalid tool calls, errors recovered)

### 4.3 Other stored state (and why it isn't in SQL)
| File | What it is | Why this format |
|---|---|---|
| `data/world.pkl` | the live simulated city (network, hidden leaks, day), open cases, search weights, KPIs | complex Python and NumPy objects; the 4 MCP processes load and save it under a **file lock** (`fcntl`) on every call; it's simulation state, not business records |
| `data/chaos.json` | chaos switches | so the dashboard can flip them while agents run in other processes |
| `data/cache/fingerprints.npz` | 3 leak sizes × 92 junctions of simulated pressure fingerprints | a NumPy array cache; built once in about 20 s, then reused |
| Protected baseline | "normal" per sensor and zone, versioned | lives in the world; updated only from ≥ 2 Auditor-certified clean days, and each update gets a version number |
| LangGraph checkpoints | the paused graph state during a human approval | `InMemorySaver`: survives waiting for approval, **not a restart**. Next step: `SqliteSaver` (the package is already installed) |

---

## 5. One case, end to end, through all three layers (tell it as a story)
1. **The UI:** a supervisor picks `leak_20` and presses Start, or a city system calls `POST /api/cases`.
2. **The backend:** the Sentinel calls `get_zone_flow` (scada-mcp): zone Z5 is +19.8 L/s, t = 55. The case row is written to `cases`, and the alarm is written to `timeline` and `ledger`.
3. **The Skeptic** calls `replay_operation` (twin-mcp): no pump, valve or planned work explains it. It opens the case. Its ledger row is `Operational context`.
4. **The Detective** calls `locate_leak`: A-211 25%, A-241 22%, A-251 16%, leak ≈ 20.0 ± 0.3 L/s.
5. **The Orchestrator** calls `plan_search_areas`: next-best survey A-211 (value 0.30). The Skeptic reviews the plan.
6. **The UI:** "Approve the plan". The row goes to `approvals` (gate plan, Supervisor, supervisor).
7. **The Field Commander** calls `create_work_order` + `acoustic_check` (field-mcp):
   - A-211 is quiet, so `work_orders` gets WO-001 with result no, and the plan is re-made
   - A-241 has leak noise, so WO-002 has result yes
8. **The UI:** "Approve the dig". The safety validator checks the acoustic yes and the role. WO-003 (dig) is created with approved_by and role, and the crew reports "repaired".
9. **The Auditor** calls `verify_repair` (audit-mcp). It measures the pre-repair loss itself (20.0 L/s), then tests hour by hour: FIXED at 999:1 after 3 h. It calls `release_contractor`.
   - The `cases` row becomes closed / FIXED / released.
   - `kpi_report` shows about 1,728 m³ of water saved per day.
10. **Read it back** in the Database & API tab, with `GET /api/cases/CASE-...`, or with the SQL box.

---

## 6. Numbers to know (all simulated, EPA Net3)
| Measure | Value |
|---|---|
| Agent evaluation, 16 scenarios × 5 fresh seeds | **79/80 passed** |
| Cases closed while still leaking | 0 |
| Unapproved digs | 0 |
| Invalid tool calls | 0 |
| Look-alikes that sent a crew | 0/35 |
| Wrong repairs caught | 5/5 |
| Chaos runs recovered | 20/20 |
| Ablation: tickets closed while still leaking | threshold alarm **52%** → full NEER **0%** |
| Ablation: crews sent for look-alikes | 56% → 6% |
| Engine: false alarms | 0% |
| Engine: correct zone | 96–98% |
| Engine: leak found within 3 visits | 58–75% (86–94% within 8) |
| Engine: wasted digs per leak | 0.09–0.18 |
| Tests | **82 test runs**, all passing |

Scale of the system:
- 19 tools
- 4 MCP servers
- 6 agents
- 16 scenarios
- 5 zones, 15 meters, 20 pressure sensors, 92 junctions
- 5 database tables

Ports:
- Streamlit **8501**
- API **8000**
- API docs **/docs**

---

## 7. Glossary (the small words)
- **NRW:** non-revenue water, i.e. water that never reaches a bill: leaks, theft and billing losses. NEER targets leaks.
- **DMA / zone:** a district metered area. It has meters on every pipe that crosses its border, so we know how much water goes in.
- **SCADA:** the utility's monitoring system (flows, pressures, pump states). Ours is simulated and read-only.
- **WNTR / EPANET:** US EPA hydraulic simulation software. It's our "digital twin".
- **Emitter:** EPANET's way to model a leak as an orifice (flow ∝ √pressure).
- **Evidence dimensions:** mass balance (extra water), hydraulic response (pressure dips), temporal persistence (still there at night).
- **Relative likelihood:** our area scores. They are not calibrated probabilities, and they are conservative.
- **Sequential test (SPRT):** the Auditor adds evidence hour by hour and stops as soon as it is sure. FIXED needs 999:1 odds.
- **LangGraph:** a library for agent workflows as a graph (nodes = agents, edges = who runs next), with interrupts for humans.
- **Interrupt / resume:** pause the graph for a human, then continue with `Command(resume=...)`.
- **MCP:** Model Context Protocol, a standard for AI tools. **stdio:** processes talking through stdin/stdout. **JSON-RPC:** the message format.
- **REST API:** HTTP endpoints (GET = read, POST = create or run) that return JSON. **OpenAPI/Swagger:** automatic docs for it.
- **Pydantic:** Python data models with validation. We use it for tools, API requests and AI answers.
- **ASGI / Uvicorn:** the server that runs FastAPI.
- **SQLite:** a file-based SQL database. **WAL:** write-ahead logging. **ACID:** atomic, consistent, isolated, durable. **PK/FK:** primary / foreign key. **Index:** makes lookups fast.
- **Circuit breaker:** stop calling a failing service for a while instead of hammering it.
- **Idempotent:** repeating the same request gives the same result. Our work orders are idempotent.
- **RBAC:** role-based access control (supervisor / engineer may approve digs).
- **429:** the HTTP status for "too many requests" (rate limit). **422:** invalid request body. **404:** not found.

---

## 8. Five-minute review demo (focused on UI + API + database)
1. **(30 s)** Show both terminals running. Open `localhost:8000/docs`:
   > "This is our backend's REST API, documented automatically."
2. **(60 s)** In the dashboard: `leak_20` → Start case, then Approve twice (or Autopilot).
   > "Every step you see is being written to SQLite right now."
3. **(45 s)** Set the role to **viewer** → Start case → approve the dig.
   > "Refused inside the tool, and escalated."
   Set the role back to supervisor.
4. **(60 s)** Open the **Database & API** tab:
   - "Connected to the API."
   - the row counts
   - the cases table
   - open the viewer's case: Approvals shows the attempt (by the viewer, role viewer), Work orders has **no dig**, and the Timeline shows "Dig refused"
   - open the supervisor's case: Work orders shows who approved the dig
5. **(45 s)** Press **"Run 'leak_20' through the API"**.
   > "The UI calls POST /api/cases, the backend runs the agents, stores the case, and here it is in the table."
6. **(30 s)** In the SQL box, choose "Digs and who approved them".
   > "Any auditor can query this. It's read-only; a DELETE is refused by SQLite itself."
7. **(30 s)** Optional: switch "Tools via" to **4 MCP servers** and start again.
   > "Now the same case runs through 4 separate backend processes over MCP, writing to the same database."

---

## 9. Questions they may ask, and short answers
**UI and backend**
- *Is the UI really connected to a backend, or is it all one script?*
  The UI calls the agent backend. In MCP mode the tools run as 4 separate server processes over the MCP protocol. And the same backend is exposed as a REST API that the UI also calls (the "Run through the API" button). All of them share one SQLite database.
- *How does the UI update while the agents work?*
  `graph.stream()` yields each agent's update as it finishes. Streamlit redraws the live box over its WebSocket. When the graph pauses for a human, the UI shows Approve / Reject and resumes the graph with the answer.
- *What happens if two people use it at once?*
  Each browser session has its own `session_state`. The API runs cases one at a time with a lock. SQLite in WAL mode handles concurrent readers and one writer. For real multi-user use, we'd run one simulated world per case and move to PostgreSQL.
- *What if the backend or a tool fails mid-case?*
  The resilience layer handles it: timeout, retry, circuit breaker, a readable ToolError, MCP → direct fallback. If SCADA is down, the case goes to WATCH / INCONCLUSIVE instead of guessing. You can show this with the "SCADA times out" chaos button.

**APIs**
- *Which APIs do you integrate?*
  1. our FastAPI REST API
  2. MCP (4 servers, 19 tools)
  3. LLM APIs: Groq, Gemini, local Ollama
  4. OpenStreetMap tiles
  SMS and crew systems are simulated endpoints behind field-mcp.
- *How are API keys handled?* They are in `.env`, loaded at start-up, and excluded from git. The code checks whether a key exists before calling a provider.
- *What if the LLM API is down or rate-limited?* It gets one retry, then the next provider, and finally deterministic rules, which always answer. After 2 network failures a provider rests for 60 s. Calls can be spaced out with `NEER_LLM_MIN_INTERVAL_S`.
- *How do you stop the LLM from doing something dangerous?*
  - It can only pick from an allowed set, in a strict schema, checked by a guard.
  - It never produces numbers; those come from tools.
  - The safety validator inside the tools blocks unsafe digs whoever asks.
  - A rule veto stops it from dismissing a clear leak.
- *Why MCP instead of plain function calls?* It's a standard: the same servers work with any MCP client (Claude, LangChain, other agents). The tools are separated from the agents, typed, and each can run as its own process or be swapped for a real SCADA connector.
- *How do you validate API input?* With Pydantic models. Bad input returns 422 with the reason, an unknown id returns 404, and the role must be one of four values.
- *Authentication?* Not yet, because it's local. Next is an API key or JWT with the same roles, plus HTTPS. The role check already exists in the backend (the safety validator).

**Database**
- *Which database, and why?* SQLite in WAL mode. It's one file with ACID transactions and no server, and it's safe for our several processes. In production we'd use PostgreSQL with the same schema.
- *Show me the schema.* Five tables: cases, timeline, ledger, approvals, work_orders. Show `SCHEMA` in `neer/store.py`, or run `SELECT * FROM sqlite_master` in the SQL box.
- *How do you prevent SQL injection?* Parameterised queries everywhere. The SQL box is a read-only connection that accepts one SELECT only.
- *What exactly is stored when I press Approve?* An `approvals` row with the gate, approved yes/no, name, role and area. For a dig that passes the safety validator, a `work_orders` row with approved_by and approver_role. If the role is wrong, the approval row is still stored (so there's an audit trail of the attempt), but no dig work order is created, and the timeline says "Dig refused". The timeline row "Dig approved by …" is stored too.
- *Is data lost if the app restarts?* Everything in `neer.db` and `trace.db` stays. A case paused mid-approval is held in LangGraph's in-memory checkpointer, so that pause does not survive a restart. Next step: SqliteSaver.
- *Why is the world a pickle file and not SQL?* It is a live simulation: a network graph, NumPy arrays and hidden leaks. It's shared between the MCP processes with a file lock. Business records (cases, approvals, work orders, evidence) are in SQL.
- *Is the database tested?* Yes, in `tests/test_api_db.py`:
  - a case is stored in every table
  - a refused dig never creates a work order
  - the SQL box refuses DELETE / DROP / UPDATE
  - every API endpoint works

**General**
- *Is this real data?* No. It's a simulated city (EPA Net3), and we say so everywhere. The next steps are the BattLeDIM L-Town dataset, then a utility's historical data, then one Madurai DMA pilot.
- *What is agentic about it?* The agents plan (next-best action), act through tools, check the result (the Auditor measures the loss itself), and re-plan when reality disagrees (acoustic no, NOT FIXED, PARTLY FIXED). Humans approve anything physical.

---

## 10. Honest limits (say them before they find them)
- Simulated city only; no live SCADA.
- The API has no login yet (localhost demo).
- A paused approval doesn't survive a restart (in-memory checkpointer).
- The live AI evaluation was limited by free-tier quota (13 of 337 decisions were live in the last run).
- Area scores are relative likelihoods, not probabilities.
- The map placement on Madurai is illustrative.

---

## 11. The "wow" layer (`neer/app/wow.py`, `neer/app/twin3d.py`)
All of it is plain HTML + CSS animation and Plotly. There are no extra libraries, and it reads only real case state, so no numbers are made up.
- **Hero banner:** animated water waves and falling drops, a pulsing green "LIVE" dot, the one-line pitch, and live counters (cases this session, repairs proven, m³/day saved).
- **Mission stepper:** SUSPECT → QUESTION → INVESTIGATE → ACT → VERIFY → REPLAN.
  - Finished stages fill in blue with a ✓, and the current stage **glows and pulses**.
  - The connector bar "flows" into the current stage.
  - REPLAN shows `↺ ×N` re-plans.
  - The stage is read from the case state (`wow._stage`: last_event, status, plan_approved, areas).
- **Outcome banner:**
  - **FIXED:** a green card with a stamped ✓ seal, a shine sweep, and animated count-up numbers (m³ saved per day, ₹ per day at the assumed ₹25/m³). It uses a CSS `@property` animation.
  - **Escalated:** an amber card.
  - **No crew sent:** a blue card carrying the Skeptic's reason.
- **Toasts:** pop-ups at the key moments:
  - Sentinel alarm
  - acoustic "leak heard"
  - safety validator refused a dig
  - Auditor NOT FIXED / FIXED
  They come from `wow.toast_for(update)` on every streamed agent update, and are off during "Run all demo scenarios".
- **3D twin (Twin sandbox tab):** after Simulate, the whole network is drawn as a 3D landscape. Height is the predicted pressure change from the `simulate` tool, so a leak shows as a dip around its junction. Sensors are orange diamonds and the leak is a red marker. **Drag to rotate, scroll to zoom.**

**Where to show them in the demo:**
1. The hero is visible as soon as the page opens.
2. Start `leak_20` and watch the stepper glow move and the toasts pop.
3. Autopilot: the green FIXED banner stamps in and the counters run up.
4. In the Twin sandbox, press Simulate and rotate the 3D landscape.

---

## 12. Night watch (autonomous mode): how to demo it
1. Open the first tab, **Night watch (autonomous)** → **Start the live city**.
2. Press **Run tonight's scan**. Night 1 is clean; say "600 raw readings checked, all normal".
3. Run it again. Night 2: **Case opened by NEER** in its zone, waiting for dig approval. Show the chart, then the inbox card.
4. Set the role to **viewer** → Approve dig: refused, escalated. Set it back to **supervisor** → start a new city or wait for the next case → Approve: the Auditor proves FIXED.
5. **Fast-forward 7 nights:** the calendar fills with a pump trip explained, look-alikes, and clean nights.
6. **Show on map** on a case to show the 3D / Blueprint views of it.

### Night watch and Control Room extras (latest)
- **Morning briefing:** a sunrise card in plain English covering last night, the totals so far, and what needs you (with the approver and role). It turns amber when a dig is waiting.
- **News ticker:** the last 8 nights scroll past like a control-room news line.
- **Zone tiles:** one tile per zone with tonight's extra water and t-score. A zone over the alarm line pulses red.
- **Night-water gauge:** the total unexplained water between 02:00 and 04:00 (green < 5 L/s, amber < 15, red above).
- **Play the week:** the nights go by one at a time with the calendar redrawn live. It **pauses by itself** when a dig needs a person.
- **Team chat:** the agents' timeline shown as a group chat, with an avatar per agent, human approvals on the right, AI/rules tags, and red and green bubbles for alerts and verdicts. It's in the Control Room (first sub-tab) and in each Night-watch inbox case.
- **Fixed during testing:**
  - After a case ran through the 4 MCP servers, later in-process and night-watch runs kept reading a shared world file. A dig approved later escalated by mistake. In-process mode now always uses one world in memory.
  - The header KPIs now refresh straight after each night.
