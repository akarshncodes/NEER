"""The six NEER agents as LangGraph nodes.

Loop: SUSPECT (Sentinel) -> QUESTION (Skeptic) -> INVESTIGATE (Detective, Orchestrator)
      -> ACT (human-approved field work) -> VERIFY (Auditor) -> REPLAN.

Pattern in every node:  call tools  ->  (optionally) ask the LLM to choose from an allowed set
->  apply the deterministic guard  ->  write a timeline entry + evidence-ledger rows.
Numbers only ever come from tools. The Sentinel is a deterministic data monitor (no LLM).
"""
from __future__ import annotations

from langgraph.types import interrupt

from neer import config
from neer.agents import prompts
from neer.agents.llm import decide
from neer.agents.state import CaseState, TimelineEntry
from neer.agents.toolbox import call
from neer.tools.resilience import is_error


def T(agent: str, text: str, kind: str = "info", provider: str | None = None, **numbers) -> dict:
    """One line in the case timeline (stored as a plain dict so checkpoints stay portable)."""
    return TimelineEntry(agent=agent, text=text, kind=kind, provider=provider, numbers=numbers).model_dump()


def L(dimension: str, finding: str, supports: str, reliability: str, source: str, when: str = "") -> dict:
    """One evidence-ledger row: what was found, which way it points, how reliable, which tool, when."""
    return {"when": when, "dimension": dimension, "finding": finding, "supports": supports,
            "reliability": reliability, "source": source}


def _provider_note(d) -> str:
    return d.provider + (f" (after: {'; '.join(d.fallbacks)})" if d.fallbacks else "")


# ============================================================ 1. SENTINEL
def sentinel(s: CaseState) -> dict:
    zf = call("Sentinel", "get_zone_flow", days=1)
    window = 1
    for days in (2, 3):
        # slow-leak check: a small leak hides in one day of noise but adds up over several days
        if is_error(zf) or zf["detection"]["alarm"]:
            break
        longer = call("Sentinel", "get_zone_flow", days=days)
        if not is_error(longer) and longer["detection"]["alarm"]:
            zf, window = longer, days
    if is_error(zf):
        return {"status": "watch", "last_event": "inconclusive",
                "timeline": [T("Sentinel", f"SCADA unavailable ({zf['message']}). Degraded mode: watching, "
                                           "no decision without data.", "alert")]}
    d = zf["detection"]
    worst = max(zf["zones"], key=lambda z: z["t_score"])
    if not d["alarm"]:
        return {"status": "no_alarm", "tier": "NONE",
                "timeline": [T("Sentinel", f"All zones normal (largest t = {worst['t_score']}). No case.", "info")]}
    names = {"water": "mass balance", "pressure": "hydraulic response", "persistence": "temporal persistence"}
    present = [names[w] for w in ("water", "pressure", "persistence") if d[w]]
    slow = f" (slow leak: visible over {window} days)" if window > 1 else ""
    when = f"Day {zf['day']}"
    ledger = [
        L("Mass balance", f"Zone {worst['zone']} inflow {worst['excess_lps']:+.1f} L/s vs baseline (t = {worst['t_score']})",
          "leak" if d["water"] else "neutral", "high" if worst["t_score"] > 10 else "medium", "get_zone_flow", when),
        L("Hydraulic response", f"Pressure anomaly score {d['pressure_score']}",
          "leak" if d["pressure"] else "neutral", "medium", "get_zone_flow", when),
        L("Temporal persistence", "Still present in hours 18-23" if d["persistence"] else "Not present late in the day",
          "leak" if d["persistence"] else "against", "medium", "get_zone_flow", when),
    ]
    return {"tier": d["tier"], "zone": worst["zone"], "window_days": window, "status": "open",
            "alarm_excess_lps": worst["excess_lps"], "sim_day": zf["day"], "ledger": ledger,
            "timeline": [T("Sentinel",
                           f"Alarm{slow}, tier {d['tier']}. Evidence: {', '.join(present)}. "
                           f"Zone {worst['zone']} takes {worst['excess_lps']:+.1f} L/s vs normal (t = {worst['t_score']}); "
                           f"pressure score {d['pressure_score']}.", "alert",
                           excess_lps=worst["excess_lps"], t=worst["t_score"])]}


# ============================================================ 2. SKEPTIC (gate)
def skeptic_gate(s: CaseState) -> dict:
    health = call("Skeptic", "sensor_health")
    ops = call("Skeptic", "get_ops_log", days=s.window_days)
    cal = call("Skeptic", "get_supply_calendar", days=s.window_days)
    v = call("Skeptic", "replay_operation", days=s.window_days)
    if is_error(v):
        return {"status": "watch", "timeline": [T("Skeptic", f"Could not run checks ({v['message']}); watching.", "alert")]}
    bad = [x["sensor"] for x in health.get("sensors", []) if x["status"] != "ok"] if not is_error(health) else []
    situation = (f"Alarm tier {s.tier} in zone {s.zone}. Sensor problems: {bad or 'none'}. "
                 f"Ops log today: {[o['detail'] for o in ops] if not is_error(ops) else 'unavailable'}. "
                 f"Calendar: {[c['detail'] for c in cal] if not is_error(cal) else 'unavailable'}. "
                 f"Twin replay verdict: {v['verdict']} - {v['reason']}")
    engine_says_leak = v["verdict"] == "leak"
    when = f"Day {s.sim_day}"
    ledger = [L("Operational context", v["reason"], "leak" if engine_says_leak else "against", "high",
                "replay_operation", when)]
    if bad:
        ledger.append(L("Sensor health", f"Unhealthy sensors masked: {', '.join(bad)}", "neutral", "high",
                        "sensor_health", when))
    small = engine_says_leak and s.alarm_excess_lps < config.MIN_ACTIONABLE_LPS and s.waits < config.MAX_WAIT_DAYS
    if small:
        allowed = ["wait_more_data", "open_case"]
        rules = lambda: ("wait_more_data", f"Only {s.alarm_excess_lps:+.1f} L/s - too small to send a crew on one "
                                           "window of data. Collect another day first.")
    elif engine_says_leak:
        allowed, rules = ["open_case"], lambda: ("open_case", v["reason"])
    else:
        allowed, rules = ["dismiss", "open_case"], lambda: ("dismiss", v["reason"])
    d = decide("Skeptic", prompts.SKEPTIC_GATE, situation + f" Raw excess before explaining: {s.alarm_excess_lps} L/s.",
               allowed, rules)
    if d.choice == "wait_more_data":
        return {"status": "waiting", "skeptic_verdict": v["verdict"], "ledger": ledger,
                "timeline": [T("Skeptic", f"Wait: {d.reason}", "decision", _provider_note(d))]}
    if d.choice == "dismiss":
        call("Skeptic", "case_memory", op="write", key=f"false_alarm:{s.case_id}", value=v["reason"])
        return {"status": "watch", "skeptic_verdict": v["verdict"], "skeptic_reason": v["reason"], "ledger": ledger,
                "timeline": [T("Skeptic", f"Dismissed ({v['verdict']}): {d.reason} Put on WATCH, re-check tomorrow.",
                               "decision", _provider_note(d))]}
    return {"skeptic_verdict": v["verdict"], "skeptic_reason": v["reason"], "ledger": ledger,
            "timeline": [T("Skeptic", f"Could not explain it away: {d.reason} Case opened.", "decision",
                           _provider_note(d))]}


# ============================================================ 3. DETECTIVE
def detective(s: CaseState) -> dict:
    # after a repair, only post-repair data describes the leak that is left
    days = 1 if s.last_event in ("partly", "not_fixed") else 2
    loc = call("Detective", "locate_leak", case_id=s.case_id, days=days)
    if is_error(loc):
        return {"last_event": "inconclusive", "timeline": [T("Detective", f"Localisation failed: {loc['message']}", "alert")]}
    size = call("Detective", "estimate_leak_size", zone=loc["zone"], days=days)
    pm = f" ± {size['plus_minus_lps']}" if not is_error(size) else ""
    areas = ", ".join(f"{a['area_id']} {a['likelihood']:.0%}" for a in loc["areas"])
    event = "located" if s.last_event in ("start", "located") else s.last_event
    return {"zone": loc["zone"], "leak_size_lps": loc["leak_size_lps"], "areas": loc["areas"],
            "evidence": loc["evidence"], "last_event": event,
            "ledger": [L("Hydraulic localisation", f"Zone {loc['zone']}, ≈{loc['leak_size_lps']}{pm} L/s; relative "
                                                   f"likelihood {areas}", "leak", "medium (simulated, uncalibrated)",
                         "locate_leak", f"Day {s.sim_day}")],
            "timeline": [T("Detective", f"Zone {loc['zone']}, leak ≈ {loc['leak_size_lps']}{pm} L/s. "
                                        f"Relative likelihood: {areas}.", "info", leak_lps=loc["leak_size_lps"])]}


# ============================================================ 4. ORCHESTRATOR
def orchestrator(s: CaseState) -> dict:
    over_budget = (s.visits - s.round_start_visits >= config.MAX_VISITS
                   or s.replans - s.round_start_replans > config.MAX_REPLANS)
    if over_budget and s.last_event != "acoustic_yes":      # never abandon a confirmed acoustic hit
        return {"next_action": "escalate",
                "timeline": [T("Orchestrator", f"Budget used ({s.visits - s.round_start_visits} visits this round, "
                                               f"{s.replans - s.round_start_replans} re-plans). "
                                               "Escalating to the supervisor with a summary.", "decision")]}
    if s.last_event == "dig_rejected":
        return {"next_action": "escalate",
                "timeline": [T("Orchestrator", "The dig was refused (no valid approval). Escalating to a supervisor "
                                               "instead of working around the safety gate.", "decision")]}
    areas = call("Orchestrator", "plan_search_areas", case_id=s.case_id, n=3)
    if is_error(areas):
        return {"next_action": "escalate", "timeline": [T("Orchestrator", f"Cannot plan: {areas['message']}", "alert")]}
    top = areas[0]
    if s.last_event == "acoustic_inconclusive" and s.current_area:
        allowed = ["acoustic_check", "escalate"]
        target = s.current_area
        rules = lambda: ("acoustic_check", f"The survey in {target} was inconclusive (noise); repeat it before moving on.")
    elif s.last_event == "acoustic_yes":
        allowed = ["request_dig", "acoustic_check"]
        rules = lambda: ("request_dig", f"Acoustic loggers heard leak noise in {s.current_area}; dig there.")
        target = s.current_area
    else:
        allowed = ["acoustic_check", "escalate"]
        why = {"acoustic_no": "The last area was quiet, so its likelihood dropped.",
               "dig_empty": "The dig found nothing there, so that area is down-weighted.",
               "not_fixed": "The Auditor proved the leak is still running.",
               "partly": "One leak fixed; hunting what is left."}.get(s.last_event, "")
        if s.last_event == "not_fixed" and s.current_area:
            # the repair did not hold: most often the crew fixed a different pipe nearby - re-listen there first
            target = s.current_area
            rules = lambda: ("acoustic_check", f"{why} Re-listen at the repair site {target} first: "
                                               "a wrong pipe nearby is the most common cause.")
        else:
            target = top["area_id"]
            rules = lambda: ("acoustic_check", f"{why} Next-best action: acoustic survey of {top['area_id']} "
                                               f"(likelihood {top['likelihood']:.0%}, information gain {top['info_gain']:.2f}, "
                                               f"{top['cost_hours']} crew-h, value {top['action_value']:.2f}).".strip())
    situation = (f"Case {s.case_id}, zone {s.zone}, leak ≈ {s.leak_size_lps} L/s. Last event: {s.last_event}. "
                 f"Visits {s.visits}/{config.MAX_VISITS}, re-plans {s.replans}/{config.MAX_REPLANS}. "
                 f"Candidate acoustic surveys ranked by next-best-action value "
                 f"(chance of finding + 0.3 x information gain; crew-hours shown): "
                 f"{[(a['area_id'], a['likelihood'], a['info_gain'], a['cost_hours'], a['action_value']) for a in areas]}. "
                 f"Current area: {s.current_area}.")
    d = decide("Orchestrator", prompts.ORCHESTRATOR, situation, allowed, rules)
    if d.choice == "acoustic_check" and s.last_event == "acoustic_yes":
        target = s.current_area
    replanned = s.last_event in ("acoustic_no", "dig_empty", "not_fixed", "partly", "acoustic_inconclusive")
    return {"next_action": d.choice, "current_area": target, "areas": areas, "plan_reason": d.reason,
            "replans": s.replans + (1 if replanned else 0),
            "timeline": [T("Orchestrator", f"{'Re-plan: ' if replanned else 'Plan: '}{d.choice} in {target}. {d.reason}",
                           "decision", _provider_note(d))]}


# ============================================================ 5. SKEPTIC (plan review = critic)
def skeptic_review(s: CaseState) -> dict:
    top = s.areas[0] if s.areas else None
    weak = top is None or s.leak_size_lps < 1.0
    allowed = ["approve_plan", "send_back"] if s.review_sendbacks < 1 else ["approve_plan"]
    situation = (f"Plan: {s.next_action} in {s.current_area}. Reason: {s.plan_reason} "
                 f"Top area relative likelihood {top['likelihood'] if top else 0:.2f}. Leak size {s.leak_size_lps} L/s. "
                 f"Skeptic gate verdict: {s.skeptic_verdict}.")
    d = decide("Skeptic", prompts.SKEPTIC_REVIEW, situation, allowed,
               rules=lambda: ("send_back", "Evidence too weak for a field visit.") if weak and "send_back" in allowed
               else ("approve_plan", "Plan picks the best-value survey and listens before any dig."))
    if d.choice == "send_back":
        return {"review_sendbacks": s.review_sendbacks + 1, "plan_reviewed": False,
                "timeline": [T("Skeptic", f"Plan sent back: {d.reason}", "decision", _provider_note(d))]}
    return {"plan_reviewed": True, "timeline": [T("Skeptic", f"Plan approved for the supervisor: {d.reason}", "decision",
                                                  _provider_note(d))]}


# ============================================================ human gates (LangGraph interrupts)
def approve_plan(s: CaseState) -> dict:
    answer = interrupt({"type": "approve_plan", "case_id": s.case_id, "zone": s.zone, "area": s.current_area,
                        "action": s.next_action, "reason": s.plan_reason, "evidence": s.evidence, "areas": s.areas})
    ok = bool(answer.get("approved"))
    return {"plan_approved": ok, "status": "open" if ok else "escalated",
            "timeline": [T("Supervisor", f"Plan {'approved' if ok else 'rejected'} by {answer.get('by', 'supervisor')}.",
                           "human")]}


def approve_dig(s: CaseState) -> dict:
    answer = interrupt({"type": "approve_dig", "case_id": s.case_id, "area": s.current_area,
                        "reason": s.plan_reason})
    ok = bool(answer.get("approved"))
    who, role = answer.get("by", "Supervisor"), answer.get("role", "supervisor")
    return {"next_action": "dig" if ok else "rejected", "last_event": s.last_event if ok else "dig_rejected",
            "dig_approver": who if ok else None, "dig_approver_role": role if ok else None,
            "timeline": [T("Supervisor", f"Dig in {s.current_area} {'approved' if ok else 'rejected'} "
                                         f"by {who} ({role}).", "human")]}


# ============================================================ 6. FIELD COMMANDER
def field_commander(s: CaseState) -> dict:
    area = s.current_area
    if s.next_action == "acoustic_check":
        call("Field Commander", "create_work_order", case_id=s.case_id, area_id=area, action="acoustic")
        r = call("Field Commander", "acoustic_check", case_id=s.case_id, area_id=area)
        if is_error(r):
            return {"last_event": "acoustic_no", "visits": s.visits + 1,
                    "timeline": [T("Field Commander", f"Acoustic check failed ({r['message']}); treating as no.", "alert")]}
        res = r["result"]
        text = {"yes": "LEAK NOISE HEARD", "no": "quiet - no dig",
                "inconclusive": "INCONCLUSIVE (too noisy to tell) - no dig"}[res]
        event = {"yes": "acoustic_yes", "no": "acoustic_no", "inconclusive": "acoustic_inconclusive"}[res]
        return {"last_event": event, "visits": s.visits + 1,
                "ledger": [L("Field evidence", f"Acoustic survey {area}: {res}",
                             {"yes": "leak", "no": "against", "inconclusive": "neutral"}[res],
                             "85% sensitive, 5% false alarm", "acoustic_check", f"Day {s.sim_day}")],
                "timeline": [T("Field Commander", f"Acoustic loggers in {area} overnight: {text}.", "action")]}
    # dig (already approved by a human)
    wo = call("Field Commander", "create_work_order", case_id=s.case_id, area_id=area, action="dig",
              approved_by=s.dig_approver, approver_role=s.dig_approver_role)
    if is_error(wo):
        return {"last_event": "dig_rejected", "timeline": [T("Field Commander", f"Dig refused: {wo['message']}", "alert")]}
    sms = call("Field Commander", "notify_residents", area_id=area, lang="ta",
               message=f"NEER: water repair work in your street ({area}) today. Supply may be low for 2-3 hours. "
                       "உங்கள் தெருவில் இன்று குழாய் பழுது நீக்கும் பணி.")
    st = call("Field Commander", "crew_status", work_order_id=wo["work_order_id"])
    if st.get("result") == "repaired":
        call("Field Commander", "slow_refill_instruction", work_order_id=wo["work_order_id"])
        return {"work_order": wo["work_order_id"], "last_event": "repaired",
                "ledger": [L("Field evidence", f"Crew report: repaired in {area} (a claim - not proof)", "neutral",
                             "low (unverified)", "crew_status", f"Day {s.sim_day}")],
                "timeline": [T("Field Commander", f"{wo['work_order_id']}: crew reports leak repaired in {area}. "
                                                  f"{sms.get('homes_notified', 0)} homes texted; slow refill ordered "
                                                  "(avoids a pressure-surge burst).", "action")]}
    return {"work_order": wo["work_order_id"], "last_event": "dig_empty",
            "timeline": [T("Field Commander", f"{wo['work_order_id']}: dig in {area} found nothing.", "alert")]}


# ============================================================ 7. AUDITOR
def auditor(s: CaseState) -> dict:
    v = call("Auditor", "verify_repair", case_id=s.case_id)
    if is_error(v):
        return {"verdict": "INCONCLUSIVE", "last_event": "inconclusive",
                "inconclusive_waits": s.inconclusive_waits + 1,
                "timeline": [T("Auditor", f"Cannot verify yet: {v['message']}", "alert")]}
    out = {"verdict": v["verdict"], "verdict_reason": v["reason"], "llr_trace": v["llr_trace"],
           "ledger": [L("Independent audit", f"{v['verdict']}: {v['reason']}",
                        {"FIXED": "fixed", "PARTLY_FIXED": "leak", "NOT_FIXED": "leak"}.get(v["verdict"], "neutral"),
                        "high (99:1 / 999:1 sequential test)", "verify_repair",
                        f"+{v['hours_used']} h after repair")]}
    if v["verdict"] == "FIXED":
        rel = call("Auditor", "release_contractor", work_order_id=s.work_order)
        kpi = call("Auditor", "kpi_report")
        saved = kpi.get("litres_saved_per_day", 0) if not is_error(kpi) else 0
        out.update(status="closed", contractor=rel.get("decision"),
                   timeline=[T("Auditor", f"FIXED - {v['reason']} Contractor {rel.get('decision')}. "
                                          f"Water saved ≈ {saved / 1000:,.0f} m³/day.", "verdict")])
    elif v["verdict"] in ("NOT_FIXED", "PARTLY_FIXED"):
        rel = call("Auditor", "release_contractor", work_order_id=s.work_order)
        out.update(contractor=rel.get("decision"), last_event="partly" if v["verdict"] == "PARTLY_FIXED" else "not_fixed",
                   round_start_visits=s.visits, round_start_replans=s.replans,
                   timeline=[T("Auditor", f"{v['verdict'].replace('_', ' ')} - {v['reason']} "
                                          f"Contractor payment {rel.get('decision')}. Case reopened.", "verdict")])
    else:
        out.update(last_event="inconclusive", inconclusive_waits=s.inconclusive_waits + 1,
                   timeline=[T("Auditor", f"INCONCLUSIVE - {v['reason']}", "verdict")])
    return out


# ============================================================ waiting for more evidence
def wait_day(s: CaseState) -> dict:
    """Let one more day of SCADA data arrive (the simulation clock), then the Sentinel looks again."""
    from neer.tools.world import session
    with session() as w:
        d = w.advance_day()
    return {"waits": s.waits + 1, "status": "open",
            "timeline": [T("Orchestrator", f"Waited for day {d.day}'s data before deciding (wait {s.waits + 1}/"
                                           f"{config.MAX_WAIT_DAYS}).", "info")]}


# ============================================================ terminal nodes
def escalate(s: CaseState) -> dict:
    return {"status": "escalated", "timeline": [T("Orchestrator", "Escalated to the supervisor: automatic budget "
                                                                  "used up. Summary and evidence attached.", "alert")]}


def watch(s: CaseState) -> dict:
    return {"status": "watch"}
