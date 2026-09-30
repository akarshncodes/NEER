"""How agents call tools: through the 4 MCP servers (NEER_TOOL_MODE=mcp) or in-process (direct).

MCP mode keeps one long-lived stdio session per server on a background event loop.
If an MCP call fails at the transport level, the call falls back to direct mode
(and the trace says so) - one more self-correction layer.
"""
from __future__ import annotations

import asyncio
import json
import os
import threading
import time
from contextlib import AsyncExitStack
from typing import Any

from neer.tools.registry import ALL_TOOLS, SERVERS
from neer.tools.resilience import _trace, current_agent

TOOL_SERVER = {fn.__name__: f"{srv}-mcp" for srv, fns in SERVERS.items() for fn in fns}


class McpToolbox:
    def __init__(self) -> None:
        from neer.mcp_servers.client import connections
        self.conns = connections()
        self.loop = asyncio.new_event_loop()
        self.sessions: dict[str, Any] = {}
        self._ready = threading.Event()
        self.error: Exception | None = None
        threading.Thread(target=self._run, daemon=True).start()
        if not self._ready.wait(60):
            self.error = TimeoutError("MCP servers did not start in 60 s")
        if self.error:
            raise RuntimeError(f"MCP unavailable: {self.error}")

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._open())
        except Exception as e:  # noqa: BLE001
            self.error = e
            self._ready.set()
            return
        self._ready.set()
        self.loop.run_forever()

    async def _open(self) -> None:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        self.stack = AsyncExitStack()
        for name, c in self.conns.items():
            p = StdioServerParameters(command=c["command"], args=c["args"], env=c["env"], cwd=c["cwd"])
            r, w = await self.stack.enter_async_context(stdio_client(p))
            s = await self.stack.enter_async_context(ClientSession(r, w))
            await s.initialize()
            self.sessions[name] = s

    def call(self, name: str, args: dict) -> Any:
        async def go():
            res = await self.sessions[TOOL_SERVER[name]].call_tool(name, args)
            text = res.content[0].text if res.content else "[]"
            if res.isError:
                return {"error": True, "code": "invalid_input", "message": text[:300], "hint": "Fix arguments."}
            return json.loads(text)
        return asyncio.run_coroutine_threadsafe(go(), self.loop).result(timeout=30)


_mcp: McpToolbox | None = None


def call(agent: str, name: str, **args) -> Any:
    """Call a tool as `agent`. Returns data or a ToolError dict (never raises)."""
    global _mcp
    token = current_agent.set(agent)
    try:
        if os.getenv("NEER_TOOL_MODE", "direct") == "mcp":
            try:
                if _mcp is None:
                    _mcp = McpToolbox()
                t0 = time.time()
                out = _mcp.call(name, args)
                bad = isinstance(out, dict) and out.get("error") is True
                _trace(agent, name, args, not bad, f"via {TOOL_SERVER[name]}: " + json.dumps(out, default=str)[:160],
                       (time.time() - t0) * 1000)
                return out
            except RuntimeError as e:        # servers never came up: stay in direct mode from now on
                os.environ["NEER_TOOL_MODE"] = "direct"
                _trace(agent, name, args, False, f"{e}; switching to direct tool calls", 0)
            except Exception as e:  # noqa: BLE001 - transport failure -> in-process fallback
                _trace(agent, name, args, False, f"MCP transport failed ({type(e).__name__}); using direct call", 0)
        return ALL_TOOLS[name](**args)
    finally:
        current_agent.reset(token)
