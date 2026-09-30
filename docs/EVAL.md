# NEER agent evaluation

_Generated 2026-09-30 12:19 · brain: **rules** · tools: **direct** · seeds [21, 22, 23, 24, 25]_

## Result: **passed 76/80** runs (16 scenarios × 5 seeds)

Simulated city (EPA Net3, harsh noise). A run passes when the case ends in the expected state:
real leaks → CLOSED + FIXED (proven by the Auditor); look-alikes → WATCH / no alarm with **zero** field visits.

| Scenario | What happens | Expected | Passed | Avg visits | Avg tool calls | Tool errors recovered | Avg time |
|---|---|---|---|---|---|---|---|
| `quiet` | A normal day | watch_or_no_alarm | 4/5 | 1.6 | 13 | 0 | 0.4 s |
| `leak_20` | Hidden 20 L/s leak | closed_fixed | 5/5 | 2.6 | 23 | 0 | 0.4 s |
| `leak_10` | Small 10 L/s leak | closed_fixed | 4/5 | 2.4 | 21 | 0 | 0.4 s |
| `leak_40` | Burst 40 L/s | closed_fixed | 5/5 | 1.0 | 18 | 0 | 0.4 s |
| `pump_trip` | Pump 10 trips (logged) | watch_or_no_alarm | 5/5 | 0.0 | 6 | 0 | 0.3 s |
| `valve_closure` | Valve closed by operator (logged) | watch_or_no_alarm | 5/5 | 0.0 | 6 | 0 | 0.4 s |
| `planned_work` | Planned flushing (in calendar) | watch_or_no_alarm | 5/5 | 0.0 | 3 | 0 | 0.3 s |
| `fire_draw` | Fire-fighting draw | watch_or_no_alarm | 5/5 | 0.0 | 3 | 0 | 0.3 s |
| `stuck_sensor` | Pressure sensor freezes | watch_or_no_alarm | 5/5 | 0.0 | 3 | 0 | 0.3 s |
| `sensor_offset` | Sensor reads 2 m low | watch_or_no_alarm | 5/5 | 0.0 | 3 | 0 | 0.3 s |
| `two_leaks` | Two leaks in one zone | closed_fixed | 4/5 | 4.0 | 34 | 0 | 0.5 s |
| `wrong_repair` | Crew fixes the wrong pipe first | closed_fixed | 4/5 | 5.4 | 37 | 0 | 0.5 s |
| `chaos_scada` | Leak + SCADA timeouts | closed_fixed | 5/5 | 2.6 | 25 | 10 | 1.9 s |
| `chaos_llm` | Leak + broken LLM replies | closed_fixed | 5/5 | 2.6 | 23 | 0 | 0.4 s |
| `chaos_sensor` | Leak + a sensor dies | closed_fixed | 5/5 | 2.6 | 23 | 0 | 0.4 s |
| `chaos_crew` | Leak + crew hears nothing first | closed_fixed | 5/5 | 2.4 | 23 | 0 | 0.4 s |

## Highlights
- Cases wrongly closed while a leak was still running: **0/80**.
- Runs that did not pass ended safely (escalated to a human or on watch): **4/4**.
- Leak cases closed with proof: **42/45**, average 2.8 acoustic visits per case.
- Look-alike events that sent a crew: **1/35**.
- Wrong repairs caught by the Auditor (NOT FIXED, contractor held, re-planned): **5/5**.
- Second leaks found after PARTLY FIXED: **4/5**.
- Chaos runs (SCADA timeout, broken LLM JSON, dead sensor, crew hears nothing) that still closed FIXED: **20/20**.

Engine-level accuracy (detection, localisation, Auditor) is in `scripts/engine_report.py`.
