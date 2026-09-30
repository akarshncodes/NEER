# NEER technical specification (the contract)

The algorithms below were tested earlier today in `reference/`. Read those files for a working version, then re-implement cleanly with this structure, the Pydantic contracts and tests. Parameters in **bold** are the tested values; keep them unless a test shows a better one.

---

## 1. Stage 1: the simulated city (`neer/sim/`)

### 1.1 Network
- EPA **Net3**, loaded from the WNTR library: `os.path.join(os.path.dirname(wntr.__file__), "library", "networks", "Net3.inp")`
- Hydraulics: **EpanetSimulator**, 1-hour steps, one simulated day = 24 hourly values (`duration = 23*3600`).
- Junction list `J = wn.junction_name_list` (92 junctions).

### 1.2 Zones (DMAs) and meters (`zones.py`)
- Undirected networkx graph of the network. Zones come from `greedy_modularity_communities(G, cutoff=5, best_n=5)`, which gives 5 zones named `Z1..Z5`. Sort communities by their smallest junction name so the labels are stable.
- Tanks and reservoirs belong to zone `-1` (outside every zone).
- **Flow meters** = every link whose two end nodes are in different zones (expected: 15 links).
- Zone inflow = signed sum of meter flows: +flow if the link ends inside the zone, −flow if it starts inside it. Store this as a matrix `MZ` of shape (5 × meters).
- **Bulk-metered customers** (big users with their own meters): junctions `["203","35","123","15"]`. Their measured demand is subtracted from zone inflow before analysis.
- **Pressure sensors (20, chosen for leak discrimination):** `["101","211","208","40","139","117","197","15","241","10","265","103","149","229","143","217","167","219","35","207"]`
- **Search area** of a junction = that junction plus its junction neighbours within 1 hop. The area id is `A-<junction>`. Area pipe length = the sum of lengths of pipes with both ends inside the area.

### 1.3 Leaks
- A leak is an orifice modelled with an EPANET emitter: `emitter_coefficient = 0.75 * A * sqrt(2*9.81)`.
- Leak size in L/s is converted to area with `A = q/1000 / (0.75*sqrt(2*9.81)*sqrt(40))`.

### 1.4 Realistic noise (class `SimCity(seed)`)
Each city has hidden "truth" that NEER must not see:
| Noise | Value |
|---|---|
| Per-junction demand bias (fixed for the whole city) | **N(1, 0.10)** |
| Per-junction day-to-day variation | **N(1, 0.03)** |
| Hourly city-wide demand factor, applied to the demand pattern multipliers | **N(1, 0.03)** |
| Pressure sensor noise | **N(0, 0.1 m)** |
| Flow meter bias (fixed per meter) | **N(1, 0.02)** |
| Flow meter reading noise | **N(1, 0.01)** |
| Bulk meter reading noise | **N(1, 0.01)** |

### 1.5 Events (`events.py`, Pydantic models)
| Event | Parameters | Logged in SCADA ops log? |
|---|---|---|
| `Leak` | node, lps | no (hidden truth) |
| `PumpTrip` | pump=`"10"`, start_h, end_h | yes |
| `ValveClosure` | pipe, taken from the safe list below | yes |
| `FireDraw` | node, lps, h0, h1 | no |
| `PlannedCut` | zone, h0, h1 | yes, in the supply calendar |
| `StuckSensor` | sensor, from_h | no |
| `SensorOffset` | sensor, metres | no |

- Pump trip: add time controls (pump 10 CLOSED at start_h, OPEN at end_h).
- Safe valve pipes (closing one does not disconnect the network): `["107","113","115","145","147","153","163","171","186","202","223","245","269","289","305","307","311"]`.
- Planned cut: model it by closing that zone's meter links for h0..h1.

### 1.6 City clock
`SimCity` API:
- `SimCity(seed)` generates **7 normal history days** on creation.
- `add_event(e)` and `remove_leak(node)`.
- `advance_day()` returns a `DayData` object:
  - pressure, 24 × 20 sensors
  - `zone_inflow_net`, 24 × 5 (inflow minus bulk)
  - `ops_log` entries
  - `calendar` entries
- `history`: the list of past `DayData`.
- The **hidden truth** (`truth()`, current leaks) is used only by field tools and the eval.

### 1.7 Fingerprint library (`library.py`)
- For each junction and each area size **(0.0004, 0.0012, 0.003 m²)**, the fingerprint is the base pressure minus the pressure with a leak at that junction: an array of shape (3 × 92 × 24 × 92).
- `QREF[s, j] = 1000*C(A_s)*sqrt(max(mean base pressure at j, 1))` in L/s.
- Cache the result to `data/cache/fingerprints.npz`. It takes about 15 s to build.

**Stage 1 tests:**
- 5 zones and 15 meters
- a 20 L/s leak raises its zone's net inflow by 15–25 L/s and other zones by less than 3 L/s
- the same seed gives the same output
- the cache round-trips

---

## 2. Stage 2: the physics engine (`neer/engine/`)
These are pure functions and classes with no LLM. Each returns Pydantic models from `schemas.py`.

### 2.1 Baseline (`baseline.py`)
- Built from the history days. For pressure, compute the mean and standard deviation per (hour, sensor), with the std floored at **0.05 m**. For zone inflow, compute the mean and std per (hour, zone), floored at **0.5 L/s**.
- **Zone excess** for a set of days is a weighted mean over hours of (observed − normal), with weights 1/zs².
  - Common-mode removal: `f = median(ex/n)` and `ex -= f*n`, where n is the zone's normal mean flow (floored at 1).
- `ex_se` is the leave-one-out spread of daily excess over the history × **1.2**, floored at 0.3.
- `p_thr` is the maximum leave-one-out pressure score × **1.25**, where pressure score = RMS of (residual / ps).
- `z_thr` = **4.0**.
- **The normal pattern learns only from days marked `certified_clean`** (by the Auditor, or history days).

### 2.2 Detection: three witnesses (`detect.py`)
The three witnesses:
- **water**: max zone t = ex/ex_se > 4
- **pressure**: score > p_thr
- **persistence**: the anomaly is still present in hours 18–23 (zone t over those hours with se ×2 > 2.5, or a late pressure z-RMS > 2.5)

Alarm = water OR pressure. The tier is:
- **CONFIRMED** if all three witnesses are present
- **PROBABLE** if (water or pressure) and persistence
- **WATCH** otherwise

### 2.3 Skeptic checks (`skeptic.py`)
Run these in order and return a `SkepticVerdict` with a verdict and a plain reason.
1. **Sensor health**
   - Frozen: std over hours 6–23 < 0.01.
   - Lone wolf: the highest per-sensor mean |z| is > 4 while the second highest is < 2 and zone t < 3.
   - Mask faulty sensors (replace them with normal). If the alarm clears, the verdict is `sensor_fault`.
2. **Operations replay:** for each logged op or calendar event, compute the twin delta (twin with the event − twin without it) for pressure and zone flow, and subtract it. If the alarm clears **or** zone t < z_thr, the verdict is `operation`.
   - Key insight: a pump or valve change moves pressure, not consumption.
3. **Temporary:** anomalous hours ≤ 4 with none in the last 6, **or** (late zone t < 2.5 and no late pressure anomaly). The verdict is `temporary`.
4. Otherwise the verdict is `leak`.

Tested target: pump trip, valve closure, stuck sensor and sensor offset are judged correctly ≥ 90%, fire-fighting ≥ 80%, and real leaks are kept ≥ 85%.

### 2.4 Localisation (`locate.py`)
- Weighted residual `a = ((normal − observed)/ps).ravel()` over the observed days.
- For each size s:
  - `F = (FP[s][:,:,sensors]/ps).reshape(92,-1)`
  - `kfree = clip((F@a)/sum(F²),0)`
  - `k = sqrt((q_zone/QREF[s]) * kfree)`, where `q_zone` is the zone excess of each junction's zone, clipped at a minimum of 0.5
  - `err = sum((a − k F)²)`
- `loglik = max over s of (−0.5*err/24) * temper`, where **temper = 0.1**.
- Add the zone term `0.5*max(t_zone,0)²`, then add optional log-priors (pipe age, complaints; default uniform).
- The posterior is a softmax.
- Returns: the zone, the top areas, and the leak size estimate (the best zone's excess, in L/s).
- Tested: correct zone 92–100%; found within 3 visits 79% (5–40 L/s leaks, 3 days of data).

### 2.5 Search planning (`plan.py`)
- `plan_search_areas(posterior, weights)`: repeatedly pick the area (junction + 1-hop neighbours) with the largest remaining weighted probability mass. Return an ordered list of `SearchArea(id, junctions, probability, pipe_km)`.
- Soft elimination:
  - after an acoustic "no", multiply that area's junction weights by **0.15**
  - after a dig finds nothing, multiply by 0.1

### 2.6 Acoustic check simulation (`acoustic.py`)
- Sensitivity **0.85**, false-positive rate **0.05**, seeded.
- Tested: **0.07 wasted digs per leak**, against 4.6 when digging wherever the model points.

### 2.7 Auditor: sequential test (`audit.py`)
- Hour-by-hour after the repair:
  - `e = inflow_h − normal_h`
  - `s = zs_h * 2.0`
  - `q = max(pre-repair zone excess, 1)`
  - `llr += (e*q − q²/2)/s²`
- If `llr > ln(99)`, the verdict is NOT FIXED; if `llr < −ln(99)`, it is FIXED. Cap at **72 h**; if still undecided, INCONCLUSIVE.
- On NOT FIXED, if the post-repair daily excess dropped by more than 35% of the pre-repair excess, the verdict is **PARTLY FIXED**.
- If a zone meter or ≥ 30% of the sensors are unhealthy during the window, the verdict is **INCONCLUSIVE**.
- Tested: median decision time 1 h (40 L/s), 2 h (20), 4.5 h (10), 8 h (5); ≤ 2% wrong verdicts.

**Stage 2 tests:** small statistical tests with 10–20 seeded cases each, at loose thresholds (e.g. zone accuracy ≥ 85% for 20 L/s, pump-trip dismissal ≥ 80%, auditor correct ≥ 85%), plus unit tests on the maths.

---

## 3. Stage 3: tools, resilience, MCP servers (`neer/tools/`, `neer/mcp_servers/`)

### 3.1 The 19 tools
Each tool is a plain Python function with Pydantic input and output, living in `neer/tools/*`. The MCP servers only wrap them.

| Server | Tool | Input | Output |
|---|---|---|---|
| scada-mcp | `get_zone_flow` | zone: str\|None, days:int=1 | per zone: hourly net inflow, normal, excess L/s, t-score |
| | `get_pressure` | sensors: list\|None, days:int=1 | per sensor: residual series, z-RMS |
| | `sensor_health` | – | per sensor: ok / frozen / outlier / offline, with a reason |
| | `get_ops_log` | since_hours:int=24 | list of ops events (pump, valve) |
| | `get_supply_calendar` | – | planned cuts |
| twin-mcp | `simulate` | events: list[Event] | pressure and zone-flow deltas summary |
| | `replay_operation` | op_id | explained: bool, zone t before/after, reason |
| | `locate_leak` | days:int=3, priors: dict\|None | zone, leak_size_lps, top areas with probability, evidence list |
| | `estimate_leak_size` | zone | lps, ± |
| | `plan_search_areas` | case_id | ordered areas (with current soft-elimination weights) |
| field-mcp | `acoustic_check` | case_id, area_id | result yes/no, confidence 0.85 |
| | `create_work_order` | case_id, area_id, action (acoustic\|dig\|repair) | work_order_id (**idempotent**: same key gives the same id) |
| | `crew_status` | work_order_id | status, result (found_leak / nothing_found / repaired) |
| | `notify_residents` | area_id, message, lang (ta\|en) | homes notified (simulated) |
| | `slow_refill_instruction` | work_order_id | acknowledged |
| audit-mcp | `verify_repair` | case_id | verdict, hours_used, llr trace, reason |
| | `release_contractor` | work_order_id | released \| held; **refuses unless the verdict is FIXED** |
| | `case_memory` | op read\|write, key, value | stored value (SQLite) |
| | `kpi_report` | – | cases, false alarms avoided, digs, wasted digs, litres saved |

### 3.2 Resilience (`resilience.py`), wrapping every tool
- Pydantic validation of inputs and outputs. An invalid input returns a structured `ToolError(code="invalid_input", message, hint)` so the agent can correct itself.
- Timeout (default 10 s); retry 2 times with exponential back-off (0.5 s, 1 s).
- A **circuit breaker** per server: after 3 failures it opens for 60 s and returns `ToolError(code="degraded")`.
- Every call is logged to the trace table: timestamp, agent, tool, args, result summary, ms, ok/error.

### 3.3 Chaos toggles (`chaos.py`)
A shared registry, file-backed at `data/chaos.json` so the dashboard can flip toggles:
- `scada_timeout`: the next 2 SCADA calls raise TimeoutError
- `sensor_dies`: one sensor returns NaN, and health reports it offline
- `llm_bad_json`: the next LLM reply is malformed
- `crew_finds_nothing`: the next acoustic check returns "no" even inside the leak area

### 3.4 MCP servers
- Four FastMCP servers (`scada_server.py` etc.), stdio transport.
- The shared city state lives in a singleton `World` (city + case store), loaded from `data/world.pkl` / SQLite so all servers see the same city.
- Also provide `NEER_TOOL_MODE=direct`, in which agents call the Python functions in-process. This is a fallback if MCP transport fails, and it is used by the tests.

**Stage 3 tests:**
- every tool is happy-path tested
- invalid input returns a ToolError
- the retry and circuit breaker work
- chaos toggles have their effect
- the MCP servers list the 19 tools (use the `mcp` client in a test)

---

## 4. Stage 4: agents (`neer/agents/`)

### 4.1 Case state (`state.py`, Pydantic, shared by all agents)
Fields:
- `case_id`, `tier`, `zone`
- `evidence[]`: {source, text, numbers}
- `skeptic_verdict`
- `hypotheses{area_id: prob}`, `leak_size_lps`
- `plan[]`: {step, action, area_id, reason}
- `actions_log[]`, `approvals[]`
- `work_orders[]`
- `visits`, `replans`
- `verdict`, `status` (open / watch / closed / escalated)
- `messages[]`: agent narrations

### 4.2 LLM router (`llm.py`)
- Chain from the environment variable `NEER_LLM_CHAIN`, default `groq:llama-3.3-70b-versatile,gemini:gemini-2.0-flash,ollama:qwen2.5:7b,rules`. Model names are configurable; skip providers without keys.
- Each call:
  - structured output (Pydantic)
  - timeout 20 s
  - retry once, then the next provider
  - `rules` = the deterministic policy, which **always works**
- Log provider, latency and tokens to the trace.

### 4.3 Agents (nodes)
Every node:
1. calls tools (never inventing numbers)
2. asks the LLM for a decision from an **allowed set**, with a reason
3. validates the answer
4. writes a narration into the state

| Agent | Tools | LLM decides (allowed set) | Deterministic guard |
|---|---|---|---|
| Sentinel | get_zone_flow, get_pressure, sensor_health | – (summarise only) | detection rule gives the tier |
| Skeptic (critic) | get_ops_log, get_supply_calendar, replay_operation, sensor_health | at the gate: dismiss / open_case; at plan review: approve_plan / send_back(reason) | engine verdict must support "dismiss" |
| Orchestrator | plan_search_areas, case_memory | next action ∈ {acoustic_check, request_dig, next_area, wait_more_data, escalate} | budget guard: ≤ 3 re-plans or ≤ 6 visits, then escalate |
| Detective | locate_leak, estimate_leak_size | – (explains the map) | probabilities come from the tool only |
| Field Commander | acoustic_check, create_work_order, crew_status, notify_residents, slow_refill_instruction | drafts SMS and work-order text (Tamil and English) | no dig without an acoustic yes **and** human approval |
| Auditor | verify_repair, release_contractor, kpi_report, case_memory | – (explains the verdict) | never reads crew notes; release only if FIXED |

### 4.4 Graph (`graph.py`)
```
START → sentinel ─(no alarm)→ END
               └→ skeptic_gate ─(dismiss)→ watch → END
                              └→ detective → orchestrator → skeptic_review ─(send_back)→ detective
                                                            └→ approve_plan [interrupt] → field_commander
field_commander ─(acoustic no)→ orchestrator (re-plan)
                ─(acoustic yes)→ approve_dig [interrupt] → repair (world update) → auditor
auditor ─FIXED→ close (release contractor, certify clean day) → END
        ─PARTLY→ detective (hunt second leak)
        ─NOT FIXED→ orchestrator (hold contractor, re-plan)
        ─INCONCLUSIVE→ wait (advance a day) → auditor
orchestrator ─(budget exceeded)→ escalate → END
```
- Human interrupts use LangGraph `interrupt()`; the CLI auto-approves with `--auto-approve`.
- Checkpointer: SqliteSaver (`data/cases.db`).
- `runner.py`: `--scenario <name> --seed --auto-approve --llm rules|chain` prints a coloured timeline.

**Stage 4 tests:**
- with `--llm rules`:
  - leak_20 ends FIXED
  - pump_trip ends in watch
  - wrong-area repair gives NOT FIXED, then a re-plan, then FIXED
  - two_leaks gives PARTLY FIXED, then FIXED
- with chaos on: all of the above still end correctly

---

## 5. Stage 5: dashboard (`neer/app/`)
Streamlit "NEER Control Room" with wide layout, light theme, and colours matching our diagrams (agents blue, critic red, human yellow, auditor green).
- **Left:** a Plotly network map showing zones in colour, sensors (triangles), meters (squares), the probability heat on junctions, search areas as circles, and the true leak only in "reveal" mode.
- **Centre:** a zone water-bill chart (inflow vs normal band) and the Auditor confidence meter (llr toward ±ln 99).
- **Right:** the case card (evidence card format below), **Approve / Reject** buttons for interrupts, and an agent trace timeline (agent · tool · result · ms · provider).
- **Sidebar:** a scenario launcher (leak_20, pump_trip, two_leaks, wrong_repair, stuck_sensor), step / auto-run, **chaos toggles**, LLM chain status, and a KPI strip.
- Evidence card format:
  ```
  Case Z2-#0042 · PROBABLE · 02:14
  Zone Z2 inflow +20.4 L/s vs normal night
  Pressure −0.4 m at S7, −0.3 m at S9 (S12 masked: frozen)
  Ops: no pump/valve event; no planned cut
  Areas: A-239 41% · A-247 33% · A-251 26%
  Next: acoustic logger in A-239 tonight · Approval needed
  ```

## 6. Stage 6: evaluation and polish (`neer/eval/`)
- `scenarios.yaml`: 20 scripted scenarios with expected end states:
  - 6 real leaks (10–40 L/s, different zones)
  - 5 look-alikes (pump trip, valve, fire draw, stuck sensor, offset)
  - 2 two-leak cases
  - 2 wrong-first-repair cases
  - 4 real leaks with each chaos toggle
  - 1 quiet day
- `run_eval.py` runs every scenario with `rules` and with the LLM chain. It writes `docs/EVAL.md`: a pass/fail table, tool calls, latency, tokens, and the total "passed N/20".
- README with setup, run commands, architecture image and the honest limits. Record a demo backup video.
