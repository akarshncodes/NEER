# 7-minute demo script (Control Room)

Start: `uv run streamlit run neer/app/dashboard.py`. In the sidebar, choose Rules only (or LLM chain if keys are set) and tools **via 4 MCP servers**, with animation at 0.35 s.

| Time | Do this | Say this |
|---|---|---|
| 0:00 | Title slide | "38% of India's treated water vanishes underground. When someone fixes a leak, nobody checks. NEER doesn't panic, doesn't guess, and never trusts 'job done'." |
| 1:00 | Scenario **pump_trip** → Start case | "Pressure dropped across the city. The Skeptic replayed the logged pump trip in our digital twin: pressure moved but water use didn't. Not a leak, so no crew." (timeline, WATCH) |
| 2:00 | Scenario **leak_20** → Start case | "Zone Z5's water bill is +20 L/s. The Detective lights up three areas. The Orchestrator plans to listen first. The Skeptic reviews the plan." |
| 2:40 | Press **Crew hears nothing**, then **Approve** | "Area A is quiet. Its probability drops and the Orchestrator re-plans on its own." |
| 3:20 | Press **SCADA times out**; continue; approve the dig | "SCADA just failed. The tool layer retried and recovered; look at the trace." |
| 4:00 | Auditor meter crosses FIXED | "The Auditor never reads the crew's report, only the meters. Proven FIXED at 999:1, so the contractor's payment is released. ~1,700 m³ of water saved per day." |
| 4:40 | Scenario **wrong_repair** → Autopilot | "Here the crew fixed the wrong pipe. The Auditor says NOT FIXED, the payment is held, and NEER re-listens at the site and fixes it." |
| 5:40 | Show docs/EVAL.md | "On held-out test cities: 76/80 runs passed, 0 cases wrongly closed, and 20/20 chaos runs recovered. Simulated, and we say so." |
| 6:30 | Close | "It runs on data AMRUT 2.0 already mandates (DMAs, SCADA). Madurai's Mullaiperiyar scheme is commissioning 20 DMAs. NEER turns that data into proven repairs." |

**Backups:**
- Record a screen video of this run.
- If the Wi-Fi fails, use Rules only with in-process tools; it needs no internet at all.
