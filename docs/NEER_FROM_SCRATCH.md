# NEER from scratch: the complete explanation

*Written so you can explain every part of NEER as if you built it yourself: to a judge, to an engineer, or to a 10-year-old.*

**How to read this.** Part 1 is the simple story. Parts 2–9 go deeper, one layer at a time. Part 10 is a glossary with **every technical word in plain English**. Part 11 is practice questions.

When you explain NEER, always start with Part 1, then go down only as deep as the listener wants.

---

## PART 1: The story for a 10-year-old

**The problem.**
- A city sends clean water to every house through pipes buried under the road.
- Sometimes a pipe cracks underground. Water escapes into the soil, and nobody can see it.
- In Indian cities, about **38 out of every 100 buckets** of treated water never reach a bill. That water is lost to leaks, theft and billing mistakes.
- A leaking pipe also sucks dirty water in when the pressure is low, and people can fall sick.

**Why it is hard.**
- You can't see under the road.
- The city has thousands of pipes.
- Digging up a road costs money and blocks traffic.
- Even after a worker says "I fixed it", nobody checks. The leak can keep running for weeks.

**What NEER does.** NEER (நீர் means "water" in Tamil) is a team of six computer helpers called **agents**. They work like a team of detectives:

| Helper | Job | Like a... |
|---|---|---|
| **Sentinel** | Watches the water meters all day and night, and shouts "Something is wrong in zone 5!" | security guard |
| **Skeptic** | Asks "Are you sure? Maybe a pump was switched off, or a sensor is broken?" It tries to prove the alarm wrong | doubting friend |
| **Detective** | Works out *where* in the zone the leak most likely is, and how big it is | detective with a magnifying glass |
| **Orchestrator** | Makes the plan: "Listen in area A tonight. If it's quiet, try area B" | team captain |
| **Field Commander** | Sends the crew with a listening device (it hears the hiss of a leak) and orders the dig only if the leak is heard **and** a boss says yes | foreman |
| **Auditor** | After the repair, checks the meters hour by hour. The case closes only when the numbers prove the leak is gone | strict teacher checking homework |

The loop they follow has six steps:

**SUSPECT → QUESTION → INVESTIGATE → ACT → VERIFY → REPLAN**

If a step fails (the area was quiet, or the repair didn't work), they **make a new plan** by themselves. That is what makes them "agents" and not just a calculator.

**Why nobody gets hurt.** A human always approves any digging. The computer can never dig on its own, and a rule inside the tools blocks it.

**How we know it works.** We built a pretend city inside the computer: a real test network from the US Environmental Protection Agency (EPA), called Net3. We hid leaks in it and let NEER hunt them.
- It passed 79 out of 80 tests.
- It never closed a case while the leak was still running.
- It never dug without permission.

---

## PART 2: The real problem, with facts you can quote

- **Non-revenue water (NRW)** is water that is treated and pumped but never billed.
  - Indian cities lose about **38%** (source: ORF). The good global level is 15–20%.
  - Delhi's audit (CAG) found **51–53%**, worth about ₹4,988 crore.
  - NRW = leaks (physical loss) + theft + billing errors. **NEER targets the leak part only.** Say this honestly.
- **Health.** A study in Hubli-Dharwad found **42% less typhoid** where water was supplied continuously under pressure. Low-pressure leaky pipes let dirty water in.
- **Government plan.** **AMRUT 2.0** asks cities to get losses **below 20%**, using **DMAs** (zones with meters) and **SCADA** (remote monitoring). Madurai is building **20 DMAs** under the Mullaiperiyar water scheme. NEER is software that uses exactly this kind of data.
- **Problem statement SC-02 says:** leaks run for weeks because (1) the pressure change is noticed late, (2) the location is unclear, and (3) a repair that didn't work goes unnoticed. **NEER handles all three.**

**What exists already, and the gap:**

| Existing | Where it stops |
|---|---|
| SCADA threshold alarms | too many false alarms; can't say where the leak is |
| Commercial analytics (TaKaDu, Xylem Vue) | flag anomalies, but humans chase every step |
| Research models (BattLeDIM competition) | a prediction only; no action, no follow-up |
| LLM + EPANET chat tools | run simulations when you ask; they don't detect, dispatch or verify |

**NEER closes the loop:** detect → question → locate → act with a human → verify independently → re-plan.

We never claim to be "the first agentic water system".

---

## PART 3: How we built it, step by step

We built it in **stages**. After each stage the tests had to pass, and we saved the work in git (a *commit*).

| Stage | What we built | Why |
|---|---|---|
| 0 Foundation | project set-up with `uv`; folder layout; `config.py` (all numbers in one place); `schemas.py` (data shapes); logging; tests | a clean base, so 4 people can work without breaking each other |
| 1 Simulated city | EPA Net3 network in WNTR; 5 zones; 15 meters; 20 pressure sensors; noise; events (leak, pump trip, ...); 16 scenarios; fingerprint library | we have no real city data, so we built a realistic pretend city |
| 2 Physics engine | baseline ("normal"), detection, Skeptic checks, localisation, search planning, acoustic model, Auditor test | the maths lives in tested code, not in the AI |
| 3 Tools + MCP | 19 tools; resilience layer; chaos switches; 4 MCP servers | agents act only through typed, safe tools |
| 4 Agents | 6 LangGraph agents; human approval pauses; LLM chain with rules fallback; command-line runner | the "agentic" brain |
| 5 Dashboard | Streamlit Control Room | people can see and control it |
| 6 Evaluation | 16 scenarios × seeds; engine benchmark; README | proof with numbers |
| 7 V2 upgrades | evidence ledger; next-best-action value; inconclusive results; independent Auditor; protected baseline; safety validator with roles; ablation study; honest claims | ideas from the V2 guide |
| 8 AI owns the investigation | live Groq/Gemini chain; hypothesis judge; AI picks where to search; rule veto; decision log | a real AI decides, and rules keep it safe |
| 9 Pro Control Room | Madurai operations map; live flowchart; decision cards; operations board; case PDF; twin sandbox; theme | the judges said the map was bad |
| 10 Database + API | SQLite case database; FastAPI REST API; Database & API tab | judges check UI ↔ backend, API and database |
| 11 Wow layer | animated hero; mission stepper; FIXED banner with counters; toasts; 3D pressure landscape | presentation |
| 12 3D city | 3D city view, Blueprint 3D, quick-start demos, how-to guide | easier to use and more impressive |

**Tests now: 84 test runs, all passing.**

**Challenges we solved** (say these; judges love them):
1. Our first accuracy test used unrealistically huge leaks. We re-tested with 5–40 L/s leaks, got only 24%, and redesigned: zone meters, night weighting and size-aware fingerprints.
2. Running many simulations at once crashed, because they shared temporary files. Each run now gets unique file names.
3. MCP messages got corrupted by log lines. Logs now go to a separate channel (stderr).
4. After a wrong repair, the agents searched everywhere else. Now they **re-listen at the repair site first**.
5. After a partial fix, old data confused the Detective. It now uses post-repair data only.
6. Small signals caused false alarms. Now NEER **waits one more day** when the leak looks smaller than 6 L/s.
7. Closing a case wrongly is the worst mistake. FIXED now needs **999 to 1** evidence and at least 3 hours.
8. The Auditor was using the Detective's numbers, so it wasn't independent. Now it **measures the loss itself**.
9. The AI once said "dismiss" on real leaks. A **rule veto** overrides it.
10. Free AI quotas ran out (HTTP 429 errors). The chain falls back cleanly, and a failing provider **rests for 60 s**.
11. An evaluation running next to the dashboard shared its files. Each evaluation now uses private files.

---

## PART 4: The pretend city (`neer/sim/`)

- **EPA Net3.** A real benchmark water network published by the US Environmental Protection Agency.
  - It has **92 junctions** (points where pipes meet or water is used), about 66 km of pipe, 2 water sources (a river and a lake), 3 tanks and pumps.
  - We use it because it is public, realistic and trusted by researchers.
- **WNTR / EPANET.** EPANET is the EPA's program that calculates how water flows and what the pressure is everywhere, hour by hour. WNTR is its Python wrapper.
  - `hydraulics.py` is the **only** file that calls it.
  - One simulated day = 24 hourly values.
- **Zones (DMAs).** We split the city into **5 zones (Z1–Z5)** using *modularity clustering*: a maths method that cuts a network into groups with many connections inside and few between.
  - Every pipe that crosses a zone border has a **flow meter**. That gives **15 meters**.
  - Zone inflow = water in − water out. It's like a water bill for each zone.
- **Bulk customers.** 4 big users (junctions 203, 35, 123, 15) have their own meters, so we subtract their use. That makes the zone bill cleaner.
- **Pressure sensors.** 20 sensors, placed where they best tell leaks apart.
- **Search area.** A junction plus its direct neighbours, about 1 km of pipe, with an id like `A-241`.
- **The leak model.** A leak is an **emitter**, a hole whose flow grows with the square root of pressure:
  - C = 0.75 × hole area × √(2g)
  - sized so a "20 L/s leak" really leaks about 20 L/s at 40 m of pressure
- **Hidden noise** (NEER never sees it), which makes the pretend city realistic:
  - each house uses ±10% differently from the model
  - use varies ±3% day to day and ±3% hour to hour
  - pressure sensors are ±0.1 m off
  - meters have a fixed 2% bias plus 1% reading noise
- **Events:**
  - Leak: hidden
  - PumpTrip and ValveClosure: written in the operations log
  - PlannedWork (flushing, tanker filling): in the calendar
  - FireDraw: not logged
  - StuckSensor and SensorOffset: broken readings
- **SimCity(seed).** It starts with 7 clean "history" days. `advance_day()` returns a `DayData` with:
  - pressure: 24 hours × 20 sensors
  - zone inflow: 24 × 5
  - the ops log and the calendar
  - `truth()` holds the real hidden leaks. **Only the field tools and the evaluation may read it**, the same way only a real crew digging finds the truth.
- **Seed.** A number that fixes the "random" choices. Same seed means the same city and the same result, so demos repeat exactly.
- **Fingerprint library.** We simulate a leak at each of the 92 junctions, in 3 sizes, and store how every sensor's pressure changes. Later we compare real readings to these "fingerprints", like matching fingerprints at a crime scene. It is cached in `data/cache/fingerprints.npz` and takes about 20 s to build once.
- **16 scenarios:**
  - quiet
  - leak_20, leak_10, leak_40
  - pump_trip, valve_closure, planned_work, fire_draw
  - stuck_sensor, sensor_offset
  - two_leaks, wrong_repair
  - four chaos cases
  Each has an expected ending, so the evaluation can score it.
- **Demo dataset.** `scripts/build_dataset.py` writes `dataset/`: CSV files you can open in Excel (network, 37-day live city, 16 scenarios).

---

## PART 5: The physics and statistics engine (`neer/engine/`)

There is no AI in this part: only tested maths. Rule number 1 is that **numbers only come from here, never from the AI.**

### 5.1 Baseline, "what is normal" (`baseline.py`)
- For every hour and every sensor or zone, it stores the average (**mean**) and how much it normally wobbles (the **standard deviation**, σ).
- **Excess** = observed − normal. Night hours count more, because at night people sleep, so extra water is suspicious. Technically each hour gets weight 1/σ².
- **City-wide swings are removed.** A hot day raises every zone, so a common factor is subtracted.
- **t-score** = excess ÷ its usual spread. t = 4 means "4 times bigger than normal wobble": very unlikely by chance.
- **Protected memory.** NEER re-learns "normal" only from days the Auditor **certified as leak-free**:
  - at least **2** such days before any update
  - a rolling 14-day window
  - each update is a new **version**
  This stops a slow leak from slowly becoming "the new normal".

### 5.2 Detection: three evidence dimensions (`detect.py`)
| Dimension | Simple meaning | Rule |
|---|---|---|
| **Mass balance** | the zone's water bill is too high | zone t > 4 |
| **Hydraulic response** | pressure dips in a leak-like pattern | pressure score > threshold |
| **Temporal persistence** | still there late at night | hours 18–23 still abnormal |

- **Alarm** = mass balance OR hydraulic response.
- **Tier:**
  - **CONFIRMED** if all three dimensions are present
  - **PROBABLE** if persistence is present
  - **WATCH** otherwise
- **Slow leaks:** the Sentinel also looks at 2- and 3-day windows. A small leak hides in one day of noise but adds up over several days.

### 5.3 Skeptic checks (`skeptic.py`)
1. **Sensor health.**
   - A sensor is *frozen* if its value doesn't move.
   - It is *offline* if it gives no data.
   - It is a *lone wolf* if it disagrees with all its neighbours.
   Bad sensors are hidden (**masked**). If the alarm disappears, the verdict is `sensor_fault`.
2. **Replay operations in the digital twin.** If the log says "pump 10 off 08–13 h", we simulate exactly that and subtract its effect.
   - If the alarm disappears, the verdict is `operation` (or `planned_work`).
   - **Key insight: a pump or valve changes pressure but not how much water people use. A leak changes both.**
3. **Temporary.** If the alarm is short and gone by the evening (e.g. fire-fighting), the verdict is `temporary`.
4. Otherwise the verdict is **`leak`**.

### 5.4 Digital twin (`twin.py`)
- A **digital twin** is a computer copy of the real network. We ask it "what if pump 10 stops?" or "what if there's a leak at 239?" and it answers with physics.

### 5.5 Localisation (`locate.py`)
- The zone meter says **how big** the leak is (e.g. 20 L/s).
- The pressure pattern is compared with every fingerprint of that size. A better match means a higher score, plus a bonus if the junction is in the alarmed zone.
- The result is a **relative likelihood** for all 92 junctions (e.g. A-211 25%, A-241 22%, A-251 16%).
  - It is **not a calibrated probability**, and we say that honestly.
  - Our check showed the numbers are **conservative**: at 20 L/s the top area gets 34% but really holds the leak 55% of the time.
- After a repair, it uses **only post-repair data**.

### 5.6 Planning the next best action (`plan.py`)
- For each possible listening survey:
  - **chance of finding** = likelihood in the area × 0.85 (the device's hit rate)
  - **information gain** = how much our uncertainty shrinks after listening. It's measured with **entropy**, a number for "how spread out our guesses are".
  - **crew-hours** = 1 + 1 per km of pipe
- **Value** = (chance of finding + 0.3 × information gain) ÷ (1 + cost weight × crew-hours)
- **Fast mode** (default) ignores cost. **Cheap mode** saves about 20% of crew-hours but costs about 0.4 extra nights per leak. We tested both, and chose fast, because a 20 L/s leak wastes about 1,700 m³ every day.
- **Soft elimination.** A quiet area is not set to 0%, because devices sometimes miss:
  - acoustic "no": its weight × 0.15
  - empty dig: × 0.10

### 5.7 Listening device model (`acoustic.py`)
- **Acoustic logger:** a microphone put on a pipe overnight. It hears the hiss of escaping water.
- Our model:
  - it hears a real leak **85%** of the time (sensitivity)
  - it gives a false "yes" **5%** of the time
  - **5%** of surveys are "inconclusive" (too noisy), and those are repeated
- **No acoustic "yes" means no dig.**

### 5.8 The Auditor's proof (`audit.py`)
- **Independent.** It never reads the crew's report or the Detective's answer.
  - It measures the loss itself from the 2 days before the repair (e.g. 20.0 L/s in Z5).
  - Then it watches the meter **hour by hour** after the repair.
- **Three possibilities:** 0%, 50% or 100% of the leak is still there. Each hour of data adds evidence (a **log-likelihood ratio**) for one of them.
- **Sequential test (SPRT, Wald 1945):** stop as soon as the evidence is strong enough.

  | Verdict | Needs |
  |---|---|
  | **FIXED** | **999 to 1** evidence and at least 3 hours |
  | **NOT FIXED** / **PARTLY FIXED** | 99 to 1 |
  | **INCONCLUSIVE** | after 72 hours, or if sensors are broken |

- Only FIXED releases the contractor's payment. NOT FIXED holds it and triggers a re-plan.
- The noise is doubled on purpose (×2) to be safe.

---

## PART 6: Tools, MCP, safety (`neer/tools/`, `neer/mcp_servers/`)

- A **tool** is one action an agent can take, like a button with typed inputs and outputs.

| Server | Tools |
|---|---|
| **scada-mcp** (read-only) | get_zone_flow · get_pressure · sensor_health · get_ops_log · get_supply_calendar |
| **twin-mcp** | simulate · replay_operation · locate_leak · estimate_leak_size · plan_search_areas |
| **field-mcp** | acoustic_check · create_work_order · crew_status · notify_residents (Tamil and English SMS) · slow_refill_instruction |
| **audit-mcp** | verify_repair · release_contractor · case_memory · kpi_report |

- **Pydantic.** Every input and output has a defined shape. A wrong input is rejected with a clear message, and the agent corrects itself.
- **The resilience layer** wraps every tool call:
  1. **validate** the input
  2. **timeout** after 10 s, so it doesn't wait forever
  3. **retry** twice (after 0.5 s, then 1 s)
  4. **circuit breaker:** after 3 failures, stop calling that server for 60 s, like a fuse in your house
  5. a failure becomes a readable **ToolError**, not a crash
  6. every call is written to the **trace** (SQLite)
- **Safety validator** (`safety.py`). A dig must have:
  - an acoustic "yes" in that area
  - a **named approver**
  - a role of **supervisor or engineer**
  - no other open dig on the case

  It lives **inside the tool**, so the UI, the API, the AI and an MCP client are all blocked equally. A viewer or field-crew approval is refused, and NEER escalates to a human.
- **SCADA is read-only.** NEER never switches a pump or valve.
- **Idempotent work orders.** Asking twice returns the same open order: no duplicate crews.
- **Chaos switches** (for the demo), which break things on purpose:
  - SCADA times out
  - the AI returns broken JSON
  - sensor 241 dies
  - the crew hears nothing
  NEER recovers from each. **20/20 chaos runs still closed FIXED.**
- **Shared world** (`world.py`). The city, cases, work orders and KPIs, saved in `data/world.pkl` under a **file lock** (only one process writes at a time), so the 4 server processes share one city.
- **MCP (Model Context Protocol).**
  - An open standard (from Anthropic) for giving AI agents tools: a "USB port" for AI tools.
  - Each server lists its tools with a **JSON schema**, and the client calls them.
  - We use **stdio** transport: the client starts each server as a child program, and they talk through standard input/output with **JSON-RPC** messages.
  - Built with **FastMCP** (the official Python SDK).
  - If MCP fails, the call **falls back** to a direct call, and the trace records it.

---

## PART 7: The agents and the AI (`neer/agents/`)

- **LangGraph** is a library that describes agents as a **graph**: boxes (nodes = agents) and arrows (edges = who runs next).
  - The shared memory is **CaseState**. It holds status, tier, zone, leak size, areas, visits, re-plans, approvals, verdict, the timeline and the **evidence ledger**.
- **The flow:**
  1. Sentinel → Skeptic gate → Detective → Orchestrator → Skeptic review
  2. → [HUMAN approves the plan]
  3. → Field Commander (listen)
  4. → Orchestrator → [HUMAN approves the dig]
  5. → Field Commander (dig)
  6. → Auditor

  The arrows back are **re-plans**:
  - acoustic no → Orchestrator
  - NOT FIXED → Orchestrator (re-listen at the repair site)
  - PARTLY FIXED → Detective
  - INCONCLUSIVE → wait, or escalate
- **Human gates.**
  - `interrupt()` pauses the graph and shows Approve / Reject.
  - `Command(resume=...)` continues with the human's answer: yes or no, name, role.
  - The **checkpointer** (InMemorySaver) remembers the paused state. Honest limit: it doesn't survive a restart.
- **Budget guard.** 8 visits / 6 re-plans per search round, then escalate. It never loops forever.
- **Two brains:**
  - **Rules / engine own:** physics, numbers, thresholds, safety, verification.
  - **AI owns:** interpreting the evidence, choosing the most likely hypothesis, asking for missing evidence, choosing *where* to search next, explaining. It may always choose the more cautious option.
- **The LLM chain:** Groq (openai/gpt-oss-120b) → Gemini (gemini-3.5-flash) → Ollama (qwen2.5:7b, runs locally) → **rules** (always works, so NEER runs with no internet or keys).
  - **Structured answers.** The AI must fill a form (e.g. `PlanAnswer`: action, target_area, reason, cites), and the choice must be in an **allowed set**.
  - A **guard** checks it. For example: "a dig only after an acoustic yes in that same area".
  - A bad answer gets one retry, then the next provider.
  - The **rule veto**: the AI can never dismiss a clear leak.
  - **Decision log.** Every AI decision records the provider, its choice, what the rules would have chosen, the guard result and the evidence cited. These show as badges on the timeline.
- **Evidence ledger.** Every finding is a row: when · dimension · finding · supports (leak / against / neutral / fixed) · reliability · source tool. It's a court record for the case.

---

## PART 8: What you see: the Control Room (`neer/app/`)

- **Streamlit.** A Python library that turns a Python script into a web page. Every click reruns the script, and `st.session_state` remembers values between reruns. The browser talks to it over a **WebSocket**, a permanent two-way connection.
- **Sidebar:**
  - **Quick start** demo buttons
  - scenario, seed
  - reasoning (rules / AI chain)
  - map (city / schematic)
  - tools (in-process / 4 MCP servers)
  - approver name and **role**
  - animation speed
  - Start / Autopilot
  - chaos switches
  - "reveal true leak" (judges only)
- **Hero banner.** Animated waves, a pulsing LIVE dot and live counters.
- **KPI strip:**
  - cases
  - false alarms avoided
  - acoustic checks, digs, wasted digs
  - repairs proven
  - crew-hours
  - AI decisions · fallbacks · refused by safety rules
  - water saved
- **Mission stepper.** SUSPECT…REPLAN. The current step glows, and REPLAN shows ↺ ×N.
- **Outcome banner:**
  - FIXED: a green stamp with counters running up (m³/day, ₹/day at an **assumed** ₹25/m³)
  - escalated: amber
  - no crew sent: blue
- **Map views:**
  1. **2D ops map:** Madurai basemap (placement is illustrative) or schematic when offline. It shows zones, pipes by diameter, meters, relative-likelihood heat, the search area glowing, quiet areas grey, the repaired area green and the crew marker.
  2. **3D city view:** tilted and rotatable. Every junction is a 3D column, and the suspected area rises in red/orange with a glow. Controls: **Fly to suspected area**, Tilt, Rotate (Ctrl/right-drag also rotates).
  3. **Blueprint 3D:** a drafting-board look like a film blueprint scene. White wireframe city blocks on a dark grid; the suspected pipes glow red and orange, with a "LEAK SUSPECTED A-xxx" label. It works fully offline. **The blocks are illustrative; the pipes, areas and likelihoods are real case data.**
- **"Water nobody paid for" chart.** The zone's extra inflow against the normal ±2σ band.
- **Evidence card.** Case id, tier, inflow, pressure dips, masked sensors, ops check, areas, next step.
- **Auditor meter.** The evidence climbing hour by hour to the 99:1 and 999:1 lines.
- **Decision card + Approve / Reject.**
- **Sub-tabs:** Agent timeline (with AI / rules / guard badges), Evidence ledger, Tool trace.
- **Live agent flowchart + decision cards.**
- **Pop-up toasts:** alarm, leak heard, dig refused, FIXED / NOT FIXED.
- **Operations board tab.** Kanban columns (Watch · Investigating · Waiting for approval · Field work · Verifying · Closed), an impact strip, "Run all demo scenarios", and a **case report PDF**.
- **Twin sandbox tab.** Inject a what-if (a leak, pump trip or valve), see the predicted pressure change on the map, zone bars, a plain sentence, and a **3D pressure landscape** you can rotate. You can also run a case on it.
- **Database & API tab.** Whether the API is connected, the endpoint list, **run a case through the API**, table counts, stored cases, the 4 detail tables and a read-only SQL box.

---

## PART 9: Backend API and database

- **REST API (FastAPI)**, in `neer/api/server.py`. Run it with `uv run uvicorn neer.api.server:app --port 8000`; the docs are at `/docs`.

  | Method | Path | What it does |
  |---|---|---|
  | GET | `/api/health` | is the backend up? |
  | GET | `/api/scenarios` | the 16 scenarios |
  | GET | `/api/tools` | the 19 tools |
  | **POST** | `/api/cases` | run a full case |
  | GET | `/api/cases` | the stored cases |
  | GET | `/api/cases/{id}` | one case in detail |
  | GET | `/api/kpi` | totals |
  | GET | `/api/trace` | recent tool calls |

  - Bad input returns 422, unknown ids return 404, and cases run one at a time (a lock).
  - **CORS** is on, so other web pages may call it.
  - No login yet (it's a localhost demo). The next step is API keys or JWT.
- **SQLite case database** (`data/neer.db`), in `neer/store.py`. It has 5 tables:

  | Table | Holds |
  |---|---|
  | `cases` | one row per case |
  | `timeline` | every agent message |
  | `ledger` | every piece of evidence |
  | `approvals` | who, which role, which gate, yes or no |
  | `work_orders` | every crew order, who approved it, its result |

  - **WAL mode** lets readers and a writer work together.
  - **Parameterised queries** (`?`) block SQL injection.
  - The SQL box opens a **read-only** connection and accepts one SELECT only.
  - A database error never stops a case.
- **Who writes:** every agent step (the graph wrapper `_recorded`), and the field tools (work orders, even inside the field-mcp process).
- **Who reads:** the dashboard and the API.
- **Other storage:**
  - `data/trace.db`: tool calls
  - `data/world.pkl`: the live simulation
  - `data/chaos.json`: the chaos switches
  - the fingerprint cache
- **Evaluation** (`neer/eval/`):
  - `run_eval.py`: 16 scenarios × seeds 41–45, never used for tuning. **79/80 passed**, with 0 wrong closures, 0 unapproved digs and 0 invalid tool calls.
  - `ablation.py`: switch agents off one by one on the same 72 cases.

    | System | Tickets closed while still leaking | Crews sent for look-alikes |
    |---|---|---|
    | Threshold alarm | 52% | 56% |
    | Full NEER | **0%** | 6% |

  - `llm_eval.py`: rules vs live AI. Honest note: free quota ran out, and only 13 of 337 decisions were live.
  - Engine report:
    - false alarms 0%
    - correct zone 96–98%
    - found within 3 visits 58–75%
    - 0.09–0.18 wasted digs per leak
- **Tests.** `pytest`, **84 test runs**, covering the sim, engine, tools/MCP/safety, agents, AI split, dashboard, and API + database.

---

## PART 10: Glossary: every word, simply

- **Agent:** a program that decides what to do next, acts with tools, checks the result and changes its plan. Unlike a simple script, it loops until the goal is met.
- **Agentic AI:** AI that plans, acts and self-corrects, not only answers questions.
- **Ablation study:** remove one part at a time to prove each part matters.
- **ACID:** a database promise: all-or-nothing saves (Atomic), always valid (Consistent), no interference (Isolated), saved for good (Durable).
- **Acoustic logger:** a microphone on a pipe that listens for the hiss of a leak.
- **Allowed set:** the only choices the AI may pick from.
- **API:** Application Programming Interface: a way for programs to talk to each other.
- **ASGI / Uvicorn:** the web server standard and the program that runs FastAPI.
- **Baseline:** what "normal" looks like.
- **Bulk meter:** a big customer's own meter.
- **Checkpointer:** saves the agent graph's state so it can pause and resume.
- **Circuit breaker:** stops calling a failing service for a while, like a fuse.
- **Commit (git):** a saved snapshot of the code, with a message.
- **CORS:** a browser rule about which websites may call an API.
- **CSV:** a simple table file that Excel opens.
- **Dashboard:** a screen with the important numbers and controls.
- **Deck.gl / pydeck:** a library for drawing 3D maps in the browser (pydeck is its Python version).
- **Digital twin:** a computer copy of the real network that answers "what if?".
- **DMA:** District Metered Area: a zone with meters on its borders.
- **Emitter:** EPANET's model of a leak hole.
- **Endpoint:** one URL of an API (e.g. `/api/cases`).
- **Entropy:** a number for how uncertain we are. It drops when we learn something.
- **EPANET / WNTR:** the EPA's water network simulator / its Python wrapper.
- **Escalate:** hand the case to a human.
- **Evidence ledger:** the record of every finding, with its source.
- **FastAPI:** a Python library for building web APIs quickly, with automatic docs.
- **Fallback:** plan B when plan A fails.
- **Fingerprint:** how every sensor's pressure changes for a leak at one junction.
- **Guard:** code that checks the AI's answer before it is used.
- **HTTP status codes:** 200 OK · 404 not found · 422 bad input · 429 too many requests.
- **Idempotent:** doing the same request twice has the same effect as once.
- **Information gain:** how much a test reduces uncertainty.
- **Interrupt / resume:** pause the agents for a human, then continue.
- **JSON:** a text format for data (`{"key": "value"}`).
- **JSON-RPC:** a way to call a function on another program by sending JSON messages.
- **JSON schema:** a description of which fields and types a JSON message must have.
- **KPI:** key performance indicator: an important number to watch.
- **LangGraph:** a library for building agents as a graph with state.
- **Latency:** how long something takes.
- **Likelihood (relative):** how well the evidence fits a place, compared with other places. It is not an exact probability.
- **LLM:** Large Language Model: the AI that reads and writes text (e.g. Groq's gpt-oss, Gemini).
- **Log-likelihood ratio (LLR):** a running score of how much more the evidence supports one explanation than another.
- **MCP:** Model Context Protocol: a standard plug for AI tools.
- **Mean / standard deviation (σ):** the average / how much values normally spread around it.
- **Modularity clustering:** splitting a network into groups with many links inside and few between.
- **NRW:** non-revenue water.
- **Ollama:** runs AI models on your own laptop.
- **OpenAPI / Swagger:** automatic, clickable API documentation.
- **Parameterised query:** SQL with `?` placeholders, so user text can't become commands (safe from SQL injection).
- **Pickle:** Python's way to save objects to a file.
- **Posterior:** the updated belief after seeing the evidence.
- **Pydantic:** Python data shapes with automatic checking.
- **Rate limit:** a maximum number of requests per minute or day.
- **RBAC:** role-based access control: what you may do depends on your role.
- **Resilience:** the ability to keep working when parts fail.
- **REST:** a style of web API: URLs for things, GET to read, POST to create or run.
- **Scenario:** a scripted test situation with an expected ending.
- **SCADA:** Supervisory Control And Data Acquisition: a utility's remote monitoring system.
- **Seed:** a number that makes "random" results repeatable.
- **Sensitivity / false-positive rate:** how often a test catches a real leak / how often it cries wolf.
- **Session state:** Streamlit's memory between reruns.
- **SPRT:** Sequential Probability Ratio Test: decide as soon as the evidence is strong enough.
- **SQL / SQLite:** the language for databases / a small database stored in one file.
- **stdio / stderr:** a program's standard input/output channels / its error channel.
- **Streamlit:** turns Python scripts into web apps.
- **Structured output:** the AI must answer in a fixed form, not free text.
- **t-score:** how many "normal wobbles" away a value is.
- **Timeout:** stop waiting after a set time.
- **Toast:** a small pop-up message.
- **Trace:** the log of every tool call.
- **uv:** a fast Python package and project manager (it installs everything from `uv.lock`).
- **WAL:** write-ahead log: SQLite's mode for safe multi-user access.
- **WebGL:** the browser's 3D drawing system (used by the 3D views).
- **WebSocket:** a permanent two-way connection between browser and server.

---

## PART 11: Practice. Explain these out loud
1. Tell the 10-year-old story in 60 seconds.
2. Why can't a pump trip fool NEER? *(Pressure moves, water use doesn't; the Skeptic replays it in the twin.)*
3. How does NEER know where the leak is? *(Meter → which zone and how big; pressure fingerprints → which area; the listening device confirms.)*
4. Why not dig at the most likely spot straight away? *(Listen first. It costs 0.09–0.18 wasted digs per leak, against 0.92–1.36 for systems that dig blindly.)*
5. How do you know the repair worked? *(The independent Auditor measures before and after, hour by hour, with the 999:1 rule.)*
6. What does the AI decide, and what can it never do? *(See Part 7, "Two brains", and the rule veto.)*
7. What happens if the internet or the AI goes down? *(Next provider → rules; MCP → direct; the map goes schematic; Blueprint 3D works offline.)*
8. Show a refused dig and explain why. *(A viewer role; the safety validator inside the tool.)*
9. What is stored in the database when I press Approve? *(An approvals row; a work order if valid; timeline rows.)*
10. What are your honest limits? *(Simulated city; no live SCADA; relative likelihoods; the API has no login; the paused state isn't persistent; the AI evaluation was quota-limited.)*

**How to run (Mac):**
- Terminal 1: `cd ~/Desktop/HACKSPRINT/NEER && uv sync && uv run uvicorn neer.api.server:app --port 8000`
- Terminal 2: `uv run streamlit run neer/app/dashboard.py`
- Restart Streamlit after updating files.

---

## PART 12: Autonomous night watch (the new main mode)

**For the 10-year-old:**
- Nobody tells NEER where the problem is.
- Every night, while the city sleeps (2 to 4 in the morning), the Sentinel reads every meter and every pressure sensor.
- If a zone is drinking water while everyone is asleep, something is leaking. NEER opens a case **by itself**.
- It sends the listening crew by itself too, because listening harms nobody.
- In the morning it asks the supervisor: "May we dig here?"

**Why 2–4 AM?** This is the **minimum night flow** method, the classic technique used for DMAs. At night real use is lowest, so leaks stand out most.

**How it works** (`neer/live.py`):
- **Live city:** a continuous simulation. We hide a schedule of events by night:
  - leaks: 20 L/s (night 2), 12 L/s (night 8), 40 L/s with a wrong first repair (night 15), 15 L/s (night 21)
  - a pump trip (night 4)
  - planned flushing (night 6)
  - fire-fighting (night 10)
  - a frozen sensor (night 12, fixed on night 14)
  - a valve closure (night 18)
  NEER is never told. Judges can see the schedule only with "reveal".
- **Each night:**
  1. the night's hidden events start
  2. one day of SCADA data arrives
  3. **night scan:** for each zone, the 02:00–04:00 inflow vs normal (excess L/s and t-score), the biggest pressure drops, sensor health, the ops log and the calendar. That's 600 raw readings.
  4. the Sentinel's alarm check over 1, 2 and 3 days
- **What can happen:**
  - **clean night**
  - **look-alike explained:** a case is opened and the Skeptic dismisses it, so no crew is sent
  - **watching:** a small signal, or yesterday's look-alike still in the multi-day window
  - **case opened by NEER:** the agents investigate; listening surveys are approved by the standing **night policy**; a dig waits in the **inbox**
  - **added to an open case:** the same zone already has a case, so no duplicate is opened
- **Safety is unchanged.** Only a named supervisor or engineer can approve a dig. A viewer is refused inside the tool, and the case escalates.

**Result** (24 nights, seed 7, digs approved):
- **all 4 hidden leaks proven FIXED**, including the wrong repair (NOT FIXED → re-listen → FIXED)
- no crew sent for any look-alike
- 14,400 raw readings checked

**Three problems we fixed to make it work:**
1. Days spent inside a case (the Auditor watches up to 3 days) were "swallowing" nights, so some events were never scanned. The schedule now follows the night counter.
2. After a repair, the 3-day window still contained the old leak water and opened a phantom case. Windows no longer reach back past a proven repair.
3. A fresh leak on its first day was sometimes called a "short event". The Skeptic now also checks minimum night flow: a daytime event is gone by 2 AM, a leak is not. The Auditor also measures the pre-repair loss on the stronger of the 1-day and 2-day windows.

**The screen** (tab "Night watch (autonomous)", the first tab):
- a night-sky intro with the city clock
- buttons: **Run tonight's 02:00–04:00 scan**, **Fast-forward 7 nights**, **New city**
- a KPI strip: nights, raw readings, clean nights, cases opened by NEER, look-alikes explained, waiting for approval, repairs proven, water saved
- a **night calendar** of coloured squares (green clean, amber look-alike, grey watching, red case, purple added); the latest one pulses
- **"what the Sentinel read":** the zone night-flow chart with the alarm line, pressure drops, sensor health, ops log, calendar
- **inbox:** each case NEER opened, with **Approve dig / Reject** and **Show on map** (opens it in the Control Room) (the map, the 3D views, the Auditor)
- the night log, and (reveal) the hidden schedule

**Glossary additions:**
- **Minimum night flow (MNF):** the water entering a zone in the quietest night hours; the standard leak indicator for DMAs.
- **Standing approval / night policy:** permission given in advance for one safe kind of action (listening), never for digging.
- **Autonomous:** acts on its own within limits a person has set.

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
