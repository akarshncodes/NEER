"""Shared test setup: every test gets its own data folder (world, chaos, trace) - the cache is shared."""
import pytest

from neer import config


@pytest.fixture(autouse=True)
def isolated_data(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CHAOS_FILE", tmp_path / "chaos.json")
    monkeypatch.setattr(config, "TRACE_DB", tmp_path / "trace.db")
    monkeypatch.setattr(config, "WORLD_FILE", tmp_path / "world.pkl")
    monkeypatch.setattr(config, "CASES_DB", tmp_path / "cases.db")
    from neer.tools import resilience
    monkeypatch.setattr(resilience, "RETRY_BACKOFF_S", [0.01, 0.01])
    resilience.breaker.reset()
    monkeypatch.setenv("NEER_TOOL_MODE", "direct")
    monkeypatch.setenv("NEER_LLM_CHAIN", "rules")
    monkeypatch.delenv("NEER_WORLD_SHARED", raising=False)
    from neer.agents import toolbox
    monkeypatch.setattr(toolbox, "_mcp", None)
    from neer.tools import world
    monkeypatch.setattr(world, "_world", None)
    yield
