"""
Plugin management tools for Carla MCP Server

Tools for controlling plugin activation, volume, and basic properties,
plus comprehensive plugin discovery capabilities.
"""

import json
from typing import Union, Optional
from fastmcp import FastMCP
from ..backend.backend_bridge import CarlaBackendBridge
from ..discovery.plugin_discoverer import PluginDiscoverer
from ..utils.error_handler import get_error_handler

# Global instances - will be initialized in main.py
backend_bridge: CarlaBackendBridge = None
plugin_discoverer: Optional[PluginDiscoverer] = None


def register_plugin_tools(mcp: FastMCP, bridge: CarlaBackendBridge):
    """Register plugin management tools with the MCP server"""
    global backend_bridge, plugin_discoverer
    backend_bridge = bridge
    
    # Initialize plugin discoverer
    try:
        plugin_discoverer = PluginDiscoverer()
    except Exception as e:
        print(f"⚠️  Plugin discovery not available: {e}")
        plugin_discoverer = None
    
    @mcp.tool()
    def set_plugin_active(plugin_id: int, active: bool) -> str:
        """
        Activate or deactivate a plugin in Carla
        
        Args:
            plugin_id: The ID of the plugin (0-based index)
            active: True to activate, False to deactivate
        """
        if backend_bridge.set_plugin_active(plugin_id, active):
            status = "activated" if active else "deactivated"
            return f"✅ Plugin {plugin_id} {status}"
        else:
            return f"❌ Failed to set plugin {plugin_id} active state"
    
    @mcp.tool()
    def set_plugin_volume(plugin_id: int, volume: float) -> str:
        """
        Set the volume of a plugin in Carla
        
        Args:
            plugin_id: The ID of the plugin (0-based index)
            volume: Volume level (0.0 to 1.27, where 1.0 = unity gain)
        """
        if not (0.0 <= volume <= 1.27):
            return "❌ Volume must be between 0.0 and 1.27"
        
        if backend_bridge.set_plugin_volume(plugin_id, volume):
            return f"✅ Set plugin {plugin_id} volume to {volume:.2f}"
        else:
            return f"❌ Failed to set plugin {plugin_id} volume"
    
    @mcp.tool()
    def list_loaded_plugins() -> str:
        """
        List all currently loaded plugins in Carla
        
        Returns:
            JSON string with plugin information
        """
        if backend_bridge:
            try:
                plugin_count = backend_bridge.get_current_plugin_count()
                plugins = []
                
                for i in range(plugin_count):
                    plugin_info = backend_bridge.get_plugin_info(i)
                    if plugin_info:
                        plugins.append({
                            'id': i,
                            'name': plugin_info.get('name', 'Unknown'),
                            'type': plugin_info.get('type', 0),
                            'category': plugin_info.get('category', 0),
                            'filename': plugin_info.get('filename', ''),
                            'label': plugin_info.get('label', ''),
                            'maker': plugin_info.get('maker', ''),
                            'unique_id': plugin_info.get('unique_id', 0)
                        })
                
                result = {
                    'plugin_count': plugin_count,
                    'max_plugins': backend_bridge.get_max_plugin_number(),
                    'plugins': plugins
                }
                
                return json.dumps(result, indent=2)
                
            except Exception as e:
                return f"❌ Error listing plugins via backend API: {e}"
        else:
            return "❌ Backend API not available. Plugin listing requires direct backend access."
    
    @mcp.tool()
    def add_plugin(plugin_type: str, filename: str, name: str = "", label: str = "") -> str:
        """
        Add a plugin to Carla
        
        Args:
            plugin_type: Type of plugin (lv2, vst2, vst3, ladspa, etc.)
            filename: Path to plugin file or URI
            name: Display name for the plugin (optional)
            label: Plugin label/identifier (optional)
            
        Returns:
            Status message
        """
        # Check if engine is running
        if not backend_bridge.is_engine_running():
            return "❌ Cannot add plugin: Carla engine is not running"
        
        # Use provided name or derive from filename
        display_name = name or filename.split('/')[-1].split('.')[0]
        plugin_label = label or display_name.lower().replace(' ', '_')
        
        try:
            success = backend_bridge.add_plugin(
                plugin_type=plugin_type,
                filename=filename,
                name=display_name,
                label=plugin_label,
                unique_id=0
            )
            
            if success:
                return f"Successfully added {plugin_type} plugin: {display_name}"
            else:
                # Get detailed error from backend bridge
                carla_error = "Unknown error"
                try:
                    if hasattr(backend_bridge, 'host') and hasattr(backend_bridge.host, 'get_last_error'):
                        carla_error = backend_bridge.host.get_last_error() or "No error details available"
                except Exception as e:
                    carla_error = f"Could not get error details: {e}"
                
                # Return detailed error information with Carla's actual error
                error_details = [
                    f"Failed to add plugin: {display_name}",
                    f"Plugin Type: {plugin_type}",
                    f"File Path: {filename}",
                    f"Plugin Name: {display_name}",
                    f"Plugin Label: {plugin_label}",
                    "",
                    f"Carla Error: {carla_error}",
                    "",
                    "Common Solutions:",
                    "- For LV2 plugins: Use LV2 URI instead of directory path",
                    "- For LADSPA plugins: Use .so file path with plugin label",
                    "- Check plugin file exists and is readable",
                    "- Verify plugin dependencies are installed"
                ]
                return "\n".join(error_details)
                
        except Exception as e:
            import traceback
            error_details = [
                f"Exception adding plugin: {display_name}",
                f"Plugin Type: {plugin_type}",
                f"File Path: {filename}",
                f"Plugin Name: {display_name}",
                f"Plugin Label: {plugin_label}",
                "",
                f"Exception Type: {type(e).__name__}",
                f"Exception Message: {str(e)}",
                "",
                "Full Traceback:",
                traceback.format_exc()
            ]
            return "\n".join(error_details)
    
    @mcp.tool()
    def remove_plugin(plugin_id: int) -> str:
        """
        Remove a plugin from Carla
        
        Args:
            plugin_id: ID of the plugin to remove (0-based index)
            
        Returns:
            Status message
        """
        if not backend_bridge:
            return "❌ Backend API not available. Plugin removal requires direct backend access."
        
        try:
            # Get plugin info before removing for better feedback
            plugin_info = backend_bridge.get_plugin_info(plugin_id)
            plugin_name = plugin_info.get('name', f'Plugin {plugin_id}') if plugin_info else f'Plugin {plugin_id}'
            
            success = backend_bridge.remove_plugin(plugin_id)
            
            if success:
                return f"✅ Successfully removed plugin: {plugin_name}"
            else:
                return f"❌ Failed to remove plugin: {plugin_name}"
                
        except Exception as e:
            return f"❌ Error removing plugin {plugin_id}: {e}"
    
    @mcp.tool()
    def remove_all_plugins() -> str:
        """
        Remove all plugins from Carla
        
        Returns:
            Status message
        """
        if not backend_bridge:
            return "❌ Backend API not available. Plugin removal requires direct backend access."
        
        try:
            plugin_count = backend_bridge.get_current_plugin_count()
            
            if plugin_count == 0:
                return "ℹ️ No plugins to remove"
            
            success = backend_bridge.remove_all_plugins()
            
            if success:
                return f"✅ Successfully removed all {plugin_count} plugins"
            else:
                return "❌ Failed to remove all plugins"
                
        except Exception as e:
            return f"❌ Error removing all plugins: {e}"
    
    @mcp.tool()
    def get_plugin_info(plugin_id: int) -> str:
        """
        Get detailed information about a specific plugin
        
        Args:
            plugin_id: ID of the plugin (0-based index)
            
        Returns:
            JSON string with detailed plugin information
        """
        if not backend_bridge:
            return "❌ Backend API not available. Plugin info requires direct backend access."
        
        try:
            plugin_info = backend_bridge.get_plugin_info(plugin_id)
            
            if not plugin_info:
                return f"❌ Plugin {plugin_id} not found or not loaded"
            
            return json.dumps(plugin_info, indent=2)
            
        except Exception as e:
            return f"❌ Error getting plugin info for {plugin_id}: {e}"
    
    # ============================================================================
    # Plugin Discovery Tools
    # ============================================================================
    
    @mcp.tool()
    def discover_all_plugins(force_refresh: bool = False) -> str:
        """
        Discover all available plugins on the system
        
        Args:
            force_refresh: Force rediscovery even if cache is valid
            
        Returns:
            JSON string with discovery results
        """
        if not plugin_discoverer:
            return "❌ Plugin discovery not available. Carla discovery tool may not be installed."
        
        try:
            results = plugin_discoverer.discover_all_plugins(force_refresh)
            total_plugins = sum(results.values())
            
            return json.dumps({
                'status': 'success',
                'total_plugins': total_plugins,
                'by_type': results,
                'message': f"✅ Discovered {total_plugins} plugins"
            }, indent=2)
            
        except Exception as e:
            return f"❌ Error during plugin discovery: {e}"
    
    @mcp.tool()
    def list_available_plugins(plugin_type: Optional[str] = None, category: Optional[str] = None, limit: int = 50) -> str:
        """
        List available plugins with optional filtering
        
        Args:
            plugin_type: Filter by plugin type (lv2, ladspa, vst2, vst3)
            category: Filter by category (eq, synth, delay, etc.)
            limit: Maximum number of plugins to return
            
        Returns:
            JSON string with plugin list
        """
        if not plugin_discoverer:
            return "❌ Plugin discovery not available"
        
        try:
            database = plugin_discoverer.get_database()
            
            # Get all plugins
            plugins = database.get_all_plugins()
            
            # Apply filters
            if plugin_type:
                plugins = [p for p in plugins if p.plugin_type.lower() == plugin_type.lower()]
            
            if category:
                plugins = [p for p in plugins if p.category.lower() == category.lower()]
            
            # Limit results
            plugins = plugins[:limit]
            
            # Convert to serializable format
            plugin_list = []
            for plugin in plugins:
                plugin_list.append({
                    'name': plugin.name,
                    'maker': plugin.maker,
                    'category': plugin.category,
                    'type': plugin.plugin_type,
                    'path': plugin.plugin_path,
                    'audio_ins': plugin.audio_ins,
                    'audio_outs': plugin.audio_outs,
                    'midi_ins': plugin.midi_ins,
                    'midi_outs': plugin.midi_outs,
                    'parameters': plugin.parameters_ins
                })
            
            return json.dumps({
                'plugins': plugin_list,
                'total_shown': len(plugin_list),
                'filters': {
                    'type': plugin_type,
                    'category': category,
                    'limit': limit
                }
            }, indent=2)
            
        except Exception as e:
            return f"❌ Error listing plugins: {e}"
    
    @mcp.tool()
    def search_plugins(query: str, limit: int = 20) -> str:
        """
        Search plugins by name, maker, or label
        
        Args:
            query: Search query string
            limit: Maximum number of results to return
            
        Returns:
            JSON string with search results
        """
        if not plugin_discoverer:
            return "❌ Plugin discovery not available"
        
        if not query.strip():
            return "❌ Search query cannot be empty"
        
        try:
            database = plugin_discoverer.get_database()
            plugins = database.search_plugins(query)[:limit]
            
            results = []
            for plugin in plugins:
                results.append({
                    'name': plugin.name,
                    'maker': plugin.maker,
                    'label': plugin.label,
                    'category': plugin.category,
                    'type': plugin.plugin_type,
                    'path': plugin.plugin_path,
                    'audio_ins': plugin.audio_ins,
                    'audio_outs': plugin.audio_outs,
                    'midi_ins': plugin.midi_ins,
                    'midi_outs': plugin.midi_outs
                })
            
            return json.dumps({
                'query': query,
                'results': results,
                'total_found': len(results),
                'message': f"Found {len(results)} plugins matching '{query}'"
            }, indent=2)
            
        except Exception as e:
            return f"❌ Error searching plugins: {e}"
    
    @mcp.tool()
    def get_plugin_categories() -> str:
        """
        Get list of all available plugin categories
        
        Returns:
            JSON string with category list
        """
        if not plugin_discoverer:
            return "❌ Plugin discovery not available"
        
        try:
            database = plugin_discoverer.get_database()
            categories = database.get_categories()
            
            return json.dumps({
                'categories': categories,
                'total_categories': len(categories)
            }, indent=2)
            
        except Exception as e:
            return f"❌ Error getting categories: {e}"
    
    @mcp.tool()
    def get_plugin_makers() -> str:
        """
        Get list of all plugin makers/developers
        
        Returns:
            JSON string with maker list
        """
        if not plugin_discoverer:
            return "❌ Plugin discovery not available"
        
        try:
            database = plugin_discoverer.get_database()
            makers = database.get_makers()
            
            return json.dumps({
                'makers': makers,
                'total_makers': len(makers)
            }, indent=2)
            
        except Exception as e:
            return f"❌ Error getting makers: {e}"
    
    @mcp.tool()
    def get_discovery_statistics() -> str:
        """
        Get plugin discovery statistics and status
        
        Returns:
            JSON string with discovery statistics
        """
        if not plugin_discoverer:
            return "❌ Plugin discovery not available"
        
        try:
            status = plugin_discoverer.get_discovery_status()
            
            return json.dumps({
                'total_plugins': status['total_plugins'],
                'by_type': status['by_type'],
                'by_category': status['by_category'],
                'top_makers': status['top_makers'],
                'cache_valid': status['cache_valid'],
                'discovery_tool_available': status['discovery_tool_available']
            }, indent=2)
            
        except Exception as e:
            return f"❌ Error getting statistics: {e}"
    
    @mcp.tool()
    def refresh_plugin_cache() -> str:
        """
        Refresh the plugin discovery cache
        
        Returns:
            Status message
        """
        if not plugin_discoverer:
            return "❌ Plugin discovery not available"
        
        try:
            success = plugin_discoverer.refresh_cache()
            if success:
                stats = plugin_discoverer.get_discovery_status()
                total = stats['total_plugins']
                return f"✅ Plugin cache refreshed successfully! Discovered {total} plugins."
            else:
                return "❌ Failed to refresh plugin cache"
                
        except Exception as e:
            return f"❌ Error refreshing cache: {e}"
    
    @mcp.tool()
    def add_plugin_by_name(plugin_name: str, plugin_type: Optional[str] = None) -> str:
        """
        Add a plugin to Carla by searching for it by name
        
        Args:
            plugin_name: Name of the plugin to add
            plugin_type: Optional plugin type filter
            
        Returns:
            Status message
        """
        if not plugin_discoverer:
            return "❌ Plugin discovery not available"
        
        if not backend_bridge:
            return "❌ Backend API not available. Plugin addition requires direct backend access."
        
        try:
            # Use the new simplified backend method that handles all database lookup and metadata
            success, details = backend_bridge.add_plugin_by_name(plugin_name)
            
            if success:
                return f"✅ {details}"
            else:
                return f"❌ {details}"
                
        except Exception as e:
            return f"❌ Error adding plugin: {e}"