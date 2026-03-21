"""
Looper MCP Server — FastMCP server wrapping looperdooper's JSON TCP interface.

Manages the looperdooper process lifecycle and exposes looper commands as MCP tools.
Serves via SSE for the bridge to discover and proxy.

Usage:
    uv run python -m looper_mcp.main
"""

import os
import logging
from pathlib import Path

from fastmcp import FastMCP

from looper_mcp.looper_client import LooperClient
from looper_mcp.tools import register_tools

logger = logging.getLogger(__name__)

LOOPER_PORT = os.getenv("LOOPER_JSON_PORT", "8088")
LOOPER_HOST = os.getenv("LOOPER_HOST", "127.0.0.1")
MCP_PORT = int(os.getenv("LOOPER_MCP_PORT", "3002"))
MCP_HOST = os.getenv("LOOPER_MCP_HOST", "localhost")

LOOPER_BIN = os.getenv(
    "LOOPER_BIN",
    str(Path.home() / "looperdooper" / "target" / "release" / "loopers"),
)

mcp_server = FastMCP("Looper MCP Server")
looper_client = LooperClient(host=LOOPER_HOST, port=int(LOOPER_PORT))

register_tools(mcp_server, looper_client)


def main():
    logging.basicConfig(level=logging.INFO)
    logger.info("Looper MCP Server starting on %s:%d", MCP_HOST, MCP_PORT)
    mcp_server.run(transport="sse", host=MCP_HOST, port=MCP_PORT)


if __name__ == "__main__":
    main()
