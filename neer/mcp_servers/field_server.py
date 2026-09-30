"""field-mcp: MCP server exposing NEER's field tools over stdio.

    uv run python -m neer.mcp_servers.field_server
"""
from neer.mcp_servers.common import build_server
from neer.tools.registry import SERVERS

server = build_server("field-mcp", SERVERS["field"])

if __name__ == "__main__":
    server.run()
