# Ablation study: do the agents matter?

Simulated EPA Net3 city, harsh noise. 36 leak cases (10/20/40 L/s; in 25 % the crew first fixes the wrong pipe but reports success) + 36 look-alike cases (pump trip, valve, fire draw, stuck sensor, sensor offset, planned work). Same cases for every system.

| System | Crews sent for look-alikes | Leaks really fixed | Tickets closed while still leaking | Wrong repairs caught | Digs / leak case | Wasted digs / leak case | Crew-hours / case |
|---|---|---|---|---|---|---|---|
| **A** Threshold alarm → dig at biggest pressure drop | 56% | 42% | 52% | 0% (never checks) | 1.86 | 1.36 | 10.6 |
| **B** Leak model only (dig most likely area) | 56% | 56% | 35% | 0% (never checks) | 1.61 | 0.92 | 9.8 |
| **C** Leak model + Skeptic | 6% | 56% | 35% | 0% (never checks) | 1.61 | 0.92 | 5.3 |
| **D** Leak model + Orchestrator (listen before dig) | 56% | 58% | 25% | 0% (never checks) | 0.94 | 0.17 | 16.2 |
| **E** Full NEER (+ independent Auditor, re-plan) | 6% | 78% | 0% | 88% | 1.14 | 0.17 | 8.3 |

How to read it: each added agent removes one failure mode - the Skeptic stops crews being sent for look-alikes, the Orchestrator's listen-before-dig removes wasted excavations, and only the independent Auditor catches repairs that did not work (every other system closes on the crew's word).

Simulation only; numbers come from `uv run python -m neer.eval.ablation`.
