"""Ask NEER: a question box in the UI, answered by the AI from THIS case's own record.

The live model (Groq -> Gemini -> Ollama, the same chain as the agents) gets only the case record:
status, zone, leak size, areas, verdict, the agents' messages and the evidence ledger. It is told to answer
only from that record and never to invent a number. If no model is reachable (no keys, no internet, quota),
a deterministic explainer answers from the same record, so the box always works.
"""
from __future__ import annotations

import time

from neer import config
from neer.agents import llm as L

SYSTEM = ("You are NEER's assistant inside a water-utility control room. Answer the user's question using ONLY the "
          "case record provided. Quote numbers exactly as they appear; never invent a number, place or event. If the "
          "record does not contain the answer, say so. Be short and plain (3-5 sentences). If asked for Tamil, answer "
          "in simple Tamil. Relative likelihoods are not probabilities; the Auditor's verdict is the proof of repair.")

QUICK = ["Explain this case simply", "Why this search area?", "Is the leak really fixed?",
         "What happens next?", "Summarise in Tamil"]


def case_record(v: dict, max_msgs: int = 25) -> str:
    """The case as plain text: this is all the model is allowed to know."""
    areas = ", ".join(f"{a['area_id']} {a['likelihood']:.0%}" for a in (v.get("areas") or [])[:3]) or "not located yet"
    msgs = "\n".join(f"- {e['agent']}: {e['text']}" for e in (v.get("timeline") or [])[-max_msgs:])
    ledger = "\n".join(f"- [{r['dimension']}] {r['finding']} (supports: {r['supports']}; source: {r['source']})"
                       for r in (v.get("ledger") or [])[-15:])
    return (f"Case {v.get('case_id')} | status {v.get('status')} | tier {v.get('tier')} | zone {v.get('zone')} | "
            f"leak size estimate {v.get('leak_size_lps')} L/s | areas (relative likelihood): {areas} | "
            f"current area {v.get('current_area')} | field visits {v.get('visits', 0)} | re-plans {v.get('replans', 0)} | "
            f"Auditor verdict {v.get('verdict') or 'none yet'} | contractor {v.get('contractor') or '-'}\n"
            f"Agent messages:\n{msgs}\nEvidence ledger:\n{ledger}")


def rules_answer(q: str, v: dict) -> str:
    """Deterministic explainer used when no model answers. Built only from the case record."""
    ql = q.lower()
    zone, lps, verdict = v.get("zone") or "-", v.get("leak_size_lps") or 0, v.get("verdict")
    areas = v.get("areas") or []
    top = areas[0] if areas else None
    status = v.get("status", "open")
    if "tamil" in ql:
        if status == "closed" and verdict == "FIXED":
            return (f"மண்டலம் {zone}-இல் சுமார் {lps:.1f} லிட்டர்/விநாடி நீர் கசிவு கண்டுபிடிக்கப்பட்டது. "
                    f"பழுது நீக்கப்பட்டது; மீட்டர் அளவீடுகள் அது சரியானது என்று நிரூபித்தன.")
        return (f"மண்டலம் {zone}-இல் சுமார் {lps:.1f} லிட்டர்/விநாடி கூடுதல் நீர் செல்கிறது. NEER கசிவைத் தேடுகிறது; "
                "தோண்டுவதற்கு முன் மேற்பார்வையாளர் அனுமதி தேவை.")
    if "fixed" in ql or "proof" in ql or "really" in ql:
        if verdict == "FIXED":
            return (f"Yes. The Auditor measured the zone's water loss itself before and after the repair and reached "
                    f"999:1 evidence: {v.get('verdict_reason', '')} The contractor was {v.get('contractor')}.")
        if verdict:
            return f"No. The Auditor's verdict is {verdict}: {v.get('verdict_reason', '')}"
        return "Not yet. Nothing is repaired until the Auditor proves it from the meters; no repair has been verified."
    if "why" in ql and top:
        return (f"{top['area_id']} has the highest relative likelihood ({top['likelihood']:.0%}) from matching the "
                f"pressure pattern against leak fingerprints in zone {zone}. The Orchestrator picks the next survey by "
                f"value (chance of finding + information gain): {top.get('action_value', '-')}. Listening comes "
                "before any dig, so a wrong guess costs one quiet survey, not a hole in the road.")
    if "next" in ql:
        if status == "closed":
            return "Nothing - the case is closed with proof. The proven-clean days feed the protected baseline."
        if v.get("next_action") == "request_dig":
            return f"A supervisor or engineer must approve the dig in {v.get('current_area')}. No one digs without that."
        return (f"Next action: {v.get('next_action') or 'the agents are deciding'} in {v.get('current_area') or '-'}. "
                "Every quiet area lowers its likelihood and NEER re-plans; a dig always waits for a person.")
    # default: the simple story
    story = (f"Zone {zone} was using about {lps:.1f} L/s more water than normal, and no pump, valve, planned work "
             "or broken sensor explained it, so NEER treated it as a leak. ")
    if top:
        story += f"The most likely area was {top['area_id']} ({top['likelihood']:.0%} relative likelihood). "
    story += f"The crew made {v.get('visits', 0)} listening visit(s). "
    story += (f"The Auditor's verdict is {verdict}." if verdict else "The repair has not been verified yet.")
    return story


def ask(question: str, v: dict, brain: str = "chain") -> tuple[str, str]:
    """(answer, who answered). Tries the live model chain, then the deterministic explainer."""
    record = case_record(v)
    fails = []
    if brain == "chain":
        for provider, model in L._chain():
            if provider == "rules" or not L._available(provider) or L._resting(provider):
                continue
            try:
                L._pace(provider)
                m = _plain_model(provider, model)
                fut = L._pool.submit(m.invoke, [("system", SYSTEM),
                                                ("user", f"CASE RECORD:\n{record}\n\nQUESTION: {question}")])
                out = fut.result(timeout=config.LLM_TIMEOUT_S)
                text = (getattr(out, "content", None) or str(out)).strip()
                if text:
                    return text, f"{provider}:{model}"
            except Exception as e:  # noqa: BLE001 - any failure: next provider
                fails.append(f"{provider}: {str(e)[:60]}")
                L._note_failure(provider, f"{type(e).__name__} {e}")
    who = "rules (deterministic explainer)" + (f" after: {'; '.join(fails)}" if fails else "")
    return rules_answer(question, v), who


_plain: dict[str, object] = {}


def _plain_model(provider: str, model: str):
    key = f"{provider}:{model}"
    if key not in _plain:
        if provider == "groq":
            from langchain_groq import ChatGroq
            extra = {"reasoning_effort": "low"} if "gpt-oss" in model else {}
            _plain[key] = ChatGroq(model=model, temperature=0.2, timeout=config.LLM_TIMEOUT_S, max_retries=0, **extra)
        elif provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            _plain[key] = ChatGoogleGenerativeAI(model=model, temperature=0.2, timeout=config.LLM_TIMEOUT_S, max_retries=0)
        else:
            import os
            from langchain_ollama import ChatOllama
            _plain[key] = ChatOllama(model=model, temperature=0.2, base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    return _plain[key]


def timed_ask(question: str, v: dict, brain: str) -> dict:
    t0 = time.time()
    answer, who = ask(question, v, brain)
    return {"q": question, "a": answer, "who": who, "ms": round((time.time() - t0) * 1000)}
