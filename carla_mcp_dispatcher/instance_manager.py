"""
Carla Instance Manager

Manages multiple Carla instances with unique JACK client names and MCP ports.
"""

import asyncio
import os
import subprocess
import logging
import json
from typing import Dict, List, Optional, Any
from pathlib import Path

from .config import DispatcherConfig
from .mcp_client import MCPClient

logger = logging.getLogger(__name__)


class CarlaInstance:
    """Represents a single Carla instance"""
    
    def __init__(
        self,
        instance_id: str,
        jack_name: str,
        mcp_port: int,
        channels: int = 2
    ):
        self.instance_id = instance_id
        self.jack_name = jack_name
        self.mcp_port = mcp_port
        self.channels = channels
        self.process: Optional[subprocess.Popen] = None
        self.mcp_client: Optional[MCPClient] = None
        self.is_ready = False
        
    def __repr__(self):
        return f"CarlaInstance({self.instance_id}, jack={self.jack_name}, mcp={self.mcp_port})"


class CarlaInstanceManager:
    """Manages multiple Carla instances"""
    
    def __init__(self, config: DispatcherConfig):
        self.config = config
        self.instances: Dict[str, CarlaInstance] = {}
        self._next_port = config.base_mcp_port
        self._lock = asyncio.Lock()
        
    def _get_next_mcp_port(self) -> int:
        """Get next available MCP port"""
        port = self._next_port
        self._next_port += 1
        return port
    
    def _get_jack_name(self, instance_id: str) -> str:
        """Generate JACK client name for instance"""
        return f"Carla-{instance_id}"
    
    async def create_instance(
        self,
        instance_id: str,
        channels: int = 2
    ) -> Dict[str, Any]:
        """Create a new Carla instance"""
        async with self._lock:
            # Check if instance already exists
            if instance_id in self.instances:
                return {
                    "success": False,
                    "message": f"Instance {instance_id} already exists"
                }
            
            # Check max instances limit
            if len(self.instances) >= self.config.max_instances:
                return {
                    "success": False,
                    "message": f"Maximum instances ({self.config.max_instances}) reached"
                }
            
            # Create instance
            jack_name = self._get_jack_name(instance_id)
            mcp_port = self._get_next_mcp_port()
            
            instance = CarlaInstance(
                instance_id=instance_id,
                jack_name=jack_name,
                mcp_port=mcp_port,
                channels=channels
            )
            
            # Start Carla process
            try:
                await self._start_carla_process(instance)
                self.instances[instance_id] = instance
                
                # Wait for MCP server to be ready
                await self._wait_for_mcp_ready(instance)
                
                return {
                    "success": True,
                    "jack_name": jack_name,
                    "mcp_port": mcp_port,
                    "message": f"Instance {instance_id} created successfully"
                }
                
            except Exception as e:
                logger.error(f"Failed to create instance {instance_id}: {e}")
                return {
                    "success": False,
                    "message": f"Failed to create instance: {str(e)}"
                }
    
    async def _start_carla_process(self, instance: CarlaInstance):
        """Start Carla process for instance"""
        # Find carla executable
        carla_path = self.config.carla_executable
        if not carla_path:
            # Try to find in common locations
            possible_paths = [
                "/usr/bin/carla",
                "/usr/local/bin/carla",
                str(Path.home() / ".local/bin/carla"),
                # Look for development version
                str(Path(__file__).parent.parent / "carla-mcp-fork/source/frontend/carla")
            ]
            
            for path in possible_paths:
                if Path(path).exists():
                    carla_path = path
                    break
            
            if not carla_path:
                raise RuntimeError("Could not find Carla executable")
        
        # Set up environment
        env = os.environ.copy()
        env["CARLA_CLIENT_NAME"] = instance.jack_name
        env["CARLA_MCP_PORT"] = str(instance.mcp_port)
        env["CARLA_NSM_NAME"] = instance.jack_name  # For NSM compatibility
        
        # Build command
        cmd = [
            carla_path,
            "--no-gui",  # Headless mode
            f"--client-name={instance.jack_name}",
        ]
        
        # Add channel configuration if needed
        if instance.channels > 2:
            # This would require custom Carla build or using patchbay mode
            logger.warning(f"Multi-channel support ({instance.channels}) requires custom configuration")
        
        logger.info(f"Starting Carla: {' '.join(cmd)}")
        logger.debug(f"Environment: CARLA_CLIENT_NAME={instance.jack_name}, CARLA_MCP_PORT={instance.mcp_port}")
        
        # Start process
        instance.process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
    
    async def _wait_for_mcp_ready(
        self,
        instance: CarlaInstance,
        timeout: float = 10.0
    ):
        """Wait for MCP server to be ready"""
        start_time = asyncio.get_event_loop().time()
        
        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                # Try to connect to MCP server
                instance.mcp_client = MCPClient(
                    host="127.0.0.1",
                    port=instance.mcp_port
                )
                
                # Test connection
                result = await instance.mcp_client.call_tool(
                    "test_carla_connection",
                    {}
                )
                
                if result.get("success"):
                    instance.is_ready = True
                    logger.info(f"Instance {instance.instance_id} MCP server ready")
                    return
                    
            except Exception as e:
                logger.debug(f"Waiting for MCP server: {e}")
            
            await asyncio.sleep(0.5)
        
        raise TimeoutError(f"MCP server did not start within {timeout} seconds")
    
    async def destroy_instance(self, instance_id: str) -> Dict[str, Any]:
        """Destroy a Carla instance"""
        async with self._lock:
            if instance_id not in self.instances:
                return {
                    "success": False,
                    "message": f"Instance {instance_id} not found"
                }
            
            instance = self.instances[instance_id]
            
            try:
                # Close MCP client
                if instance.mcp_client:
                    await instance.mcp_client.close()
                
                # Terminate process
                if instance.process:
                    instance.process.terminate()
                    try:
                        await asyncio.wait_for(
                            asyncio.create_subprocess_exec(
                                "wait", str(instance.process.pid)
                            ),
                            timeout=5.0
                        )
                    except asyncio.TimeoutError:
                        instance.process.kill()
                
                # Remove from instances
                del self.instances[instance_id]
                
                return {
                    "success": True,
                    "message": f"Instance {instance_id} destroyed"
                }
                
            except Exception as e:
                logger.error(f"Error destroying instance {instance_id}: {e}")
                return {
                    "success": False,
                    "message": f"Error destroying instance: {str(e)}"
                }
    
    def list_instances(self) -> List[Dict[str, Any]]:
        """List all active instances"""
        return [
            {
                "instance_id": inst.instance_id,
                "jack_name": inst.jack_name,
                "mcp_port": inst.mcp_port,
                "channels": inst.channels,
                "is_ready": inst.is_ready
            }
            for inst in self.instances.values()
        ]
    
    async def get_instance_status(self, instance_id: str) -> Dict[str, Any]:
        """Get detailed status of an instance"""
        if instance_id not in self.instances:
            return {
                "success": False,
                "message": f"Instance {instance_id} not found"
            }
        
        instance = self.instances[instance_id]
        
        # Get process status
        process_running = (
            instance.process is not None and
            instance.process.poll() is None
        )
        
        # Try to get Carla status via MCP
        carla_status = {}
        if instance.mcp_client and instance.is_ready:
            try:
                result = await instance.mcp_client.call_tool(
                    "get_engine_info",
                    {}
                )
                carla_status = result.get("data", {})
            except Exception as e:
                logger.error(f"Failed to get Carla status: {e}")
        
        return {
            "success": True,
            "instance_id": instance.instance_id,
            "jack_name": instance.jack_name,
            "mcp_port": instance.mcp_port,
            "channels": instance.channels,
            "process_running": process_running,
            "mcp_ready": instance.is_ready,
            "carla_status": carla_status
        }
    
    async def route_command(
        self,
        instance_id: str,
        tool_name: str,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Route a command to a specific instance"""
        if instance_id not in self.instances:
            return {
                "success": False,
                "message": f"Instance {instance_id} not found"
            }
        
        instance = self.instances[instance_id]
        
        if not instance.is_ready:
            return {
                "success": False,
                "message": f"Instance {instance_id} not ready"
            }
        
        if not instance.mcp_client:
            return {
                "success": False,
                "message": f"Instance {instance_id} has no MCP client"
            }
        
        try:
            # Route command to instance's MCP server
            return await instance.mcp_client.call_tool(tool_name, params)
            
        except Exception as e:
            logger.error(f"Error routing command to {instance_id}: {e}")
            return {
                "success": False,
                "message": f"Error routing command: {str(e)}"
            }
    
    async def shutdown_all(self):
        """Shutdown all instances"""
        logger.info("Shutting down all instances...")
        
        # Copy list to avoid modification during iteration
        instance_ids = list(self.instances.keys())
        
        for instance_id in instance_ids:
            await self.destroy_instance(instance_id)
        
        logger.info("All instances shut down")