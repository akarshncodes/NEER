# Round 3 guide: UI with AI, API integration, Dataset

*A friendly walk-through. Read it like a conversation, then practise the demos at the end.*

---

## Before anything: start it (2 minutes)

```
cd ~/Desktop/HACKSPRINT/NEER
uv sync                                                  # once, needs internet
uv run uvicorn neer.api.server:app --port 8000           # Terminal 1: the API  → localhost:8000/docs
uv run streamlit run neer/app/dashboard.py               # Terminal 2: the UI   → localhost:8501
```
- To show the live AI, set Reasoning to **"LLM chain"** in the sidebar. The Groq and Gemini keys are already in `.env` on your Mac.
- No internet? Everything still works with **Rules only**.

---

## Part 1: "Show us the UI and where the AI is"

**Think of it like this.** The dashboard is the control room of a water board. The AI is a team of six colleagues sitting in it. You can watch them work, ask them questions, and approve what they want to do.

**Where the AI lives in the UI** (point at each one):
1. **Night watch tab.** Nobody picks a scenario. Every night at 02:00–04:00 the agents scan all raw data and **open cases by themselves**.
   - The **morning briefing** tells you in plain English what happened and what needs you.
   - The **Inbox** is where the AI asks for your approval.
2. **Control Room → "Ask NEER (AI)".** A chat box: *"Why this area?"*, *"Is the leak really fixed?"*, *"Summarise in Tamil"*.
   - With LLM chain on, **Groq** (or Gemini) answers.
   - The AI gets only this case's record (agent messages, evidence ledger, verdict) and is told never to invent numbers.
   - Under every answer it shows **who answered** and how many milliseconds it took.
   - If the internet or the quota fails, a deterministic explainer answers from the same record, so the box never breaks.
3. **Team chat.** The six agents talk like a WhatsApp group. Each message has a tag: `groq:…` if a live model made that decision, `rules` if the deterministic policy did.
4. **Decision cards and badges.** "AI: groq", "rules", "guard: accepted", "guard: vetoed". These show where the AI decided and where a safety rule stopped it.
5. **Live flowchart.** The agent graph lights up as each agent works. Yellow boxes are where it waits for a human.
6. **KPI tile "AI decisions · fallbacks · refused by safety rules".** It counts how many decisions the live model made.

**What the AI decides, and what it may never decide** (they *will* ask):
- **AI decides:**
  - which explanation is most likely (leak / pump / planned work / sensor fault / short event)
  - whether it needs more evidence
  - which area to search next
  - how to explain things to people
- **Rules decide:**
  - all numbers and physics
  - the alarm thresholds
  - the safety gate (no dig without an acoustic "yes" + a supervisor/engineer)
  - the Auditor's proof
- **Rule veto:** if the AI says "dismiss" on a clear leak, the rule overrides it. The veto is shown in the chat and the ledger.

**How the UI talks to the backend** (a common follow-up):
- The dashboard is **Streamlit**: Python turned into a web page, talking to the browser over a WebSocket.
- A click runs the agents (**LangGraph**). The agents call tools, either inside the same program or through **4 MCP server programs** ("Tools via" in the sidebar).
- When an agent needs a human, the graph **pauses** (`interrupt`), the UI shows Approve / Reject, and your answer **resumes** it.
- Everything is written to the **SQLite database**, and the **REST API** reads the same database.

**Show-it lines:**
- "Here's NEER opening a case by itself at 2 AM; here's the AI asking me for permission."
- "Let me ask it: 'Why this area?' Groq answered, using only the case's own evidence. Here's the provider and the time it took."
- "Now I'm a viewer and I press Approve. It's refused, because the safety rule is inside the tool, not in the button."

---

## Part 2: "What APIs do you integrate?"

Say **"four kinds"** and count on your fingers.

**1. Our own REST API (FastAPI).** This is how other systems use NEER.
- Open **localhost:8000/docs**: every endpoint is listed and has a "Try it out" button.

| Method | Path | What it does |
|---|---|---|
| GET | `/api/health` | is it up? database and AI keys present |
| GET | `/api/scenarios` · `/api/tools` | the 16 scenarios · the 19 tools |
| **POST** | `/api/cases` | run a whole investigation, e.g. `{"scenario":"leak_20","seed":7,"approver":"Ravi","approver_role":"engineer"}` |
| GET | `/api/cases` · `/api/cases/{id}` | stored cases · one case's timeline, ledger, approvals, work orders |
| **POST** | `/api/cases/{id}/ask` | **ask the AI about a case** over the API |
| GET | `/api/dataset` · `/api/dataset/{file}` | the demo dataset as JSON |
| GET | `/api/kpi` · `/api/trace` | totals · the latest tool calls |

- A bad request returns **422** with the reason (e.g. role "admin"). An unknown id returns **404**.
- It runs one case at a time (a lock), and CORS is on.
- **Honest limit:** no login yet, because it's a localhost demo. The next step is API keys or JWT with the same roles.

**2. AI model APIs.**
- **Groq** (`openai/gpt-oss-120b`) → **Google Gemini** (`gemini-3.5-flash`) → **Ollama** (a local model) → **rules**.
- Keys live in `.env`, never in the code or in git.
- Every agent answer must match a strict form (**structured output**) and pick from an **allowed list**.
- A bad answer is retried once, then the next provider is tried.
- **Rate limits:** free tiers return HTTP **429**. We space calls out (`NEER_LLM_MIN_INTERVAL_S`), and a provider that fails twice on the network **rests for 60 s**, so the demo never freezes.

**3. MCP (Model Context Protocol).**
- The standard "plug" for AI tools.
- **19 tools on 4 servers:**
  - `scada-mcp`: read-only data
  - `twin-mcp`: the WNTR simulator
  - `field-mcp`: crews and SMS
  - `audit-mcp`: proof and KPIs
- Each server is a separate program talking **JSON-RPC over stdio**.
- If MCP fails, the call falls back to a direct call.
- Every call goes through validation → timeout → retry → circuit breaker → trace.

**4. Map tiles.**
- The 2D map uses OpenStreetMap tiles and the 3D map uses Carto tiles.
- Offline, the map falls back automatically (schematic / Blueprint 3D).
- SMS and crew systems are **simulated endpoints** behind `field-mcp`. In a real city you swap the tool body, and the agents don't change.

**Show-it lines:**
- "Here's Swagger. I'll POST a case. It ran the six agents, their tools and the approvals, and the case is now in the Database tab."
- "Here I ask the AI through the API: `POST /api/cases/{id}/ask` with `Is the leak really fixed?`"

---

## Part 3: "What dataset did you use? Show us the data."

**The one-sentence answer:**
> "The pipe network is **real and public**: the US EPA's **Net3** benchmark. The hourly sensor readings are **simulated** by the EPA's own hydraulic engine, with realistic noise. The leaks and look-alikes are **injected at known places and times**, so we can score every decision NEER makes against the truth."

**Why simulated?** Utilities don't publish SCADA data with the true leak locations, and without the truth you can't prove accuracy. This is also how the research field tests leak methods (e.g. the BattLeDIM competition). **Next step:** the public BattLeDIM L-Town dataset, then a utility's history, then one pilot zone.

**What's inside** (open the **Dataset** tab or the `dataset/` folder):
- **`network/`:**
  - 92 junctions (position, elevation, zone, sensor or not)
  - 117 pipes (length, diameter, zone, meter or not)
  - sources, tanks and pumps
  - 15 zone meters
  - 5 zones
- **`live_city/`:** the city for **37 days** (7 clean history days + 30 nights):
  - `scada_pressure_hourly.csv`: 20 sensors × 24 h × 37 days
  - `scada_zone_inflow_hourly.csv`: 5 zones × 24 h × 37 days
  - `ops_log.csv`, `supply_calendar.csv`: what operators logged / planned
  - `night_scan_0200_0400.csv`: what the Sentinel computes every night (night inflow vs normal, excess L/s, t-score)
  - `hidden_truth_JUDGES_ONLY.csv`: the 10 hidden events and their nights (NEER never reads it)
- **`scenarios/`:** one raw day for each of the 16 test scenarios
- In total: **27 files, about 2,600 rows, 352 KB**. `MANIFEST.csv` lists them all.

**The realism we added** (hidden from NEER):
- each consumer ±10% different from the model
- ±3% day-to-day and hour-to-hour variation
- sensors ±0.1 m
- meters with a 2% fixed bias + 1% noise
- a "20 L/s leak" is an EPANET **emitter** (a hole whose flow grows with √pressure)

**How to show it in 60 seconds:**
1. **Dataset** tab → Zone **Z1** chart. "See the dark night dots jump up on day 8 and *stay* up? That's a leak. A daytime spike that's gone by night is a look-alike."
2. Turn on **"Reveal true leak (judges only)"**. Red lines appear on the hidden events. "Night 2: a 20 L/s leak at junction 275. That's exactly where the dots jumped."
3. The pressure heatmap: the red rows are sensors near the leak, where pressure dropped.
4. **Browse any file** → `night_scan_0200_0400.csv` → **Download this CSV**, or **Download the whole dataset (ZIP)**, and open it in Excel.
5. "The same data is served by the API: `GET /api/dataset/live_city/night_scan_0200_0400.csv`."
6. "Rebuild it any time: `uv run python scripts/build_dataset.py`. The same seed always gives the same files."

**Excel check you can do live:** open `night_scan_0200_0400.csv` and filter night 2. Z1 inflow is **22.0 L/s against a normal 7.2**. Then open the hidden-truth file: night 2 is "leak: node 275, 20 L/s".

---

## Part 4: Every question they might ask (short answers)

**Dataset**
- *Is this real data?* The network is real (EPA Net3). The readings are simulated with the EPA's physics engine, and the events are injected. We say so on every screen.
- *Why not real data?* No utility publishes leak truth, and without the truth you can't measure accuracy. Next is BattLeDIM L-Town, a public dataset with real-style leaks.
- *How big is it?* 27 CSV files, about 2,600 rows. The live city covers 37 days × 24 hours for 20 pressure sensors and 5 zone meters. It's small on purpose, so anyone can open it in Excel.
- *How do you know it's realistic?* Hidden demand bias, daily and hourly variation, sensor noise and meter bias. Our first test used unrealistically big leaks and scored 24%, so we rebuilt it with 5–40 L/s leaks and harsh noise.
- *Can you add a new leak?* Yes: in the **Twin sandbox**, pick a junction and a size → Simulate → "Run a case on this".
- *Where do the numbers in your results come from?* 16 scenarios × 5 new seeds (79/80 passed), an ablation study, and an engine benchmark. They're all reproducible scripts in the repo.
- *Is the data leaked to the AI?* No. NEER reads only SCADA-like data (pressure, zone inflow, logs, calendar). The hidden truth file is for judges and scoring only.
- *What is the unit of the numbers?* Pressure is in metres of water head. Flow is in litres per second.

**AI in the UI**
- *Which model?* Groq's `openai/gpt-oss-120b`, then Gemini, then local Ollama, then rules.
- *Can it hallucinate a number?* The agents only pick from allowed options, and all numbers come from tools. "Ask NEER" answers only from the case record and says so when it doesn't know. The badges show which provider answered.
- *What if the AI says something unsafe?* The guard rejects any option outside the allowed list. A rule veto blocks dismissing a clear leak. The safety validator inside the tool blocks unsafe digs, whoever asks.
- *Show that the AI is live.* Set Reasoning to LLM chain, then Ask NEER: the caption under the answer says "answered by groq:openai/gpt-oss-120b · … ms". The timeline also shows `groq` tags.
- *Why is some output from "rules"?* The rules are the safety net. If the quota runs out or the internet drops, the rules answer, so the demo can't freeze.

**API**
- *Show the API.* Open localhost:8000/docs, then Try it out on `POST /api/cases`, then `GET /api/cases/{id}`.
- *Is it secure?* The inputs are validated and the database queries are parameterised. The SQL box is read-only. There's no login yet (it's a localhost demo); next is API keys or JWT.
- *How do the UI and the API share data?* Through one SQLite database (`data/neer.db`). A case run through the API appears in the dashboard's Database tab.
- *What's the difference between MCP and REST?* MCP is how the **agents** call their **tools**. REST is how **other systems** call **NEER**.

---

## Part 5: The 5-minute Round 3 demo
1. **(60 s) Night watch:** Start the live city → **Play the week**.
   - It stops on night 2: "NEER opened this case by itself and needs me."
   - Show the morning briefing and the Inbox, then **Approve dig**. It's proven FIXED.
2. **(60 s) Control Room → Show on map.** Use the 3D / Blueprint view, then **Ask NEER**: "Why this area?" and "Summarise in Tamil" (with the LLM chain on).
3. **(60 s) Dataset tab:** the Z1 chart, then Reveal (the red line lands exactly on the jump), then Browse → download the CSV.
4. **(60 s) API:** localhost:8000/docs → `POST /api/cases` → `POST /api/cases/{id}/ask` → `GET /api/dataset`.
5. **(60 s) Database & API tab:** "Run through the API", then the SQL box: "Digs and who approved them".

**If something fails live:**
- Switch to **Rules only** and **In-process**.
- Restart Streamlit (Ctrl+C, then run it again).
- The dataset charts don't need the network.
