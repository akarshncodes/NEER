"""audit-mcp tools: independent proof of repair, contractor sign-off, memory and KPIs."""
from __future__ import annotations

from typing import Literal, Optional

from neer import config
from neer.engine.audit import sequential_verify
from neer.schemas import AuditKind, AuditVerdict
from neer.tools.resilience import resilient_tool
from neer.tools.world import session


@resilient_tool("audit", timeout_s=30)
def verify_repair(case_id: str) -> AuditVerdict:
    """Prove the repair from zone meter data only, hour by hour (never from the crew's report).
    Watches up to 3 days; returns FIXED / PARTLY_FIXED / NOT_FIXED / INCONCLUSIVE with the evidence trace."""
    with session() as w:
        if case_id not in w.cases:
            raise ValueError(f"unknown case {case_id}")
        c = w.cases[case_id]
        if c.repair_day is None:
            raise ValueError("no repair recorded for this case yet")
        unhealthy = len(c.masked) / len(w.city.net.sensors)
        after = []
        verdict = None
        for _ in range(3):
            after.append(w.advance_day())
            verdict = sequential_verify(w.baseline, after, c.zone_idx, c.pre_excess, unhealthy)
            if verdict.verdict != AuditKind.inconclusive:
                break
        c.last_verdict = verdict
        if verdict.verdict == AuditKind.fixed:
            w.kpi["repairs_verified"] += 1
            w.kpi["litres_saved_per_day"] += round(c.pre_excess * 86400)      # L/s -> litres per day
            for d in after:                     # the network is proven clean: learn "normal" from it
                w.baseline.add_certified_clean(d)
        elif verdict.verdict in (AuditKind.not_fixed, AuditKind.partly_fixed):
            w.kpi["repairs_rejected"] += 1
            if verdict.verdict == AuditKind.partly_fixed:
                c.pre_excess = max(verdict.post_excess_lps, 1.0)     # hunt what is left
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
        return {"key": key, "value": w.memory.get(key)}


@resilient_tool("audit")
def kpi_report() -> dict:
    """Operational KPIs so far: cases, false alarms avoided, digs, wasted digs, verified repairs, water saved."""
    with session(write=False) as w:
        return dict(w.kpi)
