"""Build a FastMCP server from a list of NEER tools (all servers share this)."""
from __future__ import annotations

import os

os.environ.setdefault("NEER_WORLD_SHARED", "1")      # servers are separate processes -> share the world file

from mcp.server.fastmcp import FastMCP  # noqa: E402


def build_server(name: str, tools: list) -> FastMCP:
    server = FastMCP(name)
    for fn in tools:
        # structured_output=False: results (or ToolError dicts) are returned as JSON text,
        # so a ToolError never fails schema validation - the agent reads it and self-corrects.
        server.add_tool(fn, name=fn.__name__, description=(fn.__doc__ or "").strip(), structured_output=False)
    return server
