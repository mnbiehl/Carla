"""
Carla Backend Bridge for MCP Server

This module provides a unified interface to the Carla backend that mirrors
the same API patterns used by the GUI, enabling MCP tools to have full
backend access with the same capabilities as the native Carla interface.
"""

import logging
from typing import Optional, Dict, Any, List
from ..utils.error_handler import get_error_handler


class CarlaBackendBridge:
    """
    Bridge class that provides MCP tools with direct access to Carla backend API.
    
    This mirrors the exact same API patterns used by the GUI, ensuring consistency
    and providing full backend capabilities rather than limited OSC functionality.
    """
    
    def __init__(self, host_instance):
        """
        Initialize the backend bridge with a Carla host instance
        
        Args:
            host_instance: CarlaHostQtDLL instance from the GUI
        """
        self.host = host_instance
        self.logger = logging.getLogger(__name__)
        self._error_handler = get_error_handler()
        
    # --------------------------------------------------------------------------------------------------------
    # Connection & Engine Status
    
    def is_engine_running(self) -> bool:
        """Check if Carla engine is running"""
        try:
            return self.host.is_engine_running()
        except Exception as e:
            self.logger.error(f"Error checking engine status: {e}")
            return False
    
    def test_connection(self) -> bool:
        """Test connection to Carla backend (same as engine running for direct access)"""
        return self.is_engine_running()
    
    def get_engine_info(self) -> Dict[str, Any]:
        """Get comprehensive engine information"""
        if not self.is_engine_running():
            return {"status": "stopped", "error": "Engine not running"}
            
        try:
            info = {
                "status": "running",
                "driver_name": self.host.get_current_engine_driver() if hasattr(self.host, 'get_current_engine_driver') else "Unknown",
                "sample_rate": self.host.get_sample_rate(),
                "buffer_size": self.host.get_buffer_size(),
                "plugin_count": self.host.get_current_plugin_count(),
                "transport_info": {
                    "playing": self.host.transport_play() if hasattr(self.host, 'transport_play') else False,
                    "bpm": self.host.get_current_transport_bpm() if hasattr(self.host, 'get_current_transport_bpm') else 120.0,
                    "frame": self.host.get_current_transport_frame() if hasattr(self.host, 'get_current_transport_frame') else 0
                }
            }
            return info
        except Exception as e:
            self.logger.error(f"Error getting engine info: {e}")
            return {"status": "error", "error": str(e)}
    
    # --------------------------------------------------------------------------------------------------------
    # Plugin Management (mirroring GUI patterns)
    
    def add_plugin_by_name(self, plugin_name: str) -> bool:
        """
        Add a plugin by name using plugin database metadata
        
        Args:
            plugin_name: Name of the plugin to add
            
        Returns:
            True if plugin was added successfully, False otherwise
        """
        # Import plugin discoverer to access database
        try:
            from ..discovery.plugin_discoverer import PluginDiscoverer
            discoverer = PluginDiscoverer()
            
            # Search for plugin by name using the database
            database = discoverer.get_database()
            results = database.search_plugins(plugin_name)
            
            # Find exact matches
            exact_matches = []
            for result in results:
                if result.name.lower() == plugin_name.lower():
                    exact_matches.append(result)
            
            if not exact_matches:
                self.logger.error(f"Plugin '{plugin_name}' not found in database")
                return False
            elif len(exact_matches) > 1:
                # Multiple matches found - prefer LV2, then LADSPA, then others
                plugin_priority = {'lv2': 0, 'ladspa': 1, 'vst2': 2, 'vst3': 3}
                exact_matches.sort(key=lambda p: plugin_priority.get(p.plugin_type.lower(), 99))
                selected_plugin = exact_matches[0]
                self.logger.info(f"Multiple '{plugin_name}' plugins found, using {selected_plugin.plugin_type.upper()} version")
                plugin_info = selected_plugin.to_dict()
            else:
                plugin_info = exact_matches[0].to_dict()
            
            # Use the discovered plugin info to add with correct metadata
            success = self._add_plugin_from_database(plugin_info)
            if not success:
                self.logger.error(f"Failed to add plugin '{plugin_name}' using database metadata")
            return success
            
        except Exception as e:
            self.logger.error(f"Error adding plugin by name '{plugin_name}': {e}")
            return False

    def _add_plugin_from_database(self, plugin_info) -> bool:
        """
        Add plugin using database metadata (mimics GUI PluginListDialogResults)
        
        Args:
            plugin_info: Plugin info dict from database
            
        Returns:
            True if plugin was added successfully
        """
        try:
            # Use GUI-compatible fields from database (same as carla_host.py)
            filename = plugin_info.get('filename', '')  # GUI uses 'filename' field 
            label = plugin_info.get('label', '')
            unique_id = plugin_info.get('uniqueId', 0) or 0  # GUI uses 'uniqueId'
            build_type = plugin_info.get('build')
            plugin_type = plugin_info.get('type')  # GUI uses 'type' field (integer)
            
            # Use build type from database, fallback to platform detection
            if build_type is None:
                import platform
                is_64bit = platform.machine() in ('x86_64', 'AMD64')
                is_windows = platform.system() == 'Windows'
                if is_windows:
                    build_type = 4 if is_64bit else 3  # BINARY_WIN64 or BINARY_WIN32
                else:
                    build_type = 2 if is_64bit else 1  # BINARY_POSIX64 or BINARY_POSIX32
            
            # Call add_plugin with exact same parameters as GUI
            PLUGIN_OPTIONS_NULL = 0x0
            success = self.host.add_plugin(
                build_type,      # btype (from database or detected)
                plugin_type,     # ptype 
                filename,        # filename
                None,           # name (GUI uses None)
                label,          # label
                unique_id,      # uniqueId
                None,           # extraPtr (GUI uses None for now)
                PLUGIN_OPTIONS_NULL
            )
            
            if success:
                self.logger.info(f"Successfully added plugin: {plugin_info.get('name')} (build={build_type}, type={plugin_type})")
                return True
            else:
                # Get detailed error from Carla backend
                last_error = "Unknown error"
                try:
                    last_error = self.host.get_last_error() or "No error details available"
                except Exception as e:
                    last_error = f"Could not get error details: {e}"
                
                self.logger.error(f"Failed to add plugin: {plugin_info.get('name')} - Carla error: {last_error}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error in _add_plugin_from_database: {e}")
            return False

    def add_plugin(self, plugin_type: str, filename: str, name: str = "", 
                   label: str = "", unique_id: int = 0) -> bool:
        """
        Add a plugin using the same API pattern as the GUI
        
        Args:
            plugin_type: Plugin type (e.g., "lv2", "vst2", "vst3", "ladspa")
            filename: Plugin filename or URI
            name: Plugin name (optional)
            label: Plugin label (optional) 
            unique_id: Plugin unique ID (optional)
            
        Returns:
            True if plugin was added successfully, False otherwise
        """
        # Check prerequisites
        if not self.is_engine_running():
            self.logger.error("Cannot add plugin: engine not running")
            return False
            
        try:
            # Map plugin type string to Carla constants
            # These MUST match carla_backend.py definitions exactly!
            PLUGIN_TYPE_MAP = {
                "internal": 1,  # PLUGIN_INTERNAL (was incorrectly 0)
                "ladspa": 2,    # PLUGIN_LADSPA (was incorrectly 1)
                "dssi": 3,      # PLUGIN_DSSI (was incorrectly 2)
                "lv2": 4,       # PLUGIN_LV2 (was incorrectly 3)
                "vst2": 5,      # PLUGIN_VST2 (was incorrectly 4)
                "vst3": 6,      # PLUGIN_VST3 (was incorrectly 5)
                "au": 7,        # PLUGIN_AU (was incorrectly 6)
                "sf2": 8,       # PLUGIN_SF2 (was incorrectly 7)
                "sfz": 9,       # PLUGIN_SFZ (was incorrectly 8)
                "jack": 12      # PLUGIN_JACK (was incorrectly 7)
            }
            
            ptype = PLUGIN_TYPE_MAP.get(plugin_type.lower(), 4)  # Default to LV2 (which is 4)
            
            # Import proper binary type constants from carla_backend
            import sys
            import platform
            from pathlib import Path
            
            # Add Carla frontend to path to import binary constants
            carla_frontend_path = Path(__file__).parent.parent.parent
            if str(carla_frontend_path) not in sys.path:
                sys.path.insert(0, str(carla_frontend_path))
            
            try:
                from carla_backend import BINARY_NATIVE, BINARY_POSIX64
                # Force use of correct binary type for Linux x86_64
                if BINARY_NATIVE == 0:  # BINARY_NONE is wrong
                    BINARY_NATIVE = BINARY_POSIX64
                    self.logger.warning(f"Corrected BINARY_NATIVE from 0 to {BINARY_NATIVE} (BINARY_POSIX64)")
                else:
                    self.logger.info(f"Using BINARY_NATIVE = {BINARY_NATIVE}")
            except ImportError:
                # Fallback: manual platform detection
                is_64bit = platform.machine() in ('x86_64', 'AMD64')
                is_windows = platform.system() == 'Windows'
                
                if is_windows:
                    BINARY_NATIVE = 4 if is_64bit else 3  # BINARY_WIN64 or BINARY_WIN32
                else:
                    BINARY_NATIVE = 2 if is_64bit else 1  # BINARY_POSIX64 or BINARY_POSIX32
                
                self.logger.warning(f"Failed to import carla_backend, using fallback BINARY_NATIVE = {BINARY_NATIVE}")
            
            PLUGIN_OPTIONS_NULL = 0x0
            
            success = self.host.add_plugin(
                BINARY_NATIVE, 
                ptype, 
                filename,  # Keep as string, let Carla handle encoding
                name or None,
                label or None,
                unique_id,
                None,  # extraPtr
                PLUGIN_OPTIONS_NULL
            )
            
            if success:
                self.logger.info(f"Successfully added plugin: {filename} (binary_type={BINARY_NATIVE}, plugin_type={ptype})")
                return True
            else:
                # Get detailed error from Carla backend
                last_error = "Unknown error"
                try:
                    last_error = self.host.get_last_error() or "No error details available"
                except Exception as e:
                    last_error = f"Could not get error details: {e}"
                
                self.logger.error(f"Failed to add plugin: {filename} (binary_type={BINARY_NATIVE}, plugin_type={ptype}, arch={platform.machine()}) - Carla error: {last_error}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error adding plugin {filename}: {e}")
            return False
    
    def remove_plugin(self, plugin_id: int) -> bool:
        """Remove a plugin by ID"""
        if not self.is_engine_running():
            self.logger.error("Cannot remove plugin: engine not running")
            return False
            
        try:
            success = self.host.remove_plugin(plugin_id)
            if success:
                self.logger.info(f"Successfully removed plugin {plugin_id}")
            else:
                self.logger.error(f"Failed to remove plugin {plugin_id}")
            return success
        except Exception as e:
            self.logger.error(f"Error removing plugin {plugin_id}: {e}")
            return False
    
    def remove_all_plugins(self) -> bool:
        """Remove all loaded plugins"""
        if not self.is_engine_running():
            self.logger.error("Cannot remove plugins: engine not running")
            return False
            
        try:
            success = self.host.remove_all_plugins()
            if success:
                self.logger.info("Successfully removed all plugins")
            else:
                self.logger.error("Failed to remove all plugins")
            return success
        except Exception as e:
            self.logger.error(f"Error removing all plugins: {e}")
            return False
    
    def get_plugin_count(self) -> int:
        """Get current plugin count"""
        try:
            return self.host.get_current_plugin_count()
        except Exception as e:
            self.logger.error(f"Error getting plugin count: {e}")
            return 0
    
    def get_current_plugin_count(self) -> int:
        """Alias for get_plugin_count for compatibility"""
        return self.get_plugin_count()
    
    def get_max_plugin_number(self) -> int:
        """Get maximum number of plugins that can be loaded"""
        try:
            return self.host.get_max_plugin_number()
        except Exception as e:
            self.logger.error(f"Error getting max plugin number: {e}")
            return 0
    
    def get_plugin_info(self, plugin_id: int) -> Optional[Dict[str, Any]]:
        """Get plugin information"""
        try:
            info = self.host.get_plugin_info(plugin_id)
            return info if info else None
        except Exception as e:
            self.logger.error(f"Error getting plugin info for {plugin_id}: {e}")
            return None
    
    def get_all_plugins(self) -> List[Dict[str, Any]]:
        """Get information for all loaded plugins"""
        plugins = []
        count = self.get_plugin_count()
        
        for i in range(count):
            info = self.get_plugin_info(i)
            if info:
                plugins.append({
                    "id": i,
                    **info
                })
        
        return plugins
    
    # --------------------------------------------------------------------------------------------------------
    # Parameter Control
    
    def set_parameter_value(self, plugin_id: int, parameter_id: int, value: float) -> bool:
        """Set plugin parameter value"""
        try:
            self.host.set_parameter_value(plugin_id, parameter_id, value)
            return True
        except Exception as e:
            self.logger.error(f"Error setting parameter {parameter_id} on plugin {plugin_id}: {e}")
            return False
    
    def get_parameter_value(self, plugin_id: int, parameter_id: int) -> Optional[float]:
        """Get plugin parameter value"""
        try:
            return self.host.get_current_parameter_value(plugin_id, parameter_id)
        except Exception as e:
            self.logger.error(f"Error getting parameter {parameter_id} on plugin {plugin_id}: {e}")
            return None
    
    # --------------------------------------------------------------------------------------------------------
    # MIDI Control
    
    def send_midi_note_on(self, plugin_id: int, channel: int, note: int, velocity: int) -> bool:
        """Send MIDI note on"""
        try:
            self.host.send_midi_note(plugin_id, channel, note, velocity)
            return True
        except Exception as e:
            self.logger.error(f"Error sending MIDI note on: {e}")
            return False
    
    def send_midi_note_off(self, plugin_id: int, channel: int, note: int) -> bool:
        """Send MIDI note off"""
        try:
            self.host.send_midi_note(plugin_id, channel, note, 0)  # velocity 0 = note off
            return True
        except Exception as e:
            self.logger.error(f"Error sending MIDI note off: {e}")
            return False
    
    # --------------------------------------------------------------------------------------------------------
    # Plugin State Control
    
    def set_plugin_active(self, plugin_id: int, active: bool) -> bool:
        """Activate or deactivate a plugin"""
        try:
            self.host.set_active(plugin_id, active)
            return True
        except Exception as e:
            self.logger.error(f"Error setting plugin {plugin_id} active state: {e}")
            return False
    
    def set_plugin_volume(self, plugin_id: int, volume: float) -> bool:
        """Set plugin volume (0.0 to 1.27, where 1.0 = unity gain)"""
        try:
            # Volume is typically controlled via a specific parameter
            # This may need adjustment based on how Carla handles volume internally
            self.host.set_volume(plugin_id, volume)
            return True
        except Exception as e:
            self.logger.error(f"Error setting plugin {plugin_id} volume: {e}")
            return False