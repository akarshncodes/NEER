# Demo script (5 minutes): the Guided demo tab

**Before the judges arrive:**
- Run `uv run python scripts/selfcheck.py`. It should show 9/9 PASS.
- Run `./run_demo.sh`.
- Open localhost:8501.
- To have Groq answer the AI questions, set **Reasoning → LLM chain** in the sidebar. Rules only also works offline.

| # | Press | What appears | Say |
|---|---|---|---|
| 1 | **Start the city** | The city card | "Indian cities lose about 38% of treated water before billing, and nobody checks repairs. NEER investigates with evidence, acts only with human approval, and closes a case only on proof." |
| 2 | **Run the 02:00–04:00 scan** | Night calendar (1 clean, 2 case), zone tiles, night-flow chart | "No one picked a scenario. At 2 AM the Sentinel read 600 raw readings. Zone Z1 took far more water than a normal night, so NEER opened the case itself." |
| 3 | **Show the investigation** | Mission stepper, map with the suspected area, the agents' team chat | "The Skeptic couldn't explain it away, the Detective ranked the areas, and the crew listened before any dig. Now it asks a person." |
| 4a | **Try as a viewer** | Red REFUSED message | "The safety rule is inside the tool. No button, API call or AI can bypass it." |
| 4b | **Approve the dig as supervisor** | Green FIXED banner with counters, the map's repaired area, the Auditor's message | "The crew said repaired, but NEER doesn't trust that. The Auditor measured the water itself, hour by hour, to 999:1." |
| 5 | **Is the leak really fixed?** / **Summarise in Tamil** | The AI's answer and who answered it | "The AI answers only from this case's record, and it shows who answered." |
| 6 | (appears by itself) | Night-by-night dataset chart with the hidden truth line; the REST API status | "The network is the EPA's real Net3. The readings are simulated by the EPA's engine, and the leaks are hidden, so we can score NEER. Everything is in dataset/ as CSV and served by the API at :8000/docs." |

**Then, if asked:**
- **Control Room:** 3D city view, Blueprint 3D, Ask NEER, Team chat, chaos buttons.
- **Night watch:** Play the week.
- **Dataset:** download the CSV or ZIP.
- **Database & API:** run a case through the API, read-only SQL.
- **localhost:8000/docs:** try any endpoint.

**If something misbehaves:**
- Press **Restart demo** at the top of the Guided tab.
- If the page looks stale, press Ctrl+C and run `./run_demo.sh` again.
- The Guided demo uses only the schematic map and charts, so it works offline and in any browser.
