# 7-minute demo script (Control Room)

Start: `uv run streamlit run neer/app/dashboard.py`. In the sidebar, choose Rules only (or LLM chain if keys are set) and tools **via 4 MCP servers**, with animation at 0.35 s.

| Time | Do this | Say this |
|---|---|---|
| 0:00 | Title slide | "Indian cities lose about 38% of their treated water as non-revenue water, and a big part of it is physical leakage. When someone fixes a leak, nobody checks. NEER investigates with evidence, acts only with human approval, and doesn't close a case until independent measurements prove the repair worked." |
| 1:00 | Scenario **pump_trip** → Start case | "Pressure dropped across the city. The Skeptic replayed the logged pump trip in our digital twin: pressure moved but water use didn't. Not a leak, so no crew." (timeline, WATCH) |
| 2:00 | Scenario **leak_20** → Start case | "Zone Z5's water bill is +20 L/s. The Detective ranks areas by relative likelihood; it doesn't pretend these are exact probabilities. The Orchestrator picks the next-best survey. The Skeptic reviews the plan. Open the **Evidence ledger** tab: every finding has a source tool and a time." |
| 2:40 | Press **Crew hears nothing**, then **Approve** | "Area A is quiet. Its probability drops and the Orchestrator re-plans on its own." |
| 3:20 | Press **SCADA times out**; set approver role to **viewer** and approve the dig | "SCADA just failed; the tool layer retried and recovered. Now a *viewer* tries to approve a dig, and the safety validator refuses. Only a supervisor or engineer can approve physical work, and NEER escalates instead of working around the gate." Then switch the role back to **supervisor** and press Start case again. |
| 4:00 | Auditor meter crosses FIXED | "The Auditor never reads the crew's report or the Detective's answer. It measures the loss itself before and after. Proven FIXED at 999:1, so the contractor's payment is released. About 1,700 m³ of water saved per day." |
| 4:40 | Scenario **wrong_repair** → Autopilot | "Here the crew fixed the wrong pipe. The Auditor says NOT FIXED, the payment is held, and NEER re-listens at the site and fixes it." |
| 5:40 | Show docs/ABLATION.md and docs/EVAL.md | "Do the agents matter? On the same cases, a threshold alarm leaves 52% of tickets closed while still leaking; full NEER leaves 0%. The Skeptic cuts false dispatches from 56% to 6%. On fresh test cities, 79/80 runs passed, with 0 wrong closures and 0 unauthorised actions. All simulated, and we say so." |
| 6:30 | Close | "NEER is designed for the DMA and SCADA data that AMRUT 2.0 requires, read-only and human-supervised. The next step is BattLeDIM validation, then a one-DMA pilot. It is not live-connected today." |

**Backups:**
- Record a screen video of this run.
- If the Wi-Fi fails, use Rules only with in-process tools; it needs no internet at all.
