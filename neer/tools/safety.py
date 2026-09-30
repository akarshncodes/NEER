"""Safety validator: the last gate between an agent's recommendation and any physical action.

Every excavation / repair order passes through `check_physical_action`, whatever the agent,
LLM or MCP client asked for:
  1. listen before you dig   - an acoustic 'yes' in that exact area,
  2. a named human approver  - no anonymous approvals,
  3. role-based access       - only roles in config.APPROVER_ROLES may approve,
  4. one open dig per case   - no parallel excavations from a confused plan.
SCADA is read-only in NEER: no tool writes to pumps or valves.
Every approval and every refusal is written to the trace.
"""
from __future__ import annotations

from typing import Optional

from neer import config
from neer.tools.resilience import _trace, current_agent


def check_physical_action(world, case_id: str, area_id: str, action: str,
                          approved_by: Optional[str], approver_role: Optional[str]) -> None:
    """Raise PermissionError (with a plain reason) if the action is not allowed."""
    c = world.cases[case_id]
    reason = None
    if area_id not in c.acoustic_yes:
        reason = "No dig without an acoustic 'yes' in this area (listen before you dig)."
    elif not approved_by:
        reason = "A dig needs a named human approver (approved_by)."
    elif (approver_role or "").lower() not in config.APPROVER_ROLES:
        reason = (f"Role '{approver_role}' may not approve physical work; "
                  f"allowed: {', '.join(config.APPROVER_ROLES)}.")
    elif any(wo.case_id == case_id and wo.action in ("dig", "repair") and wo.status == "open"
             for wo in world.work_orders.values()):
        reason = "This case already has an open excavation."
    if reason:
        world.kpi["refused_actions"] = world.kpi.get("refused_actions", 0) + 1
        _trace(current_agent.get(), "safety_validator", {"case": case_id, "area": area_id, "action": action},
               False, f"REFUSED: {reason}", 0)
        raise PermissionError(reason)
    _trace(current_agent.get(), "safety_validator", {"case": case_id, "area": area_id, "action": action},
           True, f"APPROVED by {approved_by} ({approver_role})", 0)
