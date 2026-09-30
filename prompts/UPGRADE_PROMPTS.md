# Prompts: make the prototype look and feel advanced (jury feedback, 10 PM)
Jury feedback: "the prototype is very basic and simple, and the map is very bad".
Paste these into Claude Code (Code tab → Local → the NEER folder), **one at a time**, in this order.
After each one: tests green, take a screenshot, commit.

Every prompt starts with the same rules:
> Read CLAUDE.md first. Don't change anything in neer/engine or the evaluation numbers. Keep `uv run pytest -q` green. The dashboard must still work with no internet and no API keys.

---
## Prompt M: a new city map (most important, about 1.5 h)

Read CLAUDE.md and neer/app/components.py (network_map) and neer/app/dashboard.py. The jury said the map looks bad. Rebuild it as a proper operations map, without changing any engine logic.

1. **Two map modes** with a toggle in the sidebar: "City map" (default) and "Schematic".
   - **City map:** place the Net3 network on a real OpenStreetMap basemap of Madurai using `plotly.graph_objects.Scattermap` (map_style "open-street-map", no token needed).
     - Convert the Net3 x/y coordinates with a simple scale-and-shift so the network covers about 4 km × 3 km around Madurai (centre about 9.925 N, 78.12 E).
     - Put the transform in one function, `to_latlon()`, in neer/app/geo.py.
     - Add a small caption on the map: "Network placement is illustrative (EPA Net3 on a Madurai basemap)".
   - **If the tiles can't load (no internet),** fall back to the Schematic mode automatically.
2. **Pipes:**
   - line width by pipe diameter (mains thick, service pipes thin)
   - colour by zone, with the case zone at full colour and the others faded
   - pipes that cross zones drawn dashed, with a meter icon at the middle
3. **Zones:** a translucent filled polygon per zone (convex hull of its junctions, slightly padded) with a large label ("Z1 · 18 junctions").
4. **Leak likelihood:**
   - Colour the pipes and junctions of the top candidate areas on a white → orange → red scale by relative likelihood. Replace the big blue bubbles.
   - Show a colour bar titled "Relative likelihood (not calibrated)".
5. **Case layers:**
   - current search area: a thick, glowing outline
   - quiet areas (acoustic "no"): grey hatched outline
   - repaired area: green outline with a ✓ label
   - a crew/van marker at the current area during field work
   - a revealed true leak: a red droplet or star, shown only after the case closes
6. **Sensors:**
   - small circles coloured by their night pressure change (blue = normal, orange = dipping, grey with an X = masked/unhealthy)
   - a hover tooltip with the sensor id, zone, change in m and status
7. **Zoom:** after the Detective runs, zoom to the case zone automatically. Add a "Full city" button.
8. **Look:** a clean legend in one row under the map, no axes, a 600 px tall map, and consistent colours with the rest of the dashboard.
9. Add a test in tests/test_dashboard.py that builds both map modes without error (no network access in tests: mock or skip the basemap).
10. Take a screenshot at 1600×1000 of `leak_20` after the Detective step and after FIXED, and check it looks professional.

Commit as `stage9/app: operations map`.

---
## Prompt D: show the agents thinking (about 1 h)

Read CLAUDE.md, neer/agents/graph.py, nodes.py and neer/app/dashboard.py.

1. **Live agent flowchart panel:**
   - Draw the LangGraph graph (Sentinel → Skeptic → Detective → Orchestrator → Skeptic review → human approval → Field Commander → Auditor, with the loop-back arrows) as a Plotly or Graphviz diagram.
   - Highlight the node that is running now, and colour nodes already visited in this case.
   - Label the loop-back edges (acoustic no → re-plan, NOT FIXED → re-listen, PARTLY FIXED → Detective).
2. **Decision cards:** show the latest decision of each agent as a card with:
   - the agent name
   - its choice
   - the reason (from the timeline)
   - a badge for who decided: "AI: groq", "AI: gemini" or "rules"
   - the fallbacks, if any
   - the evidence it cited
3. **Evidence ledger as a proper table:**
   - coloured "supports" chips (leak / against / neutral / fixed)
   - a reliability column
   - the source tool
   - a filter by dimension
4. Add a KPI tile "AI decisions · fallbacks · refused by safety rules".
5. Screenshot and check.

Commit as `stage9/app: agent flowchart + decision cards`.

---
## Prompt S: digital-twin sandbox tab (about 45 min)

Read CLAUDE.md, neer/tools/twin.py (simulate) and neer/app/dashboard.py.

Add a new tab, "Twin sandbox (what-if)":
1. The user picks a junction (dropdown, or by clicking it on the map if Plotly selection works) and an event type: leak (5–40 L/s slider), pump trip or valve closure.
2. Press "Simulate". Call the existing `simulate` tool. Show the predicted pressure change at every junction as a colour map on the same city map, and the predicted change in each zone's inflow as a bar chart.
3. Add one sentence explaining the result, e.g. "A 20 L/s leak here lowers pressure at 3 sensors by more than 0.2 m and adds 20 L/s to Z5's inflow. A pump trip lowers pressure everywhere but changes no inflow."
4. Add a "Run a case on this" button that starts a NEER case with exactly that injected event (a custom scenario, seed from the sidebar).
5. Add a test that the sandbox's helper function returns pressure deltas for a leak.

Commit as `stage9/app: twin sandbox`.

---
## Prompt R: operations board + case report (about 45 min)

Read CLAUDE.md and neer/app/dashboard.py.

1. **Operations board tab:** a Kanban-style row of columns (Watch · Investigating · Waiting for approval · Field work · Verifying · Closed).
   - Show every case run in this session as a card: case id, zone, leak size, visits, verdict chip.
   - Add a button "Run all demo scenarios" that runs pump_trip, leak_20, wrong_repair and two_leaks on autopilot one after another and fills the board.
2. **Impact strip:**
   - water saved per day (m³)
   - crew-hours
   - wasted digs avoided
   - false alarms avoided
   - money saved per day. Use a clearly labelled assumption in config.py, e.g. `COST_PER_M3_INR = 25`, shown as "at ₹25/m³ (assumption)".
3. **Case report:** a "Download case report (PDF)" button that writes one page per case with:
   - a summary: zone, leak size, verdict, contractor decision
   - the timeline
   - the evidence ledger
   - the Auditor evidence chart image
   Use `fpdf2` (add it with `uv add fpdf2`). Label it "Simulated city: not field data".
4. Tests for the report builder (it creates a non-empty PDF).

Commit as `stage9/app: ops board + case report`.

---
## After these, if time allows before 3 AM
- Prompt A from AI_VALIDATION_PROMPTS.md (run the real AI chain and write LLM_EVAL.md), if not done yet. This matters most for the "AI / LLM integration" score.
- Then Prompt B (the AI chooses where to search and what evidence is missing, with a safety veto).
