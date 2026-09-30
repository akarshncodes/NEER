"""Chaos toggles: deliberately break things so we can show NEER recovering.

Stored in data/chaos.json so the dashboard (or a judge) can flip them while
agents run in another process.

    scada_timeout       next N SCADA tool calls time out
    sensor_dies         one pressure sensor goes offline (NaN readings)
    llm_bad_json        next N LLM replies are malformed
    crew_finds_nothing  next acoustic check says "no" even inside the leak area
"""
from __future__ import annotations

import json
import threading

from neer import config

_lock = threading.Lock()
DEFAULTS = {"scada_timeout": 0, "sensor_dies": None, "llm_bad_json": 0, "crew_finds_nothing": 0}


def _read() -> dict:
    try:
        return {**DEFAULTS, **json.loads(config.CHAOS_FILE.read_text())}
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULTS)


def _write(state: dict) -> None:
    config.CHAOS_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.CHAOS_FILE.write_text(json.dumps(state))


def get() -> dict:
    with _lock:
        return _read()


def set_toggle(name: str, value) -> None:
    if name not in DEFAULTS:
        raise KeyError(name)
    with _lock:
        s = _read()
        s[name] = value
        _write(s)


def consume(name: str) -> bool:
    """For counter toggles: True (and decrement) if the chaos should fire now."""
    with _lock:
        s = _read()
        if isinstance(s.get(name), int) and s[name] > 0:
            s[name] -= 1
            _write(s)
            return True
        return False


def reset() -> None:
    with _lock:
        _write(dict(DEFAULTS))
