"""field-mcp tools: real-world actions (simulated endpoints). Only these may touch the hidden truth."""
from __future__ import annotations

from typing import Literal, Optional

from neer import config
from neer.engine.acoustic import acoustic_check as _acoustic
from neer.schemas import AcousticResult, CrewStatus, SearchArea, WorkOrder
from neer.tools import chaos
from neer.engine.plan import survey_hours
from neer.tools.resilience import resilient_tool
from neer.tools.safety import check_physical_action
from neer.tools.world import session


def _area(w, case_id: str, area_id: str) -> list[str]:
    if case_id not in w.cases:
        raise ValueError(f"unknown case {case_id}")
    c = w.cases[case_id]
    if area_id not in c.areas:
        raise ValueError(f"area {area_id} is not in this case's plan; call plan_search_areas first")
    return c.areas[area_id]


@resilient_tool("field")
def acoustic_check(case_id: str, area_id: str) -> AcousticResult:
    """Place acoustic loggers in the area overnight. 'yes' = leak noise heard (85 % sensitive, 5 % false alarms);
    'inconclusive' = too noisy to tell (5 %). A 'no' lowers that area's likelihood but never to zero."""
    with session() as w:
        junctions = _area(w, case_id, area_id)
        truth = [l.node for l in w.city.truth()]
        forced = chaos.consume("crew_finds_nothing")
        res = _acoustic(SearchArea(area_id=area_id, junctions=junctions, likelihood=0, pipe_km=0), truth, w.rng,
                        force_no=forced)
        w.kpi["acoustic_checks"] += 1
        w.kpi["crew_hours"] = round(w.kpi.get("crew_hours", 0) + survey_hours(w.city.net.area_pipe_km(area_id[2:])), 2)
        c = w.cases[case_id]
        if res.result == "no":
            c.weights.acoustic_no(junctions)
        elif res.result == "yes":
            c.acoustic_yes.add(area_id)
        return res


@resilient_tool("field")
def create_work_order(case_id: str, area_id: str, action: Literal["acoustic", "dig", "repair"],
                      approved_by: Optional[str] = None, approver_role: Optional[str] = None) -> WorkOrder:
    """Create a crew work order. Idempotent: repeating the same request while it is open returns the same order.
    A dig passes the safety validator: acoustic 'yes' in that area + a named approver whose role is
    supervisor or engineer + no other open dig on the case."""
    with session() as w:
        _area(w, case_id, area_id)
        key = f"{case_id}|{area_id}|{action}"
        if key in w.idempotency and w.work_orders[w.idempotency[key]].status == "open":
            return w.work_orders[w.idempotency[key]]        # same request again -> same open order
        if action in ("dig", "repair"):
            check_physical_action(w, case_id, area_id, action, approved_by, approver_role)
        wo = WorkOrder(work_order_id=f"WO-{len(w.work_orders) + 1:03d}", case_id=case_id, area_id=area_id,
                       action=action, approved_by=approved_by if action != "acoustic" else None,
                       approver_role=approver_role if action != "acoustic" else None)
        w.work_orders[wo.work_order_id] = wo
        w.idempotency[key] = wo.work_order_id
        return wo


@resilient_tool("field")
def crew_status(work_order_id: str) -> CrewStatus:
    """What the crew reports. For a dig: 'repaired' if they found and fixed a leak, else 'nothing_found'.
    (Crews can be wrong - that is why the Auditor never trusts this report.)"""
    with session() as w:
        if work_order_id not in w.work_orders:
            raise ValueError(f"unknown work order {work_order_id}")
        wo = w.work_orders[work_order_id]
        if wo.status == "done":
            return CrewStatus(work_order_id=work_order_id, status="done", result=wo.result)
        c = w.cases[wo.case_id]
        junctions = c.areas[wo.area_id]
        if wo.action == "acoustic":
            wo.status, wo.result = "done", None
            return CrewStatus(work_order_id=work_order_id, status="done")
        w.kpi["digs"] += 1
        w.kpi["crew_hours"] = round(w.kpi.get("crew_hours", 0) + config.DIG_HOURS, 2)
        found = [l.node for l in w.city.truth() if l.node in junctions]
        if found:
            if w.misfix_remaining > 0:        # scenario: crew fixes the wrong pipe but reports success
                w.misfix_remaining -= 1
            else:
                for n in found:
                    w.city.remove_leak(n)
            wo.result = "repaired"
            c.repair_day = w.city.day
            c.last_dig_area = wo.area_id
        else:
            w.kpi["wasted_digs"] += 1
            c.weights.empty_dig(junctions)
            wo.result = "nothing_found"
        wo.status = "done"
        return CrewStatus(work_order_id=work_order_id, status="done", result=wo.result)


@resilient_tool("field")
def notify_residents(area_id: str, message: str, lang: Literal["en", "ta"] = "en") -> dict:
    """Send an SMS to households in the area (simulated gateway)."""
    if len(message) > 480:
        raise ValueError("message too long for SMS (max 480 characters)")
    homes = 40 * max(1, len(area_id))
    return {"area_id": area_id, "lang": lang, "homes_notified": homes, "message": message}


@resilient_tool("field")
def slow_refill_instruction(work_order_id: str) -> dict:
    """Tell the crew to reopen valves slowly after a repair, so the pressure surge does not burst a nearby pipe."""
    with session(write=False) as w:
        if work_order_id not in w.work_orders:
            raise ValueError(f"unknown work order {work_order_id}")
    return {"work_order_id": work_order_id, "acknowledged": True,
            "instruction": "Reopen isolation valves over at least 10 minutes; watch nearby pressure for 1 hour."}
