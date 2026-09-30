# Claude Code prompt: Stage 2 (physics engine)

Paste everything below the line into Claude Code once Stage 1 is green and reviewed.

---

Continue NEER. Read `CLAUDE.md` and `docs/SPEC.md` section 2. The tested algorithm reference is in `reference/engine.py`, `reference/skeptic.py`, `reference/evalx.py` and `reference/exp_v3.py`. Re-implement cleanly on top of our Stage 1 `neer.sim` and the `neer.schemas` contracts; do not import `reference/`. Give me a short plan first, then implement.

Build `neer/engine/` as pure functions and classes (no LLM, no MCP). Everything must return the Pydantic models from `schemas.py`, and all parameters come from `config.py`.

1. **`baseline.py`**: a `Baseline` class built from certified-clean days.
   - Per-hour means and stds, with floors.
   - `zone_excess(days, hours)` using 1/σ² hour weights and common-mode removal.
   - `ex_se` and `p_thr` by leave-one-out.
   - `pressure_score(days, masked)`.
   - `add_certified_clean(day)`.
2. **`detect.py`**: `detect(baseline, days) -> Detection`, giving the three witnesses (water, pressure, persistence), the tier (WATCH / PROBABLE / CONFIRMED), per-zone t-scores, and the top sensor dips.
3. **`skeptic.py`**: `skeptic_check(baseline, day, ops, calendar, twin) -> SkepticVerdict`, running in order: sensor health (frozen, lone wolf → mask), operations replay (twin delta subtraction; "pressure moved but consumption didn't"), temporary, leak. Every verdict carries a one-sentence plain-English reason and the numbers behind it.
4. **`locate.py`**: `locate(baseline, days, library, priors=None) -> LocateResult`, with the size-aware fingerprint likelihood × zone term × priors, the posterior, the leak size, and an evidence list.
5. **`plan.py`**: `plan_search_areas(posterior, weights) -> list[SearchArea]` and `SoftElimination` (acoustic "no" ×0.15, empty dig ×0.1).
6. **`acoustic.py`**: `acoustic_check(area, truth, rng) -> AcousticResult` (sensitivity 0.85, FPR 0.05).
7. **`audit.py`**: `sequential_verify(baseline, hourly_inflow_iter, zone, pre_excess) -> AuditVerdict`, with the SPRT, the partial rule (>35% drop), INCONCLUSIVE if a meter or ≥30% of sensors are unhealthy or 72 h pass, and a returned llr trace (for the dashboard meter).

## Tests (`tests/test_engine.py`)
Use seeded statistical tests with small loops (keep the total test time under about 3 minutes; mark slow ones with `@pytest.mark.slow`).
- **Detection:** on 10 leak-free cities, at most 1 false alarm; 20 L/s leaks detected ≥ 9/10.
- **Skeptic:** 10 cases each.
  - pump trip dismissed as operation ≥ 8/10
  - stuck sensor → sensor_fault ≥ 8/10
  - a real 20 L/s leak stays a leak ≥ 8/10
- **Localisation:** 20 leaks of 20 L/s with 3 days of data; correct zone ≥ 85%; the leak is inside the first 3 planned areas ≥ 65%.
- **Acoustic:** empirical rates close to 0.85 and 0.05 over 2,000 draws.
- **Auditor:** 10 cases each; correct repair → FIXED ≥ 9/10; wrong repair → NOT_FIXED ≥ 9/10; 1 of 2 leaks fixed → PARTLY_FIXED or NOT_FIXED 10/10 (never FIXED); median decision hours reported.
- Unit tests for the maths (soft elimination, the SPRT threshold sign, common-mode removal).

Also add `scripts/engine_report.py`, which prints a small table of those metrics (a 40-case version). We'll quote it in the 10 PM review.

Run until green, then commit `stage 2: physics engine`. Print the metrics table and known gaps. Stop after Stage 2.
