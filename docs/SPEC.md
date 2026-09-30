# NEER technical specification (as built)

**NEER:** an evidence-driven agentic system for closed-loop water leak investigation and repair verification.
**Loop:** SUSPECT → QUESTION → INVESTIGATE → ACT → VERIFY → REPLAN.
**Scope:** NEER targets the *physical-loss (leakage)* part of non-revenue water. It does not cover theft or billing losses.
Every number below lives in `neer/config.py`.

---

## 1. Simulated city (`neer/sim/`)
- **Network:** EPA Net3 via WNTR/EPANET, 1-hour steps, 24-hour days, 92 junctions.
  - `hydraulics.run_day` is the only WNTR caller. It uses unique temporary files per run, so parallel runs are safe.
- **Zones (DMAs):** 5 zones from modularity clustering, named Z1–Z5.
  - 15 flow meters sit on zone borders.
  - 4 bulk-metered customers (`203, 35, 123, 15`) are subtracted from zone inflow.
- **Sensors:** 20 pressure sensors, chosen for how well they tell leaks apart (`config.PRESSURE_SENSORS`).
- **Search area:** a junction plus its 1-hop junction neighbours (about 1 km of pipe), with id `A-<junction>`.
- **Leak model:** an orifice (EPANET emitter), `C = 0.75·A·√(2g)`, with the area sized for the target L/s at 40 m.
- **Hidden noise per city:**
  - demand bias N(1, 0.10)
  - day-to-day variation N(1, 0.03)
  - city-wide hourly variation N(1, 0.03)
  - pressure noise 0.1 m
  - meter bias N(1, 0.02) and reading noise 1%
  - bulk-meter noise 1%
- **Events (Pydantic, `schemas.py`):**

  | Event | Logged where |
  |---|---|
  | Leak | not logged (hidden truth) |
  | PumpTrip | ops log |
  | ValveClosure | ops log |
  | FireDraw | not logged |
  | PlannedWork (flushing / tanker filling) | calendar |
  | StuckSensor, SensorOffset | not logged (reading faults) |

- **`SimCity(seed)`:** generates 7 certified-clean history days, then `advance_day() → DayData`. Only the field tools and the evaluation may call `truth()`.
- **Fingerprint library:** 3 leak sizes × 92 junctions, cached in `data/cache/fingerprints.npz` (about 20 s to build the first time).
- **Scenarios:** 16 scripted cases in `scenarios.py`, each with an expected end state.

## 2. Physics & statistics engine (`neer/engine/`), deterministic with no LLM
### 2.1 Baseline (`baseline.py`): protected memory
- Hourly mean and standard deviation per sensor and per zone, with floors of 0.05 m and 0.5 L/s.
- **Zone excess:** weighted by 1/σ² per hour, so quiet night hours count more. A city-wide swing is removed with `f = median(ex/n)`.
- **Leave-one-out thresholds:** `ex_se` (×1.2) and `p_thr` (×1.25).
- **Safety rules for learning "normal":**
  - Only history days or Auditor-certified leak-free days may be used.
  - At least **2 pending certified days** are needed before any update; a single clean observation never updates.
  - Rolling window of **14 days**.
  - Every update gets a **new version number and timestamp** (`info()`, `versions`).

### 2.2 Evidence dimensions (`detect.py`)
These are dimensions of evidence, not independent witnesses.

| Dimension | Rule |
|---|---|
| Mass balance | zone t = excess / se > **4** |
| Hydraulic response | pressure score > `p_thr` |
| Temporal persistence | anomaly still present in hours 18–23 |

- Operational context is added by the Skeptic, field evidence by the Field Commander, and audit evidence by the Auditor.
- **Alarm** = mass balance OR hydraulic response.
- **Tier:**
  - CONFIRMED if all three dimensions are present
  - PROBABLE if persistence is present
  - WATCH otherwise
- The Sentinel also checks 2- and 3-day windows to catch slow leaks.

### 2.3 Skeptic checks (`skeptic.py`), over a 1–3 day window
1. **Sensor health:** offline, frozen (σ < 0.01 m), or a lone-wolf outlier. Mask the sensor; if the alarm then clears, the verdict is `sensor_fault`.
2. **Replay each logged operation or planned work in the twin** (`twin.event_delta`) and subtract its effect. If the alarm clears or zone t drops below 4, the verdict is `operation` or `planned_work`.
   - *Key insight: a pump or valve change moves pressure, not consumption.*
3. **Temporary event** (single day, persistence false, few anomalous hours): the verdict is `temporary`.
4. Otherwise the verdict is `leak`.

### 2.4 Localisation (`locate.py`)
- **Size-aware fingerprint likelihood:** the leak size from the zone meter is combined with the pressure fit (TEMPER 0.1), plus the zone term.
- Output is a **relative likelihood** over the 92 junctions. It is **not a calibrated probability**; `scripts/engine_report.py` prints a calibration check. The scores are conservative: at 20 L/s the top area is given ~34% but holds the leak ~55% of the time.
- After a repair, localisation uses **post-repair data only**.

### 2.5 Next-best action (`plan.py`)
- For every candidate acoustic survey:
  - information gain = entropy reduction under the acoustic model
  - chance of finding the leak = likelihood × 0.85
  - crew-hours = 1 + 1 per km
- **value = (chance of finding + 0.3 × information gain) / (1 + COST_WEIGHT × crew-hours)**
- **Mode `fast` (default, COST_WEIGHT 0):** find the leak soonest.
- **Mode `cheap` (COST_WEIGHT 0.2):** saves crew-hours.
  - Tested on 90 leaks: about 20% fewer crew-hours, but about 0.4 more nights per leak.
  - Each extra night of a 20 L/s leak wastes about 1,700 m³, so `fast` is the default.
- **Soft elimination:**
  - acoustic "no" ×0.15
  - empty dig ×0.10
  - NOT FIXED at a repair site ×1.0 (the crew did find leak signs there)

### 2.6 Field model (`acoustic.py`)
- 85% sensitivity, 5% false positives, **5% inconclusive** (noise or plastic pipe).
- A field result can be positive, negative or inconclusive.

### 2.7 Auditor (`audit.py`): independent sequential test
- **Independence:** the Auditor never reads the crew's report or the Detective's conclusion.
  - It measures the pre-repair loss itself from the 2 days before the repair and picks the zone.
  - It then tests the post-repair hours.
- **Three hypotheses** for the fraction of the loss remaining: 0, 0.5 and 1. Each hour adds Gaussian log-likelihood, with meter noise inflated ×2.
- **Verdicts:**
  - FIXED needs **999:1** evidence and at least **3 hours** of data.
  - NOT FIXED or PARTLY FIXED needs **99:1**.
  - INCONCLUSIVE after 72 hours, or if too many sensors are unhealthy.

## 3. Tools, safety, MCP (`neer/tools/`, `neer/mcp_servers/`)
### 3.1 The 19 tools (typed with Pydantic)

| Server | Tools |
|---|---|
| scada-mcp (read-only) | `get_zone_flow` · `get_pressure` · `sensor_health` · `get_ops_log` · `get_supply_calendar` |
| twin-mcp | `simulate` · `replay_operation(days)` · `locate_leak` · `estimate_leak_size` · `plan_search_areas` (returns likelihood, info_gain, cost_hours, action_value) |
| field-mcp | `acoustic_check` · `create_work_order(approved_by, approver_role)` · `crew_status` · `notify_residents` · `slow_refill_instruction` |
| audit-mcp | `verify_repair` · `release_contractor` · `case_memory` · `kpi_report` (includes crew-hours and baseline version) |

### 3.2 Resilience
Every call goes through: validation → timeout (10 s) → 2 retries with back-off → a circuit breaker per server (3 failures, then 60 s open) → a `ToolError` instead of an exception → a SQLite trace entry.

### 3.3 Safety validator (`safety.py`)
Every dig or repair order must pass all of these, whatever the agent, LLM or MCP client asked:
- an acoustic "yes" in that area
- a named approver
- a **role in {supervisor, engineer}** (role-based access control)
- no other open excavation on the case

Every approval and refusal is traced. SCADA is read-only: no tool writes to pumps or valves.

### 3.4 Chaos switches
`scada_timeout` · `sensor_dies` · `llm_bad_json` · `crew_finds_nothing`

### 3.5 MCP servers
- Four FastMCP servers over stdio. Each call returns one JSON text.
- All servers share the world file under a file lock.
- If MCP transport fails, the agents fall back to direct in-process calls.

## 4. Agents (`neer/agents/`)
- **CaseState:**
  - fields: status, tier, zone, window, waits, areas, current_area, last_event, visits and re-plans (per round), approvals, verdict, llr_trace
  - **timeline**
  - **evidence ledger:** when, dimension, finding, supports, reliability, source tool

**Two brains.** The engine and tools own physics, numbers, thresholds, safety gates, tool validation and the final
verification. The AI owns interpretation, choosing between hypotheses, deciding what evidence is missing, choosing the
next investigation and where, explaining why, and re-planning. `rules` is the last link of the chain: it answers every
question, so NEER runs with no keys. At every decision the AI answer is logged next to the `rules()` default.

| Agent | Role | LLM decides | Deterministic guard (rules veto) |
|---|---|---|---|
| Sentinel | deterministic data monitor | none | detection rules, slow-leak windows |
| Skeptic (gate) | hypothesis judge | `most_likely` of leak / operation / planned_work / sensor_fault / temporary_demand; `missing_evidence` from replay_operation, sensor_health, get_supply_calendar, get_pressure, wait_one_day; `decision` open_case / dismiss / gather_more | runs the requested tools (max 2 extra rounds, then it must decide; `wait_one_day` only within the wait budget); **may not dismiss** when the engine verdict is `leak` and zone t > mass-balance threshold (veto recorded in timeline + ledger as `AI decision` / `vetoed by rule`); may always choose the cautious option |
| Detective | localisation + interpretation | after `locate_leak`: evidence concentrated or spread, does more data help; `proceed` / `gather_more` | numbers only from `locate_leak` / `estimate_leak_size`; `gather_more` waits one day at most, inside the wait budget |
| Orchestrator | planner | `action` (acoustic_check / request_dig / escalate) **and** `target_area` from the top-3 candidates (+ current area), given likelihood, info gain, crew-hours, value and the areas already surveyed | target must be a candidate; `request_dig` only after an acoustic yes in that very area (the safety validator enforces it too); a confirmed hit is not abandoned; budget of 8 visits / 6 re-plans per round; a choice worth < 50% of the best candidate is accepted but flagged `guard: low-value choice accepted` |
| Skeptic (review) | critic of the plan | approve_plan / send_back | one send-back at most |
| Field Commander | field actions | none | safety validator (acoustic yes, named approver with role, one open dig) |
| Auditor | independent verifier | none | 999:1 to close; contractor released only on FIXED; never reads the crew report |

- **Audit trail:** every AI decision writes a timeline entry and an evidence-ledger row (`dimension = "AI decision"`) with
  provider, choice, rules-default choice, guard outcome (accepted / vetoed / low-value accepted) and the evidence cited.
- **Structured answers:** `GateAnswer`, `PlanAnswer`, `InterpretAnswer`, `Decision` (`neer/agents/llm.py`). An answer that
  fails the schema, the allowed set or the agent's `check` guard is retried once, then the next provider is tried.

- **Human interrupts:** plan approval, and dig approval with role.
- **LLM chain:** Groq → Gemini → Ollama → `rules`.
  - Answers must be structured and inside the allowed set.
  - An invalid or malformed answer falls through to the next provider.
  - **Provider rest:** 2 network failures in a row (timeout, connection, HTTP 429, auth) rest that provider for 60 s (`LLM_DOWN_AFTER`, `LLM_COOLDOWN_S`). Without it, offline Wi-Fi could cost 4 × 20 s per decision. A wrong answer never rests a provider.

## 5. Dashboard (`neer/app/`)
- Three tabs: Control Room, Operations board (Kanban, impact strip, case-report PDF), Twin sandbox (what-if).
- Operations map on a Madurai OpenStreetMap basemap (illustrative placement), falling back to a schematic when tiles cannot load; live agent flowchart and decision cards.
- Map with relative-likelihood heat and search areas.
- Chart of the zone's "water nobody paid for".
- Evidence card and Auditor meter.
- Approvals with **role selector**.
- Tabs: **agent timeline**, **evidence ledger** (with baseline version), **tool trace**.
- Chaos buttons and KPIs, including crew-hours.

## 5b. Case database and REST API
- **`neer/store.py`**, SQLite file `data/neer.db` (WAL; env `NEER_CASE_DB`). Tables: `cases` (one row per case, updated after every step), `timeline`, `ledger`, `approvals` (gate, approved, name, role), `work_orders` (PK case_id + work_order_id). Written by the graph wrapper `_recorded` in `graph.py` and by the field tools (also inside the field-mcp process). A database error is logged and never stops a case. The SQL box uses a read-only connection (`mode=ro`) and accepts one SELECT only.
- **`neer/api/server.py`** (FastAPI): `GET /api/health`, `/api/scenarios`, `/api/tools`, `POST /api/cases` (runs a case with the given approver and role; the safety validator still applies), `GET /api/cases`, `/api/cases/{id}`, `/api/kpi`, `/api/trace`. Pydantic request models (bad input → 422), 404 for unknown ids, one case at a time (lock), CORS enabled. OpenAPI docs at `/docs`.

## 6. Evaluation (`neer/eval/`)
- **`run_eval.py`:** 16 scenarios × seeds → `docs/EVAL.md`. Reports:
  - pass rate and wrong closures
  - safety violations and invalid tool calls
  - time to verified repair and crew-hours
  - ledger size
  - how failures ended (escalated or watch)
- **`ablation.py`:** five systems on the same cases → `docs/ABLATION.md`:
  - threshold alarm
  - leak model only
  - leak model + Skeptic
  - leak model + Orchestrator
  - full NEER
- **`llm_eval.py`:** the same scenarios with `rules` and with the live chain → `docs/LLM_EVAL.md` (agreement with `rules()`, fallbacks, vetoes).
- **Isolation:** every evaluation calls `config.use_private_runtime()` and uses `data/runs/<name>/` for chaos, world and trace, so it cannot leak chaos toggles into (or count tool calls from) a running dashboard.
- **`scripts/engine_report.py`:** engine accuracy, including a calibration check → `docs/ENGINE_REPORT.txt`.
- **`scripts/search_bench.py`:** the larger search run (120 leaks per size) that the pitch quotes, because 40-case rows swing by about ±7%.

## 7. What NEER does not claim
- It is not the first agentic water system.
- It does not claim that all non-revenue water is physical leakage.
- It has no real-world accuracy yet (Net3 simulation only).
- It has no live Madurai SCADA integration.
- Area likelihoods are not calibrated probabilities.
- The LLM never invents measurements or controls infrastructure.
