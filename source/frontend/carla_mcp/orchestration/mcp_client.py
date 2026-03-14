"""MCP client for parent -> child Carla instance communication."""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ChainMCPClient:
    """Connects to a child Carla's MCP server to invoke tools."""

    def __init__(self, port: int, host: str = "127.0.0.1"):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any] = None) -> Dict[str, Any]:
        """Call a tool on the child MCP server via JSON-RPC."""
        import aiohttp

        async with aiohttp.ClientSession() as session:
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments or {}},
                "id": 1,
            }
            async with session.post(f"{self.base_url}/mcp/v1", json=payload) as resp:
                if resp.status != 200:
                    raise ConnectionError(f"Child MCP returned {resp.status}")
                return await resp.json()

    async def health_check(self) -> bool:
        """Check if the child MCP server is reachable."""
        import aiohttp

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/sse", timeout=aiohttp.ClientTimeout(total=2)
                ) as resp:
                    return resp.status == 200
        except Exception:
            return False
