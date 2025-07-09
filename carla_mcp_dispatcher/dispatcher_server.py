#!/usr/bin/env python3
"""
Carla MCP Dispatcher Server

A centralized MCP server that manages multiple Carla instances,
routing commands to the appropriate instance based on loop/channel ID.
"""

import asyncio
import logging
from typing import Dict, Optional, Any
from fastmcp import FastMCP

from .instance_manager import CarlaInstanceManager
from .config import DispatcherConfig

logger = logging.getLogger(__name__)


class CarlaMCPDispatcher:
    """Central dispatcher for routing MCP commands to Carla instances"""
    
    def __init__(self, config: DispatcherConfig):
        self.config = config
        self.mcp = FastMCP("Carla MCP Dispatcher")
        self.instance_manager = CarlaInstanceManager(config)
        self._setup_tools()
        
    def _setup_tools(self):
        """Register all MCP tools for the dispatcher"""
        
        # Instance management tools
        @self.mcp.tool()
        async def create_instance(instance_id: str, channels: int = 2) -> Dict[str, Any]:
            """Create a new Carla instance with specified channel count"""
            result = await self.instance_manager.create_instance(instance_id, channels)
            return {
                "success": result["success"],
                "instance_id": instance_id,
                "jack_name": result.get("jack_name"),
                "mcp_port": result.get("mcp_port"),
                "message": result.get("message", "")
            }
        
        @self.mcp.tool()
        async def destroy_instance(instance_id: str) -> Dict[str, Any]:
            """Destroy a Carla instance"""
            result = await self.instance_manager.destroy_instance(instance_id)
            return {
                "success": result["success"],
                "instance_id": instance_id,
                "message": result.get("message", "")
            }
        
        @self.mcp.tool()
        async def list_instances() -> Dict[str, Any]:
            """List all active Carla instances"""
            instances = self.instance_manager.list_instances()
            return {
                "instances": instances,
                "count": len(instances)
            }
        
        # Plugin management (routed to specific instance)
        @self.mcp.tool()
        async def add_plugin(
            instance_id: str,
            plugin_type: str,
            plugin_name: str
        ) -> Dict[str, Any]:
            """Add a plugin to a specific Carla instance"""
            return await self.instance_manager.route_command(
                instance_id,
                "add_plugin_by_name",
                {
                    "plugin_name": plugin_name,
                    "plugin_type": plugin_type
                }
            )
        
        @self.mcp.tool()
        async def remove_plugin(
            instance_id: str,
            plugin_id: int
        ) -> Dict[str, Any]:
            """Remove a plugin from a specific Carla instance"""
            return await self.instance_manager.route_command(
                instance_id,
                "remove_plugin",
                {"plugin_id": plugin_id}
            )
        
        @self.mcp.tool()
        async def list_plugins(instance_id: str) -> Dict[str, Any]:
            """List all plugins in a specific Carla instance"""
            return await self.instance_manager.route_command(
                instance_id,
                "list_loaded_plugins",
                {}
            )
        
        # Parameter control
        @self.mcp.tool()
        async def set_parameter(
            instance_id: str,
            plugin_id: int,
            parameter_id: int,
            value: float
        ) -> Dict[str, Any]:
            """Set a plugin parameter in a specific Carla instance"""
            return await self.instance_manager.route_command(
                instance_id,
                "set_plugin_parameter",
                {
                    "plugin_id": plugin_id,
                    "parameter_id": parameter_id,
                    "value": value
                }
            )
        
        # MIDI control
        @self.mcp.tool()
        async def send_midi_note(
            instance_id: str,
            plugin_id: int,
            channel: int,
            note: int,
            velocity: int,
            duration_ms: Optional[int] = None
        ) -> Dict[str, Any]:
            """Send MIDI note to a plugin in a specific Carla instance"""
            # Send note on
            result = await self.instance_manager.route_command(
                instance_id,
                "send_midi_note_on",
                {
                    "plugin_id": plugin_id,
                    "channel": channel,
                    "note": note,
                    "velocity": velocity
                }
            )
            
            # If duration specified, schedule note off
            if duration_ms and result.get("success"):
                asyncio.create_task(self._delayed_note_off(
                    instance_id, plugin_id, channel, note, duration_ms
                ))
            
            return result
        
        async def _delayed_note_off(
            self,
            instance_id: str,
            plugin_id: int,
            channel: int,
            note: int,
            delay_ms: int
        ):
            """Send delayed note off"""
            await asyncio.sleep(delay_ms / 1000.0)
            await self.instance_manager.route_command(
                instance_id,
                "send_midi_note_off",
                {
                    "plugin_id": plugin_id,
                    "channel": channel,
                    "note": note
                }
            )
        
        # Status and monitoring
        @self.mcp.tool()
        async def get_instance_status(instance_id: str) -> Dict[str, Any]:
            """Get status of a specific Carla instance"""
            return await self.instance_manager.get_instance_status(instance_id)
        
        @self.mcp.tool()
        async def get_dispatcher_status() -> Dict[str, Any]:
            """Get overall dispatcher status"""
            instances = self.instance_manager.list_instances()
            return {
                "active_instances": len(instances),
                "max_instances": self.config.max_instances,
                "base_mcp_port": self.config.base_mcp_port,
                "instances": instances
            }
    
    async def run(self):
        """Run the dispatcher server"""
        logger.info(f"Starting Carla MCP Dispatcher on port {self.config.dispatcher_port}")
        await self.mcp.run(
            transport="sse",
            host="127.0.0.1",
            port=self.config.dispatcher_port
        )


async def main():
    """Main entry point"""
    logging.basicConfig(level=logging.INFO)
    
    config = DispatcherConfig()
    dispatcher = CarlaMCPDispatcher(config)
    
    try:
        await dispatcher.run()
    except KeyboardInterrupt:
        logger.info("Shutting down dispatcher...")
        await dispatcher.instance_manager.shutdown_all()


if __name__ == "__main__":
    asyncio.run(main())