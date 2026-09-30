"""LLM router: try each provider in NEER_LLM_CHAIN, fall back on any failure, end with `rules`.

    groq:openai/gpt-oss-120b -> gemini:gemini-3.5-flash -> ollama:qwen2.5:7b -> rules

Every decision is structured (Pydantic) and must pick from an ALLOWED set of actions.
An invalid, malformed, slow or missing answer is a failure -> retry once -> next provider.
`rules` is a deterministic policy that always answers, so NEER never stops.
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutTimeout
from dataclasses import dataclass, field
from typing import Callable

from pydantic import BaseModel, Field

from neer import config
from neer.tools import chaos
from neer.tools.resilience import _trace

_pool = ThreadPoolExecutor(max_workers=2)


class Decision(BaseModel):
    choice: str = Field(description="Exactly one of the allowed options")
    reason: str = Field(description="One or two plain-English sentences citing the numbers given")
    cites: list[str] = Field(default_factory=list, description="Short quotes of the evidence relied on, copied from the situation")


class GateAnswer(BaseModel):
    """Skeptic gate: a hypothesis judge."""
    most_likely: str = Field(description="One of the listed hypotheses")
    missing_evidence: list[str] = Field(default_factory=list, description="Extra checks wanted before deciding (may be empty)")
    decision: str = Field(description="Exactly one of the allowed decisions")
    reason: str = Field(description="One or two plain sentences citing the numbers given")
    cites: list[str] = Field(default_factory=list, description="Short quotes of the evidence relied on")


class PlanAnswer(BaseModel):
    """Orchestrator: what to do and where."""
    action: str = Field(description="Exactly one of the allowed actions")
    target_area: str = Field(description="One of the listed candidate areas (or the current area)")
    reason: str = Field(description="One or two plain sentences citing the numbers given")
    cites: list[str] = Field(default_factory=list, description="Short quotes of the evidence relied on")


class InterpretAnswer(BaseModel):
    """Detective: reads its own localisation result."""
    concentrated: bool = Field(description="True if one or two areas hold most of the likelihood")
    more_data_helps: bool = Field(description="True if another day of data would probably sharpen the map")
    decision: str = Field(description="Exactly one of the allowed decisions")
    reason: str = Field(description="One or two plain sentences interpreting the evidence, citing the numbers given")
    cites: list[str] = Field(default_factory=list, description="Short quotes of the evidence relied on")


@dataclass
class DecisionRecord:
    """One audit row per decision: what the answering provider chose vs what `rules()` would have chosen."""
    agent: str
    provider: str            # "groq:<model>", "gemini:<model>" or "rules"
    choice: str
    rules_choice: str
    reason: str
    allowed: list[str]
    fallbacks: list[str]
    guard_rejections: int    # model answers refused because the choice was not in the allowed set
    vetoed: bool = False     # the answer was valid, but a rule overrode it (set by the agent)


DECISION_LOG: list[DecisionRecord] = []


def clear_decision_log() -> None:
    DECISION_LOG.clear()


@dataclass
class DecisionResult:
    choice: str
    reason: str
    provider: str
    fallbacks: list[str]
    ms: float
    rules_choice: str = ""           # what `rules()` would have chosen at this step
    extra: dict = field(default_factory=dict)   # the other structured fields (target_area, missing_evidence, ...)
    cites: list[str] = field(default_factory=list)


def _chain() -> list[tuple[str, str]]:
    raw = os.getenv("NEER_LLM_CHAIN", config.LLM_CHAIN)
    out = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        prov, _, model = item.partition(":")
        out.append((prov, model))
    if not out or out[-1][0] != "rules":
        out.append(("rules", ""))
    return out


def _available(provider: str) -> bool:
    if provider == "groq":
        return bool(os.getenv("GROQ_API_KEY"))
    if provider == "gemini":
        return bool(os.getenv("GOOGLE_API_KEY"))
    if provider == "ollama":
        return os.getenv("NEER_USE_OLLAMA", "0") == "1"
    return provider == "rules"


_models: dict[str, object] = {}
_last_call: dict[str, float] = {}


def _pace(provider: str) -> None:
    """Optional spacing between calls to one provider (NEER_LLM_MIN_INTERVAL_S) to stay inside free-tier limits."""
    gap = float(os.getenv("NEER_LLM_MIN_INTERVAL_S", "0"))
    wait = _last_call.get(provider, 0.0) + gap - time.time()
    if wait > 0:
        time.sleep(wait)
    _last_call[provider] = time.time()


def _model(provider: str, model: str, schema: type[BaseModel] = Decision):
    key = f"{provider}:{model}:{schema.__name__}"
    if key not in _models:
        if provider == "groq":
            from langchain_groq import ChatGroq
            extra = {"reasoning_effort": "low"} if "gpt-oss" in model else {}     # fewer tokens per call (free-tier TPM)
            m = ChatGroq(model=model, temperature=0, timeout=config.LLM_TIMEOUT_S, max_retries=0, **extra)
        elif provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            m = ChatGoogleGenerativeAI(model=model, temperature=0, timeout=config.LLM_TIMEOUT_S, max_retries=0)
        elif provider == "ollama":
            from langchain_ollama import ChatOllama
            m = ChatOllama(model=model, temperature=0,
                           base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
        else:
            raise ValueError(provider)
        _models[key] = m.with_structured_output(schema)
    return _models[key]


def decide(agent: str, system: str, situation: str, allowed: list[str],
           rules: Callable[[], tuple], schema: type[BaseModel] = Decision, choice_field: str = "choice",
           check: Callable[[BaseModel], None] | None = None, ask_llm: bool = True) -> DecisionResult:
    """Ask the chain to choose one of `allowed`.

    `rules()` returns (choice, reason) or (choice, reason, extra_fields) deterministically - it is the last link of
    the chain and the default that every AI answer is compared with. `schema` / `choice_field` let an agent ask a
    richer structured question; `check(answer)` is the agent's guard: raise ValueError to reject an answer
    (it counts like any invalid answer: retry once, then the next provider, finally `rules`).
    """
    t0 = time.time()
    fails: list[str] = []
    rejected = 0
    rules_choice = rules()[0]          # deterministic and side-effect free; logged next to the model's answer
    prompt = (f"{situation}\n\nAllowed options: {allowed}.\n"
              f"Answer with `{choice_field}` = exactly one allowed option and a short `reason` that cites the numbers above. "
              f"Never invent numbers.")
    for provider, model in _chain():
        if provider == "rules" or not ask_llm:
            break
        if not _available(provider):
            continue
        for attempt in range(2):
            try:
                if chaos.consume("llm_bad_json"):
                    raise ValueError("malformed JSON from model (chaos)")
                _pace(provider)
                fut = _pool.submit(_model(provider, model, schema).invoke, [("system", system), ("user", prompt)])
                d: Decision = fut.result(timeout=config.LLM_TIMEOUT_S)
                picked = getattr(d, choice_field, None)
                if d is None or picked not in allowed:
                    rejected += 1
                    raise ValueError(f"choice {picked!r} not in allowed set")
                if check is not None:
                    try:
                        check(d)
                    except ValueError:
                        rejected += 1
                        raise
                ms = (time.time() - t0) * 1000
                _trace(agent, f"llm:{provider}", {"allowed": allowed}, True, f"{picked}: {d.reason}", ms)
                DECISION_LOG.append(DecisionRecord(agent, f"{provider}:{model}", picked, rules_choice,
                                                   d.reason.strip(), list(allowed), list(fails), rejected))
                extra = {k: v for k, v in d.model_dump().items() if k not in (choice_field, "reason", "cites")}
                return DecisionResult(picked, d.reason.strip(), f"{provider}:{model}", fails, ms, rules_choice,
                                      extra, list(getattr(d, "cites", []) or []))
            except (FutTimeout, TimeoutError):
                fails.append(f"{provider} timeout")
            except Exception as e:  # noqa: BLE001 - any model failure means: try the next one
                fails.append(f"{provider}: {str(e)[:80]}")
            _trace(agent, f"llm:{provider}", {"attempt": attempt + 1}, False, fails[-1], (time.time() - t0) * 1000)

    # deterministic fallback - always works. Chaos can still "break" it once to show the recovery.
    if chaos.consume("llm_bad_json"):
        fails.append("rules: malformed reply (chaos) -> re-asked")
        _trace(agent, "llm:rules", {}, False, "malformed reply (chaos), retrying", 0)
    choice, reason, *rest = rules()
    extra = dict(rest[0]) if rest else {}
    ms = (time.time() - t0) * 1000
    _trace(agent, "llm:rules", {"allowed": allowed}, True, f"{choice}: {reason}", ms)
    DECISION_LOG.append(DecisionRecord(agent, "rules", choice, rules_choice, reason, list(allowed), list(fails),
                                       rejected))
    return DecisionResult(choice, reason, "rules", fails, ms, rules_choice, extra,
                          list(extra.pop("cites", []) or []))
