"""
TCP server wrapper for MCP stdio transport
"""

import asyncio
import json
import logging
import threading
from typing import Optional
from .config import config

logger = logging.getLogger(__name__)

class MCPTCPServer:
    """TCP server that wraps MCP stdio communication"""
    
    def __init__(self, mcp_server, host: str = "localhost", port: int = 3001):
        self.mcp_server = mcp_server
        self.host = host
        self.port = port
        self.server = None
        self.clients = set()
        
    async def handle_client(self, reader, writer):
        """Handle a single client connection"""
        addr = writer.get_extra_info('peername')
        logger.info(f"Client connected from {addr}")
        self.clients.add(writer)
        
        try:
            while True:
                # Read line from client
                data = await reader.readline()
                if not data:
                    break
                    
                try:
                    # Parse JSON-RPC message
                    message = json.loads(data.decode().strip())
                    logger.debug(f"Received: {message}")
                    
                    # Process with MCP server (this is tricky with stdio transport)
                    # For now, send a basic response
                    response = {
                        "jsonrpc": "2.0",
                        "id": message.get("id"),
                        "result": {"status": "MCP server running in Carla"}
                    }
                    
                    # Send response
                    response_data = json.dumps(response) + "\n"
                    writer.write(response_data.encode())
                    await writer.drain()
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON from client: {e}")
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error handling client {addr}: {e}")
        finally:
            self.clients.discard(writer)
            writer.close()
            await writer.wait_closed()
            logger.info(f"Client {addr} disconnected")
    
    async def start_server(self):
        """Start the TCP server"""
        try:
            self.server = await asyncio.start_server(
                self.handle_client,
                self.host,
                self.port
            )
            
            addr = self.server.sockets[0].getsockname()
            logger.info(f"MCP TCP server started on {addr[0]}:{addr[1]}")
            
            async with self.server:
                await self.server.serve_forever()
                
        except Exception as e:
            logger.error(f"Failed to start TCP server: {e}")
    
    def start_in_thread(self):
        """Start the server in a separate thread"""
        def run_server():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.start_server())
            except Exception as e:
                logger.error(f"TCP server thread error: {e}")
            finally:
                loop.close()
        
        thread = threading.Thread(target=run_server, daemon=True, name="MCP-TCP-Server")
        thread.start()
        return thread