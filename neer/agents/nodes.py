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
from neer.agents import llm as llm_mod
from neer.agents import prompts
from neer.agents.llm import DecisionResult, GateAnswer, InterpretAnswer, PlanAnswer, decide
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


def AI(agent: str, d: DecisionResult, guard: str = "accepted", when: str = "") -> tuple[dict, dict]:
    """Audit trail of one AI decision: (numbers for the timeline entry, evidence-ledger row).

    Records who answered, what they chose, what `rules()` would have chosen, what the guard did and what was cited.
    """
    cited = "; ".join(d.cites) if d.cites else "nothing quoted"
    vetoed = guard.startswith("vetoed")
    row = L("AI decision",
            f"{agent} chose '{d.choice}'; rules default '{d.rules_choice}'; guard: {guard}; cited: {cited}",
            "vetoed by rule" if vetoed else "neutral", "model judgment, checked by a rule guard"
            if d.provider != "rules" else "deterministic rules", d.provider, when)
    return dict(ai_choice=d.choice, rules_default=d.rules_choice, guard=guard, cited=list(d.cites),
                rejected=d.rejected), row


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
            "alarm_excess_lps": worst["excess_lps"], "alarm_t": worst["t_score"], "sim_day": zf["day"], "ledger": ledger,
            "timeline": [T("Sentinel",
                           f"Alarm{slow}, tier {d['tier']}. Evidence: {', '.join(present)}. "
                           f"Zone {worst['zone']} takes {worst['excess_lps']:+.1f} L/s vs normal (t = {worst['t_score']}); "
                           f"pressure score {d['pressure_score']}.", "alert",
                           excess_lps=worst["excess_lps"], t=worst["t_score"])]}


# ============================================================ 2. SKEPTIC (gate = hypothesis judge)
HYPOTHESES = ["leak", "operation", "planned_work", "sensor_fault", "temporary_demand"]
EVIDENCE_TOOLS = ["replay_operation", "sensor_health", "get_supply_calendar", "get_pressure", "wait_one_day"]
MAX_EXTRA_ROUNDS = 2
_AS_HYPOTHESIS = {"leak": "leak", "operation": "operation", "planned_work": "planned_work",
                  "sensor_fault": "sensor_fault", "temporary": "temporary_demand", "no_alarm": "temporary_demand"}


def _hypothesis_table(s: CaseState, v: dict, bad: list, ops, cal) -> str:
    """The competing explanations, each with what the engine found (all numbers come from tools)."""
    kind = _AS_HYPOTHESIS.get(v["verdict"], "temporary_demand")

    def mark(h: str) -> str:
        return "engine SUPPORTS this" if kind == h else "engine does not support this"
    ops_txt = [o["detail"] for o in ops] if not is_error(ops) and ops else "no operator action logged"
    cal_txt = [c["detail"] for c in cal] if not is_error(cal) and cal else "no planned work in the calendar"
    return "\n".join([
        f"- leak: zone {s.zone} t = {s.alarm_t} (mass-balance threshold {config.Z_THR}), raw excess "
        f"{s.alarm_excess_lps} L/s [{mark('leak')}]",
        f"- operation: {ops_txt} [{mark('operation')}]",
        f"- planned_work: {cal_txt} [{mark('planned_work')}]",
        f"- sensor_fault: {bad or 'all pressure sensors ok'} [{mark('sensor_fault')}]",
        f"- temporary_demand: {v['reason'] if kind == 'temporary_demand' else 'no short-event signature found'} "
        f"[{mark('temporary_demand')}]",
        f"Twin replay verdict: {v['verdict']} - {v['reason']}"])


def _fetch_evidence(name: str, s: CaseState) -> tuple[str, dict | None]:
    """Run one extra evidence tool the Skeptic asked for. Returns (text for the next question, new verdict or None)."""
    if name == "replay_operation":
        r = call("Skeptic", "replay_operation", days=s.window_days)
        return (f"replay_operation: unavailable ({r['message']})", None) if is_error(r) else \
               (f"replay_operation: {r['verdict']} - {r['reason']}", r)
    if name == "sensor_health":
        r = call("Skeptic", "sensor_health")
        bad = [x["sensor"] for x in r.get("sensors", []) if x["status"] != "ok"] if not is_error(r) else None
        return (f"sensor_health: {'unavailable' if bad is None else (bad or 'all sensors ok')}", None)
    if name == "get_supply_calendar":
        r = call("Skeptic", "get_supply_calendar", days=s.window_days)
        return (f"get_supply_calendar: {'unavailable' if is_error(r) else ([c['detail'] for c in r] or 'nothing planned')}", None)
    r = call("Skeptic", "get_pressure", days=s.window_days)                       # get_pressure
    if is_error(r):
        return "get_pressure: unavailable", None
    worst = sorted(r["sensors"], key=lambda x: -x["z_rms"])[:2]
    return (f"get_pressure: anomaly score {r['score']} (threshold {r['threshold']}); most anomalous sensors "
            f"{[(x['sensor'], x['z_rms']) for x in worst]}", None)


def skeptic_gate(s: CaseState) -> dict:
    health = call("Skeptic", "sensor_health")
    ops = call("Skeptic", "get_ops_log", days=s.window_days)
    cal = call("Skeptic", "get_supply_calendar", days=s.window_days)
    v = call("Skeptic", "replay_operation", days=s.window_days)
    if is_error(v):
        return {"status": "watch", "timeline": [T("Skeptic", f"Could not run checks ({v['message']}); watching.", "alert")]}
    bad = [x["sensor"] for x in health.get("sensors", []) if x["status"] != "ok"] if not is_error(health) else []
    when = f"Day {s.sim_day}"
    ledger = [L("Operational context", v["reason"], "leak" if v["verdict"] == "leak" else "against", "high",
                "replay_operation", when)]
    if bad:
        ledger.append(L("Sensor health", f"Unhealthy sensors masked: {', '.join(bad)}", "neutral", "high",
                        "sensor_health", when))
    timeline: list[dict] = []
    gathered: list[str] = []
    rounds = 0
    while True:
        engine_leak = v["verdict"] == "leak"
        can_wait = s.waits < config.MAX_WAIT_DAYS
        small = engine_leak and s.alarm_excess_lps < config.MIN_ACTIONABLE_LPS and can_wait
        allowed = ["open_case", "dismiss"] + (["gather_more"] if rounds < MAX_EXTRA_ROUNDS else [])
        situation = (f"Alarm tier {s.tier} in zone {s.zone}. Competing explanations:\n"
                     f"{_hypothesis_table(s, v, bad, ops, cal)}\n"
                     + (f"Extra evidence gathered so far: {gathered}\n" if gathered else "")
                     + f"Allowed missing_evidence: {[e for e in EVIDENCE_TOOLS if e != 'wait_one_day' or can_wait]}. "
                       f"Extra rounds left: {MAX_EXTRA_ROUNDS - rounds}.")

        def rules(small=small, engine_leak=engine_leak, v=v):
            kind = _AS_HYPOTHESIS.get(v["verdict"], "temporary_demand")
            if small and rounds == 0:
                return ("gather_more", f"Only {s.alarm_excess_lps:+.1f} L/s - too small to send a crew on one window "
                                       "of data. Collect another day first.",
                        {"most_likely": "leak", "missing_evidence": ["wait_one_day"], "cites": [v["reason"]]})
            return (("open_case" if engine_leak else "dismiss"), v["reason"],
                    {"most_likely": kind, "missing_evidence": [], "cites": [v["reason"]]})

        def check(a, can_wait=can_wait):
            if a.most_likely not in HYPOTHESES:
                raise ValueError(f"most_likely {a.most_likely!r} is not a listed hypothesis")
            ok = [e for e in EVIDENCE_TOOLS if e != "wait_one_day" or can_wait]
            if any(m not in ok for m in a.missing_evidence):
                raise ValueError(f"missing_evidence {a.missing_evidence} not in {ok}")
            if a.decision == "gather_more" and not a.missing_evidence:
                raise ValueError("gather_more without naming the missing evidence")

        d = decide("Skeptic", prompts.SKEPTIC_GATE, situation, allowed, rules, schema=GateAnswer,
                   choice_field="decision", check=check)
        nums, row = AI("Skeptic", d, when=when)
        if d.choice == "dismiss" and engine_leak and s.alarm_t > config.Z_THR:     # rule veto: never dismiss a clear leak
            msg = (f"Rule veto: the AI ({d.provider}) wanted to dismiss, but the engine verdict is leak and zone t = "
                   f"{s.alarm_t} is above {config.Z_THR}. Case opened instead.")
            if llm_mod.DECISION_LOG:
                llm_mod.DECISION_LOG[-1].vetoed = True
            nums, row = AI("Skeptic", d, guard="vetoed: dismiss -> open_case", when=when)
            ledger.append(row)
            timeline.append(T("Skeptic", msg, "alert", _provider_note(d), **nums))
            d = DecisionResult("open_case", v["reason"], "rules", d.fallbacks, d.ms, d.rules_choice,
                               {"most_likely": "leak"}, [v["reason"]])
        else:
            ledger.append(row)
        ml = d.extra.get("most_likely", "?")
        if d.choice == "gather_more":
            want = list(d.extra.get("missing_evidence", []))
            timeline.append(T("Skeptic", f"Most likely: {ml}. Needs more evidence ({', '.join(want)}): {d.reason}",
                              "decision", _provider_note(d), **nums))
            rounds += 1
            if "wait_one_day" in want and can_wait:
                return {"status": "waiting", "skeptic_verdict": v["verdict"], "ledger": ledger, "timeline": timeline}
            for name in (w for w in want if w != "wait_one_day"):
                text, newv = _fetch_evidence(name, s)
                gathered.append(text)
                v = newv or v
                ledger.append(L("Operational context", text, "neutral", "high", name, when))
                timeline.append(T("Skeptic", f"Extra check - {text}", "info"))
            continue
        break
    if d.choice == "dismiss":
        call("Skeptic", "case_memory", op="write", key=f"false_alarm:{s.case_id}", value=v["reason"])
        timeline.append(T("Skeptic", f"Dismissed as {ml} ({v['verdict']}): {d.reason} Put on WATCH, re-check tomorrow.",
                          "decision", _provider_note(d), **nums))
        return {"status": "watch", "skeptic_verdict": v["verdict"], "skeptic_reason": v["reason"], "ledger": ledger,
                "timeline": timeline}
    timeline.append(T("Skeptic", f"Most likely: {ml}. Could not explain it away: {d.reason} Case opened.", "decision",
                      _provider_note(d), **nums))
    return {"skeptic_verdict": v["verdict"], "skeptic_reason": v["reason"], "ledger": ledger, "timeline": timeline}


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
    health = call("Detective", "sensor_health")
    bad = [x["sensor"] for x in health.get("sensors", []) if x["status"] != "ok"] if not is_error(health) else None
    ledger = [L("Hydraulic localisation", f"Zone {loc['zone']}, ≈{loc['leak_size_lps']}{pm} L/s; relative "
                                          f"likelihood {areas}", "leak", "medium (simulated, uncalibrated)",
                "locate_leak", f"Day {s.sim_day}")]
    when_ok = s.waits < config.MAX_WAIT_DAYS and not s.detective_waited and s.last_event in ("start", "located")
    top = loc["areas"][0]["likelihood"] if loc["areas"] else 0.0
    situation = (f"Zone {loc['zone']}, leak ≈ {loc['leak_size_lps']}{pm} L/s. Area relative likelihoods: {areas}. "
                 f"Sensor problems: {'unknown' if bad is None else (bad or 'none')}. "
                 f"{'One more day of data may be awaited.' if when_ok else 'No more waiting allowed.'}")
    d = decide("Detective", prompts.DETECTIVE, situation, ["proceed", "gather_more"] if when_ok else ["proceed"],
               lambda: ("proceed", f"Top area holds {top:.0%} of the relative likelihood; map is usable.",
                        {"concentrated": top >= 0.5, "more_data_helps": False, "cites": [f"top area {top:.0%}"]}),
               schema=InterpretAnswer, choice_field="decision", ask_llm=when_ok)
    nums, row = AI("Detective", d, when=f"Day {s.sim_day}")
    ledger.append(row)
    base = {"zone": loc["zone"], "leak_size_lps": loc["leak_size_lps"], "areas": loc["areas"],
            "evidence": loc["evidence"], "last_event": event, "ledger": ledger}
    shape = "concentrated" if d.extra.get("concentrated") else "spread out"
    text = (f"Zone {loc['zone']}, leak ≈ {loc['leak_size_lps']}{pm} L/s. Relative likelihood: {areas}. "
            f"Evidence {shape}: {d.reason}")
    if d.choice == "gather_more":
        return {**base, "status": "waiting", "detective_waited": True,
                "timeline": [T("Detective", text + " Waiting one more day for data.", "decision",
                               _provider_note(d), **nums)]}
    return {**base, "timeline": [T("Detective", text, "decision" if d.provider != "rules" else "info",
                                   _provider_note(d) if d.provider != "rules" else None, leak_lps=loc["leak_size_lps"],
                                   **nums)]}


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
    cands = list(areas)
    if s.current_area and s.current_area not in [a["area_id"] for a in cands]:
        wide = call("Orchestrator", "plan_search_areas", case_id=s.case_id, n=8)     # the current area's own numbers
        cands += [a for a in ([] if is_error(wide) else wide) if a["area_id"] == s.current_area]
    ids = [a["area_id"] for a in cands]
    if s.last_event == "acoustic_inconclusive" and s.current_area:
        allowed = ["acoustic_check", "escalate"]
        target = s.current_area
        rules = lambda: ("acoustic_check", f"The survey in {target} was inconclusive (noise); repeat it before moving on.",
                         {"target_area": target, "cites": [f"{target} survey inconclusive"]})
    elif s.last_event == "acoustic_yes":
        allowed = ["request_dig", "acoustic_check"]
        target = s.current_area
        rules = lambda: ("request_dig", f"Acoustic loggers heard leak noise in {s.current_area}; dig there.",
                         {"target_area": target, "cites": [f"acoustic yes in {target}"]})
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
                                               "a wrong pipe nearby is the most common cause.",
                             {"target_area": target, "cites": [f"NOT FIXED at {target}"]})
        else:
            target = top["area_id"]
            rules = lambda: ("acoustic_check", f"{why} Next-best action: acoustic survey of {top['area_id']} "
                                               f"(likelihood {top['likelihood']:.0%}, information gain {top['info_gain']:.2f}, "
                                               f"{top['cost_hours']} crew-h, value {top['action_value']:.2f}).".strip(),
                             {"target_area": top["area_id"],
                              "cites": [f"{top['area_id']} value {top['action_value']:.2f}"]})
    history = [f"{h['area']}: {h['action']} {h['result']}" for h in s.area_history] or "nothing surveyed yet"
    situation = (f"Case {s.case_id}, zone {s.zone}, leak ≈ {s.leak_size_lps} L/s. Last event: {s.last_event}. "
                 f"Visits {s.visits}/{config.MAX_VISITS}, re-plans {s.replans}/{config.MAX_REPLANS}. "
                 f"Candidate areas (area, likelihood, information gain, crew-hours, action value; value = chance of "
                 f"finding + 0.3 x information gain): "
                 f"{[(a['area_id'], a['likelihood'], a['info_gain'], a['cost_hours'], a['action_value']) for a in cands]}. "
                 f"Already surveyed: {history}. Current area: {s.current_area}.")

    def check(a):
        if a.target_area not in ids + ([s.current_area] if s.current_area else []):
            raise ValueError(f"target_area {a.target_area!r} is not a candidate")
        if a.action == "request_dig" and (s.last_event != "acoustic_yes" or a.target_area != s.current_area):
            raise ValueError("a dig needs an acoustic yes in that very area")
        if s.last_event == "acoustic_yes" and a.target_area != s.current_area:
            raise ValueError("a confirmed acoustic hit is not abandoned")

    d = decide("Orchestrator", prompts.ORCHESTRATOR, situation, allowed, rules, schema=PlanAnswer,
               choice_field="action", check=check)
    target = d.extra.get("target_area") or target
    nums, row = AI("Orchestrator", d, when=f"Day {s.sim_day}")
    ledger = [row]
    timeline = []
    chosen = next((a for a in cands if a["area_id"] == target), None)
    best = max(a["action_value"] for a in cands)
    if d.choice == "acoustic_check" and chosen and chosen["action_value"] < 0.5 * best:
        note = (f"guard: low-value choice accepted ({target} value {chosen['action_value']:.2f} vs best "
                f"{best:.2f}) - allowed, shown for review.")
        nums["guard"] = "accepted (low-value choice)"
        timeline.append(T("Orchestrator", note, "alert"))
        ledger[0]["finding"] += "; low-value choice accepted"
    replanned = s.last_event in ("acoustic_no", "dig_empty", "not_fixed", "partly", "acoustic_inconclusive")
    timeline.insert(0, T("Orchestrator", f"{'Re-plan: ' if replanned else 'Plan: '}{d.choice} in {target}. {d.reason}",
                         "decision", _provider_note(d), **nums))
    return {"next_action": d.choice, "current_area": target, "areas": areas, "plan_reason": d.reason,
            "replans": s.replans + (1 if replanned else 0), "ledger": ledger, "timeline": timeline}


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
    nums, row = AI("Skeptic", d, when=f"Day {s.sim_day}")
    if d.choice == "send_back":
        return {"review_sendbacks": s.review_sendbacks + 1, "plan_reviewed": False, "ledger": [row],
                "timeline": [T("Skeptic", f"Plan sent back: {d.reason}", "decision", _provider_note(d), **nums)]}
    return {"plan_reviewed": True, "ledger": [row],
            "timeline": [T("Skeptic", f"Plan approved for the supervisor: {d.reason}", "decision", _provider_note(d), **nums)]}


# ============================================================ human gates (LangGraph interrupts)
def approve_plan(s: CaseState) -> dict:
    answer = interrupt({"type": "approve_plan", "case_id": s.case_id, "zone": s.zone, "area": s.current_area,
                        "action": s.next_action, "reason": s.plan_reason, "evidence": s.evidence, "areas": s.areas})
    ok = bool(answer.get("approved"))
    return {"plan_approved": ok, "status": "open" if ok else "escalated",
            "approval_by": answer.get("by", "supervisor"), "approval_role": answer.get("role", "supervisor"),
            "timeline": [T("Supervisor", f"Plan {'approved' if ok else 'rejected'} by {answer.get('by', 'supervisor')}.",
                           "human")]}


def approve_dig(s: CaseState) -> dict:
    answer = interrupt({"type": "approve_dig", "case_id": s.case_id, "area": s.current_area,
                        "reason": s.plan_reason})
    ok = bool(answer.get("approved"))
    who, role = answer.get("by", "Supervisor"), answer.get("role", "supervisor")
    return {"next_action": "dig" if ok else "rejected", "last_event": s.last_event if ok else "dig_rejected",
            "dig_approver": who if ok else None, "dig_approver_role": role if ok else None,
            "approval_by": who, "approval_role": role,
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
                    "area_history": [{"area": area, "action": "acoustic", "result": "failed (treated as no)"}],
                    "timeline": [T("Field Commander", f"Acoustic check failed ({r['message']}); treating as no.", "alert")]}
        res = r["result"]
        text = {"yes": "LEAK NOISE HEARD", "no": "quiet - no dig",
                "inconclusive": "INCONCLUSIVE (too noisy to tell) - no dig"}[res]
        event = {"yes": "acoustic_yes", "no": "acoustic_no", "inconclusive": "acoustic_inconclusive"}[res]
        return {"last_event": event, "visits": s.visits + 1,
                "area_history": [{"area": area, "action": "acoustic", "result": res}],
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
                "area_history": [{"area": area, "action": "dig", "result": "repaired (claimed)"}],
                "ledger": [L("Field evidence", f"Crew report: repaired in {area} (a claim - not proof)", "neutral",
                             "low (unverified)", "crew_status", f"Day {s.sim_day}")],
                "timeline": [T("Field Commander", f"{wo['work_order_id']}: crew reports leak repaired in {area}. "
                                                  f"{sms.get('homes_notified', 0)} homes texted; slow refill ordered "
                                                  "(avoids a pressure-surge burst).", "action")]}
    return {"work_order": wo["work_order_id"], "last_event": "dig_empty",
            "area_history": [{"area": area, "action": "dig", "result": "found nothing"}],
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
