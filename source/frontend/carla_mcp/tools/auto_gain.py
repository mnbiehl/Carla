"""
Auto-gain adjustment tools for Carla MCP Server

Provides automatic gain staging based on real-time monitoring.
"""

import asyncio
import time
from typing import Dict, List, Any, Optional
from fastmcp import FastMCP
from ..backend.backend_bridge import CarlaBackendBridge
from ..resources.realtime_monitoring import monitoring_stream

# Global backend bridge instance - will be initialized in main.py
backend_bridge: CarlaBackendBridge = None


class AutoGainManager:
    """Manages automatic gain adjustments for plugins"""
    
    def __init__(self, bridge: CarlaBackendBridge):
        self.bridge = bridge
        self.enabled = False
        self.adjustment_task: Optional[asyncio.Task] = None
        self.plugin_gains: Dict[int, float] = {}  # Track current gain adjustments
        
    async def start(self):
        """Start auto-gain adjustment"""
        if not self.enabled:
            self.enabled = True
            self.adjustment_task = asyncio.create_task(self._adjustment_loop())
            
    async def stop(self):
        """Stop auto-gain adjustment"""
        self.enabled = False
        if self.adjustment_task:
            await self.adjustment_task
            
    async def _adjustment_loop(self):
        """Main loop that applies gain adjustments"""
        while self.enabled:
            try:
                if not monitoring_stream or not self.bridge.is_engine_running():
                    await asyncio.sleep(1.0)
                    continue
                    
                # Subscribe to monitoring events
                queue = monitoring_stream.subscribe()
                
                try:
                    while self.enabled:
                        # Wait for events
                        try:
                            event_data = await asyncio.wait_for(queue.get(), timeout=5.0)
                        except asyncio.TimeoutError:
                            continue
                            
                        # Process events
                        if event_data.get("type") == "peak_levels":
                            await self._process_peak_events(event_data.get("events", []))
                            
                finally:
                    monitoring_stream.unsubscribe(queue)
                    
            except Exception as e:
                # Log error but keep running
                await asyncio.sleep(1.0)
                
    async def _process_peak_events(self, events: List[Dict[str, Any]]):
        """Process peak events and apply gain adjustments"""
        adjustments_to_make = []
        
        for event in events:
            plugin_id = event.get("plugin_id")
            suggested_gain = event.get("suggested_gain")
            is_clipping = event.get("is_clipping", False)
            
            if plugin_id is None:
                continue
                
            # Handle clipping immediately
            if is_clipping and plugin_id not in self.plugin_gains:
                # Emergency gain reduction
                adjustments_to_make.append({
                    "plugin_id": plugin_id,
                    "gain_db": -6.0,
                    "reason": "clipping_protection"
                })
                self.plugin_gains[plugin_id] = -6.0
                
            # Apply suggested gain if significant
            elif suggested_gain is not None and abs(suggested_gain) > 1.0:
                current_gain = self.plugin_gains.get(plugin_id, 0.0)
                new_gain = current_gain + suggested_gain
                
                # Limit total gain adjustment
                new_gain = max(-24.0, min(12.0, new_gain))
                
                if abs(new_gain - current_gain) > 0.5:
                    adjustments_to_make.append({
                        "plugin_id": plugin_id,
                        "gain_db": new_gain,
                        "reason": "level_optimization"
                    })
                    self.plugin_gains[plugin_id] = new_gain
                    
        # Apply adjustments
        if adjustments_to_make:
            await self._apply_gain_adjustments(adjustments_to_make)
            
    async def _apply_gain_adjustments(self, adjustments: List[Dict[str, Any]]):
        """Apply gain adjustments to plugins"""
        for adj in adjustments:
            plugin_id = adj["plugin_id"]
            gain_db = adj["gain_db"]
            
            try:
                # Get current plugin info
                plugin_info = self.bridge.host.get_plugin_info(plugin_id)
                if not plugin_info:
                    continue
                    
                # Find volume/gain parameter
                param_count = self.bridge.host.get_parameter_count(plugin_id)
                volume_param_id = None
                
                for i in range(param_count):
                    param_info = self.bridge.host.get_parameter_info(plugin_id, i)
                    if param_info and param_info.get("name", "").lower() in ["volume", "gain", "level", "output"]:
                        volume_param_id = i
                        break
                        
                if volume_param_id is not None:
                    # Convert dB to linear
                    linear_gain = 10 ** (gain_db / 20.0)
                    
                    # Apply adjustment
                    self.bridge.host.set_parameter_value(plugin_id, volume_param_id, linear_gain)
                    
            except Exception as e:
                # Log error but continue
                pass


# Global auto-gain manager instance
auto_gain_manager: Optional[AutoGainManager] = None


def register_auto_gain_tools(mcp: FastMCP, bridge: CarlaBackendBridge):
    """Register auto-gain adjustment tools"""
    global backend_bridge, auto_gain_manager
    backend_bridge = bridge
    auto_gain_manager = AutoGainManager(bridge)
    
    @mcp.tool()
    async def enable_auto_gain() -> str:
        """
        Enable automatic gain adjustment based on real-time monitoring
        
        This will continuously monitor plugin levels and automatically adjust
        gains to maintain optimal levels and prevent clipping.
        
        Returns:
            Status message
        """
        if not auto_gain_manager:
            return "Error: Auto-gain manager not initialized"
            
        if not monitoring_stream or not monitoring_stream.is_running:
            # Start monitoring first
            await monitoring_stream.start()
            
        await auto_gain_manager.start()
        
        return "Auto-gain adjustment enabled - monitoring levels and adjusting gains automatically"
    
    @mcp.tool()
    async def disable_auto_gain() -> str:
        """
        Disable automatic gain adjustment
        
        Returns:
            Status message
        """
        if not auto_gain_manager:
            return "Error: Auto-gain manager not initialized"
            
        await auto_gain_manager.stop()
        
        return "Auto-gain adjustment disabled"
    
    @mcp.tool()
    def get_auto_gain_status() -> str:
        """
        Get current status of auto-gain system
        
        Returns:
            JSON string with status information
        """
        import json
        
        if not auto_gain_manager:
            return json.dumps({"error": "Auto-gain manager not initialized"})
            
        status = {
            "enabled": auto_gain_manager.enabled,
            "plugins_adjusted": len(auto_gain_manager.plugin_gains),
            "current_adjustments": {
                str(pid): f"{gain:+.1f} dB"
                for pid, gain in auto_gain_manager.plugin_gains.items()
            }
        }
        
        if monitoring_stream:
            status["monitoring"] = {
                "active": monitoring_stream.is_running,
                "target_level_db": monitoring_stream.auto_gain.target_level_db,
                "headroom_db": monitoring_stream.auto_gain.headroom_db
            }
            
        return json.dumps(status, indent=2)
    
    @mcp.tool()
    def reset_auto_gain_adjustments() -> str:
        """
        Reset all auto-gain adjustments to 0dB
        
        Returns:
            Status message
        """
        if not auto_gain_manager:
            return "Error: Auto-gain manager not initialized"
            
        # Clear tracked gains
        auto_gain_manager.plugin_gains.clear()
        
        # Reset all plugin volumes to unity
        try:
            plugin_count = backend_bridge.host.get_current_plugin_count()
            reset_count = 0
            
            for plugin_id in range(plugin_count):
                # Set volume to 1.0 (unity gain)
                try:
                    backend_bridge.host.set_volume(plugin_id, 1.0)
                    reset_count += 1
                except:
                    pass
                    
            return f"Reset {reset_count} plugin volumes to unity gain (0dB)"
            
        except Exception as e:
            return f"Error resetting gains: {str(e)}"
    
    @mcp.tool()
    def configure_auto_gain(
        target_level_db: float = -18.0,
        headroom_db: float = 6.0,
        attack_time: float = 0.1,
        release_time: float = 2.0
    ) -> str:
        """
        Configure auto-gain controller parameters
        
        Args:
            target_level_db: Target output level in dB (default -18.0)
            headroom_db: Safety headroom in dB (default 6.0)
            attack_time: Time to respond to level increases in seconds (default 0.1)
            release_time: Time to average levels in seconds (default 2.0)
            
        Returns:
            Configuration status as JSON string
        """
        import json
        
        if not monitoring_stream:
            return json.dumps({"error": "Monitoring not initialized"})
            
        controller = monitoring_stream.auto_gain
        
        # Update parameters
        controller.target_level_db = target_level_db
        controller.headroom_db = headroom_db
        controller.attack_time = attack_time
        controller.release_time = release_time
        
        return json.dumps({
            "status": "configured",
            "target_level_db": controller.target_level_db,
            "headroom_db": controller.headroom_db,
            "attack_time": controller.attack_time,
            "release_time": controller.release_time
        }, indent=2)
    
    @mcp.tool()
    async def analyze_gain_staging(duration_seconds: float = 5.0) -> str:
        """
        Analyze gain staging over a period of time and provide recommendations
        
        Args:
            duration_seconds: How long to analyze (default 5 seconds)
            
        Returns:
            JSON string with analysis results and recommendations
        """
        import json
        import math
        
        if not monitoring_stream:
            return json.dumps({"error": "Monitoring not initialized"})
            
        # Ensure monitoring is running
        if not monitoring_stream.is_running:
            await monitoring_stream.start()
            
        # Subscribe to events
        queue = monitoring_stream.subscribe()
        plugin_data: Dict[int, List[float]] = {}
        start_time = time.time()
        
        try:
            while time.time() - start_time < duration_seconds:
                try:
                    event_data = await asyncio.wait_for(queue.get(), timeout=1.0)
                    
                    if event_data.get("type") == "peak_levels":
                        for event in event_data.get("events", []):
                            plugin_id = event.get("plugin_id")
                            output_peak = event.get("output_peak", 0.0)
                            
                            if plugin_id not in plugin_data:
                                plugin_data[plugin_id] = []
                            plugin_data[plugin_id].append(output_peak)
                            
                except asyncio.TimeoutError:
                    continue
                    
        finally:
            monitoring_stream.unsubscribe(queue)
            
        # Analyze collected data
        analysis = {
            "duration_seconds": duration_seconds,
            "plugins_analyzed": len(plugin_data),
            "recommendations": []
        }
        
        for plugin_id, peaks in plugin_data.items():
            if not peaks:
                continue
                
            # Get plugin name
            try:
                plugin_info = backend_bridge.host.get_plugin_info(plugin_id)
                plugin_name = plugin_info.get("name", f"Plugin {plugin_id}") if plugin_info else f"Plugin {plugin_id}"
            except:
                plugin_name = f"Plugin {plugin_id}"
                
            # Calculate statistics
            max_peak = max(peaks)
            avg_peak = sum(peaks) / len(peaks)
            
            # Convert to dB
            def to_db(value):
                if value <= 0:
                    return -96.0
                return 20 * math.log10(value)
                
            max_peak_db = to_db(max_peak)
            avg_peak_db = to_db(avg_peak)
            
            # Generate recommendations
            plugin_analysis = {
                "plugin_id": plugin_id,
                "plugin_name": plugin_name,
                "max_peak_db": round(max_peak_db, 1),
                "avg_peak_db": round(avg_peak_db, 1),
                "samples": len(peaks)
            }
            
            if max_peak > 1.0:
                plugin_analysis["status"] = "CLIPPING"
                plugin_analysis["recommendation"] = f"Reduce gain by at least {abs(max_peak_db):.1f} dB"
            elif max_peak_db > -3.0:
                plugin_analysis["status"] = "TOO_HOT"
                plugin_analysis["recommendation"] = f"Reduce gain by {abs(-6.0 - max_peak_db):.1f} dB for headroom"
            elif avg_peak_db < -40.0:
                plugin_analysis["status"] = "TOO_QUIET"
                plugin_analysis["recommendation"] = f"Increase gain by {abs(avg_peak_db + 18.0):.1f} dB"
            elif avg_peak_db > -12.0:
                plugin_analysis["status"] = "LOUD"
                plugin_analysis["recommendation"] = f"Consider reducing gain by {abs(-18.0 - avg_peak_db):.1f} dB"
            else:
                plugin_analysis["status"] = "GOOD"
                plugin_analysis["recommendation"] = "Levels are appropriate"
                
            analysis["recommendations"].append(plugin_analysis)
            
        return json.dumps(analysis, indent=2)