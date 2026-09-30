"""audit-mcp tools: independent proof of repair, contractor sign-off, memory and KPIs."""
from __future__ import annotations

from typing import Literal, Optional

import numpy as np

from neer import config
from neer.engine.audit import sequential_verify
from neer.schemas import AuditKind, AuditVerdict
from neer.tools.resilience import resilient_tool
from neer.tools.world import session


@resilient_tool("audit", timeout_s=30)
def verify_repair(case_id: str) -> AuditVerdict:
    """Prove the repair from meter data only, hour by hour. The Auditor is INDEPENDENT: it never reads the crew's
    report and never uses the Detective's conclusion - it measures the pre-repair loss itself from SCADA, picks the
    zone that was losing water, then tests the post-repair hours. Watches up to 3 days; returns
    FIXED / PARTLY_FIXED / NOT_FIXED / INCONCLUSIVE with the evidence trace."""
    with session() as w:
        if case_id not in w.cases:
            raise ValueError(f"unknown case {case_id}")
        c = w.cases[case_id]
        if c.repair_day is None:
            raise ValueError("no repair recorded for this case yet")
        net, b = w.city.net, w.baseline
        # --- the Auditor's own pre-repair measurement (last 2 days before the repair)
        # the stronger of the last-day and last-2-days windows: a leak found on its first night has only one
        # day of loss behind it, and averaging in the clean day before would halve it
        hist = [d for d in w.city.history if d.day < c.repair_day]
        windows = [hist[-1:], hist[-2:]]
        before = max(windows, key=lambda ds: float(b.zone_t(ds).max()))
        t_pre, ex_pre = b.zone_t(before), b.zone_excess(before)
        zi = int(np.argmax(t_pre))
        if t_pre[zi] < config.Z_THR:
            verdict = AuditVerdict(verdict=AuditKind.inconclusive, hours_used=0, llr_trace=[], pre_excess_lps=0.0,
                                   post_excess_lps=0.0, reason="No clear pre-repair water loss to verify against.")
        else:
            unhealthy = len(c.masked) / len(net.sensors)
            after = []
            verdict = None
            for _ in range(3):
                after.append(w.advance_day())
                verdict = sequential_verify(b, after, zi, float(ex_pre[zi]), unhealthy)
                if verdict.verdict != AuditKind.inconclusive:
                    break
            verdict.reason = f"[{net.zone_names[zi]}, own meter reading] " + verdict.reason
        c.last_verdict = verdict
        c.audit_zone = net.zone_names[zi]
        if verdict.verdict == AuditKind.fixed:
            w.kpi["repairs_verified"] += 1
            w.kpi["litres_saved_per_day"] += round(verdict.pre_excess_lps * 86400)      # L/s -> litres per day
            for d in after:          # proven clean: queue for the protected baseline (needs >= 2 certified days)
                if b.add_certified_clean(d):
                    w.kpi["baseline_updates"] = w.kpi.get("baseline_updates", 0) + 1
        elif verdict.verdict in (AuditKind.not_fixed, AuditKind.partly_fixed):
            w.kpi["repairs_rejected"] += 1
            if verdict.verdict == AuditKind.not_fixed and c.last_dig_area in c.areas:   # repaired there, still leaking
                c.weights.downweight(c.areas[c.last_dig_area], config.SOFT_NOT_FIXED)
            c.repair_day = None
        return verdict


@resilient_tool("audit")
def release_contractor(work_order_id: str) -> dict:
    """Release the contractor's payment/sign-off ONLY if the Auditor's verdict for the case is FIXED; otherwise hold."""
    with session() as w:
        if work_order_id not in w.work_orders:
            raise ValueError(f"unknown work order {work_order_id}")
        wo = w.work_orders[work_order_id]
        v = w.cases[wo.case_id].last_verdict
        if v is not None and v.verdict == AuditKind.fixed:
            return {"work_order_id": work_order_id, "decision": "released", "reason": v.reason}
        w.kpi["contractors_held"] += 1
        why = v.reason if v else "no verified repair yet"
        return {"work_order_id": work_order_id, "decision": "held", "reason": why}


@resilient_tool("audit")
def case_memory(op: Literal["read", "write"], key: str, value: Optional[str] = None) -> dict:
    """Long-term memory (past false alarms, lessons). Read or write a short note by key."""
    with session() as w:
        if op == "write":
            if value is None:
                raise ValueError("value is required for write")
            w.memory[key] = value[:500]
            if key.startswith("false_alarm"):
                w.kpi["false_alarms_avoided"] += 1
        return {"key": key, "value": w.memory.get(key)}


@resilient_tool("audit")
def kpi_report() -> dict:
    """Operational KPIs so far: cases, false alarms avoided, digs, wasted digs, verified repairs, water saved."""
    with session(write=False) as w:
        k = dict(w.kpi)
        k["baseline"] = w.baseline.info()
        return k
