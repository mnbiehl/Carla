#!/usr/bin/env python3
"""
Stdio-to-SSE bridge for Carla MCP Server.

Claude Code connects to this via stdio transport. This proxy forwards
all MCP calls to Carla's SSE MCP server (default: http://127.0.0.1:3001/sse).

Usage in .mcp.json:
{
    "mcpServers": {
        "carla-mcp": {
            "command": "uv",
            "args": ["run", "python3", "source/frontend/carla_mcp/mcp_stdio_bridge.py"],
            "cwd": "/home/michael/carla-mcp-fork"
        }
    }
}
"""

import os
import sys


def main():
    from fastmcp import FastMCP

    port = os.getenv("CARLA_MCP_PORT", "3001")
    host = os.getenv("CARLA_MCP_HOST", "127.0.0.1")
    url = f"http://{host}:{port}/sse"

    proxy = FastMCP.as_proxy(url)
    proxy.run(transport="stdio")


if __name__ == "__main__":
    main()
