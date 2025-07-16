"""
Real-time monitoring with SSE (Server-Sent Events) for Carla MCP Server

Provides continuous monitoring of audio levels with automatic gain adjustment.
"""

import asyncio
import json
import time
from typing import Dict, List, Any, Optional, Set
from collections import deque
from dataclasses import dataclass
from datetime import datetime
import math

from fastmcp import FastMCP
from ..backend.backend_bridge import CarlaBackendBridge

# Global backend bridge instance - will be initialized in main.py
backend_bridge: CarlaBackendBridge = None


@dataclass
class PeakEvent:
    """Represents a peak level event"""
    plugin_id: int
    plugin_name: str
    timestamp: float
    input_peak: float
    output_peak: float
    is_clipping: bool
    suggested_gain: Optional[float] = None


class AutoGainController:
    """Automatic gain adjustment controller"""
    
    def __init__(self):
        self.target_level_db = -18.0  # Standard mixing level
        self.headroom_db = 6.0  # Safety headroom
        self.attack_time = 0.1  # seconds
        self.release_time = 2.0  # seconds
        self.history: Dict[int, deque] = {}  # Plugin ID -> peak history
        self.last_adjustment: Dict[int, float] = {}  # Plugin ID -> last adjustment time
        
    def calculate_gain_adjustment(self, plugin_id: int, current_peak_db: float) -> Optional[float]:
        """Calculate required gain adjustment based on peak levels"""
        now = time.time()
        
        # Initialize history if needed
        if plugin_id not in self.history:
            self.history[plugin_id] = deque(maxlen=100)
            
        # Add to history
        self.history[plugin_id].append((now, current_peak_db))
        
        # Check if we should make an adjustment
        if plugin_id in self.last_adjustment:
            time_since_last = now - self.last_adjustment[plugin_id]
            if time_since_last < self.attack_time:
                return None
                
        # Calculate average peak over window
        recent_peaks = [peak for timestamp, peak in self.history[plugin_id] 
                       if now - timestamp < self.release_time]
        
        if not recent_peaks:
            return None
            
        avg_peak_db = sum(recent_peaks) / len(recent_peaks)
        
        # Determine if adjustment needed
        if avg_peak_db > -3.0:  # Too hot, reduce gain
            adjustment = self.target_level_db - avg_peak_db
            self.last_adjustment[plugin_id] = now
            return adjustment
        elif avg_peak_db < -30.0 and len(recent_peaks) > 10:  # Too quiet
            adjustment = (self.target_level_db - self.headroom_db) - avg_peak_db
            self.last_adjustment[plugin_id] = now
            return adjustment
            
        return None


class MonitoringEventStream:
    """Manages real-time monitoring event stream"""
    
    def __init__(self, bridge: CarlaBackendBridge):
        self.bridge = bridge
        self.auto_gain = AutoGainController()
        self.subscribers: Set[asyncio.Queue] = set()
        self.monitoring_task: Optional[asyncio.Task] = None
        self.is_running = False
        
    async def start(self):
        """Start the monitoring loop"""
        if not self.is_running:
            self.is_running = True
            self.monitoring_task = asyncio.create_task(self._monitoring_loop())
            
    async def stop(self):
        """Stop the monitoring loop"""
        self.is_running = False
        if self.monitoring_task:
            await self.monitoring_task
            
    def subscribe(self) -> asyncio.Queue:
        """Subscribe to monitoring events"""
        queue = asyncio.Queue()
        self.subscribers.add(queue)
        return queue
        
    def unsubscribe(self, queue: asyncio.Queue):
        """Unsubscribe from monitoring events"""
        self.subscribers.discard(queue)
        
    async def _monitoring_loop(self):
        """Main monitoring loop that checks levels and sends events"""
        while self.is_running:
            try:
                if not self.bridge or not self.bridge.is_engine_running():
                    await asyncio.sleep(1.0)
                    continue
                    
                # Get current levels
                plugin_count = self.bridge.host.get_current_plugin_count()
                events = []
                
                for plugin_id in range(plugin_count):
                    try:
                        # Get plugin info
                        plugin_info = self.bridge.host.get_plugin_info(plugin_id)
                        if not plugin_info:
                            continue
                            
                        plugin_name = plugin_info['name']
                        
                        # Get peak values
                        input_left = self.bridge.get_input_peak_value(plugin_id, True)
                        input_right = self.bridge.get_input_peak_value(plugin_id, False)
                        output_left = self.bridge.get_output_peak_value(plugin_id, True)
                        output_right = self.bridge.get_output_peak_value(plugin_id, False)
                        
                        # Get max peaks
                        input_peak = max(input_left, input_right)
                        output_peak = max(output_left, output_right)
                        
                        # Check for clipping
                        is_clipping = input_peak > 1.0 or output_peak > 1.0
                        
                        # Convert to dB
                        def to_db(value):
                            if value <= 0:
                                return -96.0
                            return 20 * math.log10(value)
                            
                        output_peak_db = to_db(output_peak)
                        
                        # Calculate auto-gain if needed
                        gain_adjustment = None
                        if is_clipping or abs(output_peak_db - self.auto_gain.target_level_db) > 12.0:
                            gain_adjustment = self.auto_gain.calculate_gain_adjustment(
                                plugin_id, output_peak_db
                            )
                            
                        # Create event if significant
                        if is_clipping or output_peak > 0.1 or gain_adjustment is not None:
                            event = PeakEvent(
                                plugin_id=plugin_id,
                                plugin_name=plugin_name,
                                timestamp=time.time(),
                                input_peak=input_peak,
                                output_peak=output_peak,
                                is_clipping=is_clipping,
                                suggested_gain=gain_adjustment
                            )
                            events.append(event)
                            
                    except Exception as e:
                        # Log error but continue
                        pass
                        
                # Send events to subscribers
                if events:
                    await self._broadcast_events(events)
                    
                # Sleep for monitoring interval (50ms for 20Hz updates)
                await asyncio.sleep(0.05)
                
            except Exception as e:
                # Log error but keep monitoring
                await asyncio.sleep(1.0)
                
    async def _broadcast_events(self, events: List[PeakEvent]):
        """Broadcast events to all subscribers"""
        # Convert events to JSON
        event_data = {
            "type": "peak_levels",
            "timestamp": datetime.utcnow().isoformat(),
            "events": [
                {
                    "plugin_id": e.plugin_id,
                    "plugin_name": e.plugin_name,
                    "timestamp": e.timestamp,
                    "input_peak": round(e.input_peak, 4),
                    "output_peak": round(e.output_peak, 4),
                    "is_clipping": e.is_clipping,
                    "suggested_gain": round(e.suggested_gain, 2) if e.suggested_gain else None
                }
                for e in events
            ]
        }
        
        # Send to all subscribers
        dead_queues = []
        for queue in self.subscribers:
            try:
                await queue.put(event_data)
            except:
                dead_queues.append(queue)
                
        # Clean up dead queues
        for queue in dead_queues:
            self.unsubscribe(queue)


# Global monitoring stream instance
monitoring_stream: Optional[MonitoringEventStream] = None


def register_realtime_monitoring(mcp: FastMCP, bridge: CarlaBackendBridge):
    """Register real-time monitoring resources with SSE support"""
    global backend_bridge, monitoring_stream
    backend_bridge = bridge
    monitoring_stream = MonitoringEventStream(bridge)
    
    @mcp.resource("monitoring://realtime/subscribe")
    async def subscribe_to_monitoring() -> Dict[str, Any]:
        """
        Subscribe to real-time monitoring events
        
        Returns SSE endpoint information for connecting to the event stream.
        """
        if not monitoring_stream:
            return {"error": "Monitoring not initialized"}
            
        # Ensure monitoring is running
        await monitoring_stream.start()
        
        return {
            "status": "subscribed",
            "sse_endpoint": "/monitoring/events",
            "update_frequency_hz": 20,
            "features": {
                "peak_detection": True,
                "clipping_alerts": True,
                "auto_gain_suggestions": True
            }
        }
    
    @mcp.resource("monitoring://realtime/auto_gain/status")
    def get_auto_gain_status() -> Dict[str, Any]:
        """Get current auto-gain controller status"""
        if not monitoring_stream:
            return {"error": "Monitoring not initialized"}
            
        controller = monitoring_stream.auto_gain
        
        return {
            "enabled": monitoring_stream.is_running,
            "target_level_db": controller.target_level_db,
            "headroom_db": controller.headroom_db,
            "attack_time": controller.attack_time,
            "release_time": controller.release_time,
            "plugins_monitored": len(controller.history),
            "recent_adjustments": len(controller.last_adjustment)
        }
    
    # Note: Configuration should be done via tools, not resources
    # Resources in MCP are read-only endpoints
    # Use the auto_gain tools to configure the controller


def create_sse_endpoint(mcp: FastMCP):
    """Create SSE endpoint for real-time monitoring events"""
    from starlette.responses import StreamingResponse
    from starlette.requests import Request
    
    async def monitoring_events(request: Request):
        """SSE endpoint that streams monitoring events"""
        if not monitoring_stream:
            return StreamingResponse(
                iter(["data: {\"error\": \"Monitoring not initialized\"}\n\n"]),
                media_type="text/event-stream"
            )
        
        # Subscribe to events
        queue = monitoring_stream.subscribe()
        
        async def event_generator():
            """Generate SSE events"""
            try:
                # Send initial connection event
                yield f"data: {json.dumps({'type': 'connected', 'timestamp': datetime.utcnow().isoformat()})}\n\n"
                
                # Stream events
                while True:
                    try:
                        # Wait for event with timeout
                        event = await asyncio.wait_for(queue.get(), timeout=30.0)
                        yield f"data: {json.dumps(event)}\n\n"
                    except asyncio.TimeoutError:
                        # Send keepalive
                        yield f"data: {json.dumps({'type': 'keepalive', 'timestamp': datetime.utcnow().isoformat()})}\n\n"
                        
            except asyncio.CancelledError:
                # Clean up on disconnect
                monitoring_stream.unsubscribe(queue)
                raise
                
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no"  # Disable nginx buffering
            }
        )
    
    return monitoring_events