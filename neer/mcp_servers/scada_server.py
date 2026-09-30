"""scada-mcp: MCP server exposing NEER's scada tools over stdio.

    uv run python -m neer.mcp_servers.scada_server
"""
from neer.mcp_servers.common import build_server
from neer.tools.registry import SERVERS

server = build_server("scada-mcp", SERVERS["scada"])

if __name__ == "__main__":
    server.run()
