"""twin-mcp: MCP server exposing NEER's twin tools over stdio.

    uv run python -m neer.mcp_servers.twin_server
"""
from neer.mcp_servers.common import build_server
from neer.tools.registry import SERVERS

server = build_server("twin-mcp", SERVERS["twin"])

if __name__ == "__main__":
    server.run()
