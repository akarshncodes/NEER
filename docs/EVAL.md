# NEER agent evaluation

_Generated 2026-09-30 21:11 · brain: **rules** · tools: **direct** · seeds [41, 42, 43, 44, 45]_

## Result: **passed 79/80** runs (16 scenarios × 5 seeds)

Simulated city (EPA Net3, harsh noise). A run passes when the case ends in the expected state:
real leaks → CLOSED + FIXED (proven by the Auditor); look-alikes → WATCH / no alarm with **zero** field visits.

| Scenario | What happens | Expected | Passed | Avg visits | Avg crew-h | Avg tool calls | Tool errors recovered | Avg time |
|---|---|---|---|---|---|---|---|---|
| `quiet` | A normal day | watch_or_no_alarm | 5/5 | 0.0 | 0.0 | 3 | 0 | 0.1 s |
| `leak_20` | Hidden 20 L/s leak | closed_fixed | 5/5 | 2.8 | 12.9 | 28 | 0 | 0.2 s |
| `leak_10` | Small 10 L/s leak | closed_fixed | 5/5 | 3.0 | 11.6 | 28 | 0 | 0.2 s |
| `leak_40` | Burst 40 L/s | closed_fixed | 5/5 | 1.2 | 8.5 | 21 | 0 | 0.2 s |
| `pump_trip` | Pump 10 trips (logged) | watch_or_no_alarm | 5/5 | 0.0 | 0.0 | 6 | 0 | 0.1 s |
| `valve_closure` | Valve closed by operator (logged) | watch_or_no_alarm | 5/5 | 0.0 | 0.0 | 6 | 0 | 0.1 s |
| `planned_work` | Planned flushing (in calendar) | watch_or_no_alarm | 5/5 | 0.0 | 0.0 | 3 | 0 | 0.1 s |
| `fire_draw` | Fire-fighting draw | watch_or_no_alarm | 5/5 | 0.0 | 0.0 | 3 | 0 | 0.1 s |
| `stuck_sensor` | Pressure sensor freezes | watch_or_no_alarm | 5/5 | 0.0 | 0.0 | 3 | 0 | 0.1 s |
| `sensor_offset` | Sensor reads 2 m low | watch_or_no_alarm | 5/5 | 0.0 | 0.0 | 3 | 0 | 0.1 s |
| `two_leaks` | Two leaks in one zone | closed_fixed | 4/5 | 3.6 | 18.2 | 39 | 0 | 0.2 s |
| `wrong_repair` | Crew fixes the wrong pipe first | closed_fixed | 5/5 | 3.8 | 20.3 | 39 | 0 | 0.2 s |
| `chaos_scada` | Leak + SCADA timeouts | closed_fixed | 5/5 | 2.8 | 12.9 | 30 | 10 | 1.7 s |
| `chaos_llm` | Leak + broken LLM replies | closed_fixed | 5/5 | 2.8 | 12.9 | 28 | 0 | 0.2 s |
| `chaos_sensor` | Leak + a sensor dies | closed_fixed | 5/5 | 3.0 | 13.2 | 29 | 0 | 0.2 s |
| `chaos_crew` | Leak + crew hears nothing first | closed_fixed | 5/5 | 2.2 | 9.9 | 25 | 0 | 0.2 s |

## Highlights
- Cases wrongly closed while a leak was still running: **0/80**.
- Safety: physical actions without a valid approver/role: **0**; invalid tool calls: **0** of 1466.
- Time to verified repair (simulated days from first anomaly to FIXED): median **3.0 days**; crew-hours per leak case: median **9.7 h**.
- Every case carries an evidence ledger (source tool, finding, direction, reliability): median 15.0 rows per case.
- Runs that did not pass ended safely (escalated to a human or on watch): **1/1**.
- Leak cases closed with proof: **44/45**, average 2.8 acoustic visits per case.
- Look-alike events that sent a crew: **0/35**.
- Wrong repairs caught by the Auditor (NOT FIXED, contractor held, re-planned): **5/5**.
- Second leaks found after PARTLY FIXED: **4/5**.
- Chaos runs (SCADA timeout, broken LLM JSON, dead sensor, crew hears nothing) that still closed FIXED: **20/20**.

Engine-level accuracy (detection, localisation, Auditor) is in `scripts/engine_report.py`.
