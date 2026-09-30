"""Build a FastMCP server from a list of NEER tools (all servers share this)."""
from __future__ import annotations

import os

os.environ.setdefault("NEER_WORLD_SHARED", "1")      # servers are separate processes -> share the world file

import functools  # noqa: E402
import inspect  # noqa: E402
import json  # noqa: E402

from mcp.server.fastmcp import FastMCP  # noqa: E402

from neer.tools.resilience import current_agent  # noqa: E402


def _as_json_text(fn):
    """Same tool signature, but always returns ONE JSON string (a list stays a list, a ToolError stays readable)."""
    @functools.wraps(fn)
    def wrapped(**kwargs) -> str:
        token = current_agent.set("mcp-server")
        try:
            return json.dumps(fn(**kwargs), default=str)
        finally:
            current_agent.reset(token)
    sig = inspect.signature(fn.raw, eval_str=True)      # resolve string annotations (Optional etc.)
    wrapped.__signature__ = sig.replace(return_annotation=str)
    del wrapped.__wrapped__
    return wrapped


def build_server(name: str, tools: list) -> FastMCP:
    server = FastMCP(name)
    for fn in tools:
        server.add_tool(_as_json_text(fn), name=fn.__name__, description=(fn.__doc__ or "").strip(),
                        structured_output=False)
    return server
