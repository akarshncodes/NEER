"""audit-mcp: MCP server exposing NEER's audit tools over stdio.

    uv run python -m neer.mcp_servers.audit_server
"""
from neer.mcp_servers.common import build_server
from neer.tools.registry import SERVERS

server = build_server("audit-mcp", SERVERS["audit"])

if __name__ == "__main__":
    server.run()
