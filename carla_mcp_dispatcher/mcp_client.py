"""
MCP Client for communicating with Carla MCP servers
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional
import aiohttp

logger = logging.getLogger(__name__)


class MCPClient:
    """Client for communicating with MCP servers via SSE"""
    
    def __init__(self, host: str = "127.0.0.1", port: int = 3001):
        self.host = host
        self.port = port
        self.base_url = f"http://{host}:{port}"
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        
    async def close(self):
        """Close the client session"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def call_tool(
        self,
        tool_name: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Call an MCP tool"""
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        # MCP SSE protocol uses JSON-RPC format
        request_data = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": params
            },
            "id": 1
        }
        
        try:
            # Send request
            async with self.session.post(
                f"{self.base_url}/sse",
                json=request_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"MCP request failed: {response.status} - {error_text}")
                    return {
                        "success": False,
                        "message": f"Request failed: {response.status}"
                    }
                
                # Parse SSE response
                result = await self._parse_sse_response(response)
                return result
                
        except aiohttp.ClientError as e:
            logger.error(f"MCP client error: {e}")
            return {
                "success": False,
                "message": f"Client error: {str(e)}"
            }
        except Exception as e:
            logger.error(f"Unexpected error calling MCP tool: {e}")
            return {
                "success": False,
                "message": f"Unexpected error: {str(e)}"
            }
    
    async def _parse_sse_response(
        self,
        response: aiohttp.ClientResponse
    ) -> Dict[str, Any]:
        """Parse SSE response from MCP server"""
        result = {}
        
        async for line in response.content:
            line = line.decode('utf-8').strip()
            
            if line.startswith('data: '):
                data_str = line[6:]  # Remove 'data: ' prefix
                
                try:
                    data = json.loads(data_str)
                    
                    # Handle JSON-RPC response
                    if "result" in data:
                        return data["result"]
                    elif "error" in data:
                        return {
                            "success": False,
                            "message": data["error"].get("message", "Unknown error"),
                            "error": data["error"]
                        }
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse SSE data: {e}")
        
        # If we get here, no valid response was found
        return {
            "success": False,
            "message": "No valid response received"
        }
    
    async def test_connection(self) -> bool:
        """Test if MCP server is reachable"""
        try:
            result = await self.call_tool("test_carla_connection", {})
            return result.get("success", False)
        except Exception:
            return False