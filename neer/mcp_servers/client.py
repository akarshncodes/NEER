"""MCP client config: how agents launch and talk to the 4 NEER MCP servers (stdio)."""
from __future__ import annotations

import os
import sys

from neer import config

SERVER_NAMES = ["scada", "twin", "field", "audit"]


def connections() -> dict:
    """Connection settings for langchain-mcp-adapters' MultiServerMCPClient."""
    env = {**os.environ, "NEER_WORLD_SHARED": "1", "PYTHONPATH": str(config.ROOT),
           "NEER_WORLD_FILE": str(config.WORLD_FILE), "NEER_CHAOS_FILE": str(config.CHAOS_FILE),
           "NEER_TRACE_DB": str(config.TRACE_DB)}
    return {f"{n}-mcp": {"command": sys.executable, "args": ["-m", f"neer.mcp_servers.{n}_server"],
                         "transport": "stdio", "env": env, "cwd": str(config.ROOT)} for n in SERVER_NAMES}
