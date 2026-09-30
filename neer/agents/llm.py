"""LLM router: try each provider in NEER_LLM_CHAIN, fall back on any failure, end with `rules`.

    groq:llama-3.3-70b-versatile -> gemini:gemini-2.0-flash -> ollama:qwen2.5:7b -> rules

Every decision is structured (Pydantic) and must pick from an ALLOWED set of actions.
An invalid, malformed, slow or missing answer is a failure -> retry once -> next provider.
`rules` is a deterministic policy that always answers, so NEER never stops.
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutTimeout
from dataclasses import dataclass
from typing import Callable

from pydantic import BaseModel, Field

from neer import config
from neer.tools import chaos
from neer.tools.resilience import _trace

_pool = ThreadPoolExecutor(max_workers=2)


class Decision(BaseModel):
    choice: str = Field(description="Exactly one of the allowed options")
    reason: str = Field(description="One or two plain-English sentences citing the numbers given")


@dataclass
class DecisionResult:
    choice: str
    reason: str
    provider: str
    fallbacks: list[str]
    ms: float


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


def _model(provider: str, model: str):
    key = f"{provider}:{model}"
    if key not in _models:
        if provider == "groq":
            from langchain_groq import ChatGroq
            m = ChatGroq(model=model, temperature=0, timeout=config.LLM_TIMEOUT_S, max_retries=0)
        elif provider == "gemini":
            from langchain_google_genai import ChatGoogleGenerativeAI
            m = ChatGoogleGenerativeAI(model=model, temperature=0, timeout=config.LLM_TIMEOUT_S, max_retries=0)
        elif provider == "ollama":
            from langchain_ollama import ChatOllama
            m = ChatOllama(model=model, temperature=0,
                           base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
        else:
            raise ValueError(provider)
        _models[key] = m.with_structured_output(Decision)
    return _models[key]


def decide(agent: str, system: str, situation: str, allowed: list[str],
           rules: Callable[[], tuple[str, str]]) -> DecisionResult:
    """Ask the chain to choose one of `allowed`. `rules()` returns (choice, reason) deterministically."""
    t0 = time.time()
    fails: list[str] = []
    prompt = (f"{situation}\n\nAllowed options: {allowed}.\n"
              f"Answer with `choice` = exactly one allowed option and a short `reason` that cites the numbers above. "
              f"Never invent numbers.")
    for provider, model in _chain():
        if provider == "rules":
            break
        if not _available(provider):
            continue
        for attempt in range(2):
            try:
                if chaos.consume("llm_bad_json"):
                    raise ValueError("malformed JSON from model (chaos)")
                fut = _pool.submit(_model(provider, model).invoke, [("system", system), ("user", prompt)])
                d: Decision = fut.result(timeout=config.LLM_TIMEOUT_S)
                if d is None or d.choice not in allowed:
                    raise ValueError(f"choice {getattr(d, 'choice', None)!r} not in allowed set")
                ms = (time.time() - t0) * 1000
                _trace(agent, f"llm:{provider}", {"allowed": allowed}, True, f"{d.choice}: {d.reason}", ms)
                return DecisionResult(d.choice, d.reason.strip(), f"{provider}:{model}", fails, ms)
            except (FutTimeout, TimeoutError):
                fails.append(f"{provider} timeout")
            except Exception as e:  # noqa: BLE001 - any model failure means: try the next one
                fails.append(f"{provider}: {str(e)[:80]}")
            _trace(agent, f"llm:{provider}", {"attempt": attempt + 1}, False, fails[-1], (time.time() - t0) * 1000)

    # deterministic fallback - always works. Chaos can still "break" it once to show the recovery.
    if chaos.consume("llm_bad_json"):
        fails.append("rules: malformed reply (chaos) -> re-asked")
        _trace(agent, "llm:rules", {}, False, "malformed reply (chaos), retrying", 0)
    choice, reason = rules()
    ms = (time.time() - t0) * 1000
    _trace(agent, "llm:rules", {"allowed": allowed}, True, f"{choice}: {reason}", ms)
    return DecisionResult(choice, reason, "rules", fails, ms)
