"""The resilience layer every tool goes through.

    validate input (Pydantic)  ->  timeout  ->  retry with back-off  ->  circuit breaker
    ->  structured ToolError instead of a crash  ->  trace log (SQLite)

Agents read ToolError messages and correct themselves (tool self-correction loop).
"""
from __future__ import annotations

import contextvars
import functools
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutTimeout
from typing import Any, Callable

from pydantic import BaseModel, ValidationError, validate_call

from neer import config
from neer.schemas import ToolError

current_agent: contextvars.ContextVar[str] = contextvars.ContextVar("current_agent", default="user")
_pool = ThreadPoolExecutor(max_workers=4)
RETRY_BACKOFF_S = [0.5, 1.0]


# ------------------------------------------------------------ circuit breaker
class Breaker:
    def __init__(self) -> None:
        self.fails: dict[str, int] = {}
        self.open_until: dict[str, float] = {}

    def is_open(self, server: str) -> bool:
        return time.time() < self.open_until.get(server, 0)

    def record(self, server: str, ok: bool) -> None:
        if ok:
            self.fails[server] = 0
            return
        self.fails[server] = self.fails.get(server, 0) + 1
        if self.fails[server] >= config.BREAKER_FAILS:
            self.open_until[server] = time.time() + config.BREAKER_COOLDOWN_S
            self.fails[server] = 0

    def reset(self) -> None:
        self.fails.clear()
        self.open_until.clear()


breaker = Breaker()


# ------------------------------------------------------------ trace log
def _trace(agent: str, tool: str, args: dict, ok: bool, summary: str, ms: float) -> None:
    try:
        config.TRACE_DB.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(config.TRACE_DB) as db:
            db.execute("CREATE TABLE IF NOT EXISTS trace (ts REAL, agent TEXT, tool TEXT, args TEXT, ok INT, summary TEXT, ms REAL)")
            db.execute("INSERT INTO trace VALUES (?,?,?,?,?,?,?)",
                       (time.time(), agent, tool, json.dumps(args, default=str)[:500], int(ok), summary[:300], ms))
    except sqlite3.Error:
        pass   # tracing must never break a tool


def read_trace(limit: int = 200) -> list[dict]:
    try:
        with sqlite3.connect(config.TRACE_DB) as db:
            rows = db.execute("SELECT ts, agent, tool, args, ok, summary, ms FROM trace ORDER BY ts DESC LIMIT ?",
                              (limit,)).fetchall()
    except sqlite3.Error:
        return []
    keys = ["ts", "agent", "tool", "args", "ok", "summary", "ms"]
    return [dict(zip(keys, r)) for r in rows]


def clear_trace() -> None:
    try:
        with sqlite3.connect(config.TRACE_DB) as db:
            db.execute("DELETE FROM trace")
    except sqlite3.Error:
        pass


def _dump(x: Any) -> Any:
    if isinstance(x, BaseModel):
        return x.model_dump(mode="json")
    if isinstance(x, list):
        return [_dump(i) for i in x]
    return x


# ------------------------------------------------------------ the decorator
def resilient_tool(server: str, chaos_hook: Callable[[], None] | None = None,
                   timeout_s: float = config.TOOL_TIMEOUT_S, retries: int = config.TOOL_RETRIES):
    """Wrap a tool function: validated, timed out, retried, breaker-protected, traced.
    Always returns JSON-able data (dict / list) or a ToolError dict - never raises."""
    def deco(fn):
        checked = validate_call(fn)

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            name = fn.__name__
            agent = current_agent.get()
            t0 = time.time()
            if breaker.is_open(server):
                err = ToolError(code="degraded", message=f"{server} is temporarily unavailable (circuit open)",
                                hint="Work with the data you already have, or mark the case INCONCLUSIVE.")
                _trace(agent, name, kwargs, False, err.message, 0)
                return err.model_dump()
            last = None
            for attempt in range(retries + 1):
                try:
                    if chaos_hook:
                        chaos_hook()
                    fut = _pool.submit(checked, *args, **kwargs)
                    out = _dump(fut.result(timeout=timeout_s))
                    breaker.record(server, True)
                    _trace(agent, name, kwargs, True, _summary(out), (time.time() - t0) * 1000)
                    return out
                except ValidationError as e:
                    err = ToolError(code="invalid_input", message=_short(e),
                                    hint="Fix the arguments to match the tool schema and call again.")
                    _trace(agent, name, kwargs, False, err.message, (time.time() - t0) * 1000)
                    return err.model_dump()
                except (TimeoutError, FutTimeout):
                    last = ToolError(code="timeout", message=f"{name} timed out", hint="Retried automatically.")
                    _trace(agent, name, kwargs, False, f"timeout (attempt {attempt + 1}), retrying", (time.time() - t0) * 1000)
                except PermissionError as e:
                    err = ToolError(code="refused", message=str(e), hint="This action is not allowed yet.")
                    _trace(agent, name, kwargs, False, err.message, (time.time() - t0) * 1000)
                    return err.model_dump()
                except (ValueError, KeyError) as e:
                    err = ToolError(code="invalid_input", message=str(e), hint="Check ids (case, area, work order).")
                    _trace(agent, name, kwargs, False, err.message, (time.time() - t0) * 1000)
                    return err.model_dump()
                except Exception as e:  # noqa: BLE001 - tools must never crash an agent
                    last = ToolError(code="internal", message=f"{type(e).__name__}: {e}")
                if attempt < retries:
                    time.sleep(RETRY_BACKOFF_S[min(attempt, len(RETRY_BACKOFF_S) - 1)])
            breaker.record(server, False)
            _trace(agent, name, kwargs, False, last.message, (time.time() - t0) * 1000)
            return last.model_dump()

        wrapper.raw = fn
        return wrapper
    return deco


def is_error(x: Any) -> bool:
    return isinstance(x, dict) and x.get("error") is True


def _summary(out: Any) -> str:
    s = json.dumps(out, default=str)
    return s[:200]


def _short(e: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, er['loc']))}: {er['msg']}" for er in e.errors())[:300]
