"""
Carla Backend Bridge for MCP Server

This module provides a unified interface to the Carla backend that mirrors
the same API patterns used by the GUI, enabling MCP tools to have full
backend access with the same capabilities as the native Carla interface.
"""

import logging
from typing import Optional, Dict, Any, List
from ..utils.error_handler import get_error_handler
from ..constants import (
    PLUGIN_STRING_TO_TYPE,
    NATIVE_BINARY_TYPE,
    PLUGIN_OPTIONS_NULL,
    ENGINE_PROCESS_MODE_PATCHBAY,
    ENGINE_PROCESS_MODE_CONTINUOUS_RACK,
    ENGINE_OPTION_PROCESS_MODE,
    get_plugin_type_constant,
    BINARY_WIN64, BINARY_WIN32,
    BINARY_POSIX64, BINARY_POSIX32
)


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
        self._cleanup_performed = False
        
        # Track patchbay connections
        self._patchbay_connections = {}
        self._last_patchbay_error = ""
        
    # --------------------------------------------------------------------------------------------------------
    # Audio Monitoring
    
    def get_input_peak_value(self, plugin_id: int, is_left: bool) -> float:
        """
        Get the input peak value for a specific plugin and channel
        
        Args:
            plugin_id: Plugin ID (0-based index)
            is_left: True for left channel, False for right channel
            
        Returns:
            Peak value as float (typically 0.0 to 1.0, can exceed 1.0 for clipping)
        """
        if not self.is_engine_running():
            return 0.0
            
        try:
            return float(self.host.get_input_peak_value(plugin_id, is_left))
        except Exception as e:
            self.logger.error(f"Error getting input peak value for plugin {plugin_id}: {e}")
            return 0.0
    
    def get_output_peak_value(self, plugin_id: int, is_left: bool) -> float:
        """
        Get the output peak value for a specific plugin and channel
        
        Args:
            plugin_id: Plugin ID (0-based index)
            is_left: True for left channel, False for right channel
            
        Returns:
            Peak value as float (typically 0.0 to 1.0, can exceed 1.0 for clipping)
        """
        if not self.is_engine_running():
            return 0.0
            
        try:
            return float(self.host.get_output_peak_value(plugin_id, is_left))
        except Exception as e:
            self.logger.error(f"Error getting output peak value for plugin {plugin_id}: {e}")
            return 0.0
    
    # --------------------------------------------------------------------------------------------------------
    # Connection & Engine Status
    
    def is_engine_running(self) -> bool:
        """Check if Carla engine is running"""
        try:
            if self._cleanup_performed:
                return False
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
    
    def add_plugin_by_name(self, plugin_name: str) -> tuple[bool, str]:
        """
        Add a plugin by name using plugin database metadata
        
        Args:
            plugin_name: Name of the plugin to add
            
        Returns:
            Tuple of (success, detailed_message)
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
                error_msg = f"Plugin '{plugin_name}' not found in database"
                self.logger.error(error_msg)
                return False, error_msg
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
            success, details = self._add_plugin_from_database(plugin_info)
            if not success:
                self.logger.error(f"Failed to add plugin '{plugin_name}' using database metadata")
            return success, details
            
        except Exception as e:
            error_msg = f"Error adding plugin by name '{plugin_name}': {e}"
            self.logger.error(error_msg)
            return False, error_msg

    def _add_plugin_from_database(self, plugin_info) -> tuple[bool, str]:
        """
        Add plugin using database metadata (mimics GUI PluginListDialogResults)
        
        Args:
            plugin_info: Plugin info dict from database
            
        Returns:
            Tuple of (success, detailed_message)
        """
        try:
            plugin_type_str = plugin_info.get('plugin_type', '').lower()
            label = plugin_info.get('label', '')
            
            # Extract the correct filename and label based on plugin type
            if plugin_type_str == 'lv2':
                # For LV2, filename should be empty and label should contain the URI
                filename = ""  # LV2 plugins use empty filename
                if '/' in label:
                    # Extract URI from label (format: "Bundle.lv2/uri:scheme:here")
                    uri = label.split('/', 1)[1]  # Get the URI part after the /
                    label = uri  # Use the URI as the label
                    self.logger.info(f"LV2 plugin: using empty filename and URI as label: '{label}'")
                else:
                    self.logger.warning(f"LV2 plugin label doesn't contain URI separator: '{label}'")
            else:
                # For other types, use the file path as filename
                filename = plugin_info.get('filename', plugin_info.get('plugin_path', ''))
                self.logger.info(f"{plugin_type_str.upper()} plugin: using path '{filename}' and label '{label}'")
            
            # No need to clean label - we already set it correctly above
            
            unique_id = plugin_info.get('uniqueId', 0) or 0  # GUI uses 'uniqueId'
            build_type = plugin_info.get('build')
            plugin_type = plugin_info.get('type')  # GUI uses 'type' field (integer)
            
            # Use build type from database, fallback to platform detection
            if build_type is None:
                import platform
                is_64bit = platform.machine() in ('x86_64', 'AMD64')
                is_windows = platform.system() == 'Windows'
                if is_windows:
                    build_type = BINARY_WIN64 if is_64bit else BINARY_WIN32
                else:
                    build_type = BINARY_POSIX64 if is_64bit else BINARY_POSIX32
            
            # Call add_plugin with exact same parameters as GUI
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
                msg = f"Successfully added plugin: {plugin_info.get('name')} (build={build_type}, type={plugin_type})"
                self.logger.info(msg)
                return True, msg
            else:
                # Get detailed error from Carla backend
                last_error = "Unknown error"
                try:
                    last_error = self.host.get_last_error() or "No error details available"
                except Exception as e:
                    last_error = f"Could not get error details: {e}"
                
                # Build detailed error message
                error_details = [
                    f"Failed to add plugin: {plugin_info.get('name')}",
                    f"Plugin type: {plugin_type_str} (int: {plugin_type})",
                    f"Filename: {filename}",
                    f"Label: {label}",  
                    f"Build type: {build_type}",
                    f"Carla error: {last_error}"
                ]
                
                error_msg = "\n".join(error_details)
                
                # Log to console
                for line in error_details:
                    self.logger.error(f"  - {line}")
                    
                return False, error_msg
                
        except Exception as e:
            error_msg = f"Error in _add_plugin_from_database: {e}\nPlugin info: {plugin_info}"
            self.logger.error(error_msg)
            return False, error_msg

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
            # Get plugin type constant from centralized constants module
            ptype = get_plugin_type_constant(plugin_type)
            
            # For special plugin types, handle filename/label appropriately
            if plugin_type.lower() == 'lv2':
                # LV2 plugins: empty filename, URI as label
                filename = ""  
                if '/' in label:
                    uri = label.split('/', 1)[1]  # Get URI part
                    label = uri  # Use the URI as the label
            
            success = self.host.add_plugin(
                NATIVE_BINARY_TYPE, 
                ptype, 
                filename,  # Keep as string, let Carla handle encoding
                name or None,
                label or None,
                unique_id,
                None,  # extraPtr
                PLUGIN_OPTIONS_NULL
            )
            
            if success:
                self.logger.info(f"Successfully added plugin: {filename} (binary_type={NATIVE_BINARY_TYPE}, plugin_type={ptype})")
                return True
            else:
                # Get detailed error from Carla backend
                last_error = "Unknown error"
                try:
                    last_error = self.host.get_last_error() or "No error details available"
                except Exception as e:
                    last_error = f"Could not get error details: {e}"
                
                self.logger.error(f"Failed to add plugin: {filename} (binary_type={NATIVE_BINARY_TYPE}, plugin_type={ptype}) - Carla error: {last_error}")
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
    
    def get_parameter_count(self, plugin_id: int) -> int:
        """Get number of parameters for a plugin"""
        try:
            return self.host.get_parameter_count(plugin_id)
        except Exception as e:
            self.logger.error(f"Error getting parameter count for plugin {plugin_id}: {e}")
            return 0
    
    def get_parameter_info(self, plugin_id: int, parameter_id: int) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific parameter"""
        try:
            info = self.host.get_parameter_info(plugin_id, parameter_id)
            if info:
                return {
                    "name": info['name'],
                    "symbol": info.get('symbol', ''),
                    "unit": info.get('unit', ''),
                    "comment": info.get('comment', ''),
                    "groupName": info.get('groupName', ''),
                    "scalePointCount": info.get('scalePointCount', 0)
                }
            return None
        except Exception as e:
            self.logger.error(f"Error getting parameter info for plugin {plugin_id}, param {parameter_id}: {e}")
            return None
    
    def get_parameter_data(self, plugin_id: int, parameter_id: int) -> Optional[Dict[str, Any]]:
        """Get parameter data including current value and ranges"""
        try:
            data = self.host.get_parameter_data(plugin_id, parameter_id)
            if data:
                return {
                    "type": data['type'],
                    "hints": data['hints'],
                    "midiChannel": data['midiChannel'],
                    "mappedControlIndex": data['mappedControlIndex'],
                    "mappedMinimum": data['mappedMinimum'],
                    "mappedMaximum": data['mappedMaximum'],
                    "mappedMinimumStr": data.get('mappedMinimumStr', ''),
                    "mappedMaximumStr": data.get('mappedMaximumStr', '')
                }
            return None
        except Exception as e:
            self.logger.error(f"Error getting parameter data for plugin {plugin_id}, param {parameter_id}: {e}")
            return None
    
    def get_parameter_ranges(self, plugin_id: int, parameter_id: int) -> Optional[Dict[str, float]]:
        """Get parameter ranges (min, max, default, current)"""
        try:
            ranges = self.host.get_parameter_ranges(plugin_id, parameter_id)
            if ranges:
                return {
                    "minimum": ranges['minimum'],
                    "maximum": ranges['maximum'], 
                    "default": ranges['default'],
                    "step": ranges['step'],
                    "stepSmall": ranges['stepSmall'],
                    "stepLarge": ranges['stepLarge']
                }
            return None
        except Exception as e:
            self.logger.error(f"Error getting parameter ranges for plugin {plugin_id}, param {parameter_id}: {e}")
            return None
    
    def get_all_parameter_details(self, plugin_id: int) -> List[Dict[str, Any]]:
        """Get all parameter details for a plugin"""
        parameters = []
        param_count = self.get_parameter_count(plugin_id)
        
        for i in range(param_count):
            try:
                param = {
                    "id": i,
                    "value": self.get_parameter_value(plugin_id, i)
                }
                
                # Get parameter info
                info = self.get_parameter_info(plugin_id, i)
                if info:
                    param.update(info)
                
                # Get parameter ranges
                ranges = self.get_parameter_ranges(plugin_id, i)
                if ranges:
                    param["ranges"] = ranges
                
                # Get parameter data
                data = self.get_parameter_data(plugin_id, i)
                if data:
                    param["data"] = data
                    
                parameters.append(param)
            except Exception as e:
                self.logger.error(f"Error getting details for parameter {i}: {e}")
                
        return parameters
    
    # --------------------------------------------------------------------------------------------------------
    # Batch Parameter Operations
    
    def set_parameters_batch(self, plugin_id: int, param_changes: List[tuple]) -> Dict[str, Any]:
        """
        Set multiple parameters for a single plugin efficiently
        
        Args:
            plugin_id: Plugin ID (0-based index)
            param_changes: List of (parameter_id, value) tuples
            
        Returns:
            Dict with success count, results, and errors
        """
        if not self.is_engine_running():
            return {
                "success": False,
                "error": "Engine not running",
                "results": [],
                "success_count": 0
            }
        
        results = []
        success_count = 0
        errors = []
        
        # Validate plugin exists first
        try:
            plugin_count = self.host.get_current_plugin_count()
            if plugin_id >= plugin_count:
                return {
                    "success": False,
                    "error": f"Plugin {plugin_id} does not exist (max: {plugin_count-1})",
                    "results": [],
                    "success_count": 0
                }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to validate plugin: {e}",
                "results": [],
                "success_count": 0
            }
        
        # Get parameter count for validation
        param_count = self.get_parameter_count(plugin_id)
        
        # Execute batch parameter changes
        for i, (param_id, value) in enumerate(param_changes):
            result = {
                "index": i,
                "param_id": param_id,
                "value": value,
                "success": False,
                "error": None
            }
            
            try:
                # Validate parameter ID
                if param_id >= param_count:
                    result["error"] = f"Parameter {param_id} does not exist (max: {param_count-1})"
                    errors.append(result["error"])
                else:
                    # Set the parameter
                    self.host.set_parameter_value(plugin_id, param_id, value)
                    result["success"] = True
                    success_count += 1
                    
            except Exception as e:
                error_msg = f"Failed to set param {param_id}: {e}"
                result["error"] = error_msg
                errors.append(error_msg)
                self.logger.error(f"Batch parameter error for plugin {plugin_id}, param {param_id}: {e}")
            
            results.append(result)
        
        return {
            "success": success_count > 0,
            "success_count": success_count,
            "total_count": len(param_changes),
            "results": results,
            "errors": errors
        }
    
    def set_multiple_plugin_parameters(self, changes: List[Dict]) -> Dict[str, Any]:
        """
        Set parameters across multiple plugins efficiently
        
        Args:
            changes: List of {"plugin_id": int, "param_id": int, "value": float} dicts
            
        Returns:
            Dict with success count, results grouped by plugin, and errors
        """
        if not self.is_engine_running():
            return {
                "success": False,
                "error": "Engine not running",
                "results": {},
                "success_count": 0
            }
        
        # Group changes by plugin for efficiency
        grouped_changes = {}
        for change in changes:
            plugin_id = change["plugin_id"]
            if plugin_id not in grouped_changes:
                grouped_changes[plugin_id] = []
            grouped_changes[plugin_id].append((change["param_id"], change["value"]))
        
        results = {}
        total_success = 0
        all_errors = []
        
        # Process each plugin's parameters as a batch
        for plugin_id, param_changes in grouped_changes.items():
            plugin_result = self.set_parameters_batch(plugin_id, param_changes)
            results[str(plugin_id)] = plugin_result
            total_success += plugin_result["success_count"]
            all_errors.extend(plugin_result["errors"])
        
        return {
            "success": total_success > 0,
            "success_count": total_success,
            "total_count": len(changes),
            "results": results,
            "errors": all_errors,
            "plugins_affected": len(grouped_changes)
        }
    
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
    
    # --------------------------------------------------------------------------------------------------------
    # Engine Mode and Patchbay Control
    
    def set_engine_process_mode(self, mode: int) -> bool:
        """
        Switch between rack (2) and patchbay (3) modes
        
        Args:
            mode: Engine process mode (2=rack, 3=patchbay)
            
        Returns:
            True if mode was changed successfully
        """
        try:
            success = self.host.set_engine_option(ENGINE_OPTION_PROCESS_MODE, mode, "")
            if success:
                self.logger.info(f"Successfully set engine process mode to {mode}")
                return True
            else:
                self.logger.error(f"Failed to set engine process mode to {mode}")
                return False
        except Exception as e:
            self.logger.error(f"Error setting engine process mode to {mode}: {e}")
            return False
    
    def get_engine_process_mode(self) -> int:
        """
        Get current engine mode (2=rack, 3=patchbay)
        
        Returns:
            Current engine process mode or -1 on error
        """
        try:
            # Get process mode directly from host object
            if hasattr(self.host, 'processMode'):
                mode = self.host.processMode
                self.logger.info(f"Engine process mode: {mode}")
                return mode
            else:
                self.logger.warning("Host object doesn't have processMode attribute")
                return -1
        except Exception as e:
            self.logger.error(f"Error getting engine process mode: {e}")
            return -1
    
    def patchbay_connect(self, group_a: int, port_a: int, group_b: int, port_b: int) -> bool:
        """
        Connect two ports in patchbay mode
        
        Args:
            group_a: Source port group ID
            port_a: Source port ID within group
            group_b: Destination port group ID  
            port_b: Destination port ID within group
            
        Returns:
            True if connection was successful
        """
        try:
            # Log detailed connection attempt info
            self.logger.info(f"=== PATCHBAY CONNECTION ATTEMPT ===")
            self.logger.info(f"Source: Group {group_a}, Port {port_a}")
            self.logger.info(f"Dest: Group {group_b}, Port {port_b}")
            
            # Get group info for debugging
            try:
                groups = self.get_patchbay_groups()
                source_group = next((g for g in groups if g['id'] == group_a), None)
                dest_group = next((g for g in groups if g['id'] == group_b), None)
                
                if source_group:
                    self.logger.info(f"Source group: {source_group['name']} (type: {source_group.get('type', 'unknown')})")
                if dest_group:
                    self.logger.info(f"Dest group: {dest_group['name']} (type: {dest_group.get('type', 'unknown')})")
            except:
                pass
            
            self.logger.info(f"Calling host.patchbay_connect(False, {group_a}, {port_a}, {group_b}, {port_b})")
            
            success = self.host.patchbay_connect(False, group_a, port_a, group_b, port_b)
            if success:
                self.logger.info(f"✓ Successfully connected ports: {group_a}:{port_a} -> {group_b}:{port_b}")
                # Track the connection - we'll get the ID from the callback
                # For now, store with a temporary key
                temp_key = f"{group_a}:{port_a}:{group_b}:{port_b}"
                self._patchbay_connections[temp_key] = {
                    'group_a': group_a,
                    'port_a': port_a,
                    'group_b': group_b,
                    'port_b': port_b,
                    'pending': True
                }
                return True
            else:
                # Get the actual Carla error message
                carla_error = "Unknown error"
                try:
                    carla_error = self.host.get_last_error()
                except:
                    pass
                
                error_msg = f"✗ Failed to connect ports: {group_a}:{port_a} -> {group_b}:{port_b}"
                if carla_error:
                    error_msg += f" - Carla error: {carla_error}"
                    
                self.logger.error(error_msg)
                # Store the error so tools can access it
                self._last_patchbay_error = carla_error
                return False
        except Exception as e:
            self.logger.error(f"✗ Error connecting ports {group_a}:{port_a} -> {group_b}:{port_b}: {e}")
            self._last_patchbay_error = str(e)
            return False
    
    def get_last_patchbay_error(self) -> str:
        """Get the last patchbay connection error message"""
        return self._last_patchbay_error
    
    def patchbay_disconnect(self, connection_id: int) -> bool:
        """
        Disconnect ports by connection ID
        
        Args:
            connection_id: ID of the connection to disconnect
            
        Returns:
            True if disconnection was successful
        """
        try:
            success = self.host.patchbay_disconnect(False, connection_id)
            if success:
                self.logger.info(f"Successfully disconnected connection {connection_id}")
                return True
            else:
                self.logger.error(f"Failed to disconnect connection {connection_id}")
                return False
        except Exception as e:
            self.logger.error(f"Error disconnecting connection {connection_id}: {e}")
            return False
    
    def get_patchbay_connections(self) -> List[Dict[str, Any]]:
        """
        Get list of current patchbay connections
        
        Returns:
            List of connection dictionaries
        """
        # Return non-pending connections
        return [
            {**conn, 'id': conn_id} 
            for conn_id, conn in self._patchbay_connections.items() 
            if isinstance(conn_id, int) and not conn.get('pending', False)
        ]
    
    def register_connection(self, connection_id: int, group_a: int, port_a: int, group_b: int, port_b: int):
        """
        Register a connection that was made (called from callback)
        
        Args:
            connection_id: The connection ID assigned by Carla
            group_a: Source group ID
            port_a: Source port ID
            group_b: Destination group ID
            port_b: Destination port ID
        """
        # Check if we have a pending connection matching these parameters
        temp_key = f"{group_a}:{port_a}:{group_b}:{port_b}"
        
        if temp_key in self._patchbay_connections:
            # Move from temp key to proper ID
            conn_data = self._patchbay_connections.pop(temp_key)
            conn_data['pending'] = False
            self._patchbay_connections[connection_id] = conn_data
        else:
            # Connection made outside MCP, still track it
            self._patchbay_connections[connection_id] = {
                'group_a': group_a,
                'port_a': port_a,
                'group_b': group_b,
                'port_b': port_b,
                'pending': False
            }
        
        self.logger.info(f"Registered connection {connection_id}: {group_a}:{port_a} -> {group_b}:{port_b}")
    
    def unregister_connection(self, connection_id: int):
        """
        Remove a connection from tracking (called from callback)
        
        Args:
            connection_id: The connection ID to remove
        """
        if connection_id in self._patchbay_connections:
            del self._patchbay_connections[connection_id]
            self.logger.info(f"Unregistered connection {connection_id}")
    
    def patchbay_refresh(self) -> bool:
        """
        Refresh patchbay state
        
        Returns:
            True if refresh was successful
        """
        try:
            success = self.host.patchbay_refresh(False)
            if success:
                self.logger.info("Successfully refreshed patchbay")
                return True
            else:
                self.logger.error("Failed to refresh patchbay")
                return False
        except Exception as e:
            self.logger.error(f"Error refreshing patchbay: {e}")
            return False
    
    def get_patchbay_groups(self) -> List[Dict]:
        """
        Get all available port groups (plugins, system, etc.)
        
        Returns:
            List of dictionaries containing group information
        """
        try:
            groups = []
            
            # Get current plugin count to iterate through plugin groups
            plugin_count = self.get_plugin_count()
            
            # Group IDs in Carla patchbay:
            # 0 = Audio Input group
            # 1 = Audio Output group  
            # 2 = Midi Input group
            # 3 = Midi Output group
            # 4+ = Plugin groups
            
            # Add Audio Input group
            groups.append({
                'id': 0,
                'name': 'Audio Input',
                'type': 'audio_input',
                'port_count': 16,  # Carla typically has 16 audio inputs
                'ports': {
                    'outputs': [f'Capture {i+1}' for i in range(16)]  # Audio inputs have outputs in patchbay
                }
            })
            
            # Add Audio Output group
            groups.append({
                'id': 1,
                'name': 'Audio Output',
                'type': 'audio_output',
                'port_count': 16,  # Carla typically has 16 audio outputs
                'ports': {
                    'inputs': [f'Playback {i+1}' for i in range(16)]  # Audio outputs have inputs in patchbay
                }
            })
            
            # Add Midi Input group
            groups.append({
                'id': 2,
                'name': 'Midi Input',
                'type': 'midi_input',
                'port_count': 1,
                'ports': {
                    'outputs': ['Capture 1']
                }
            })
            
            # Add Midi Output group
            groups.append({
                'id': 3,
                'name': 'Midi Output',
                'type': 'midi_output',
                'port_count': 1,
                'ports': {
                    'inputs': ['Playback 1']
                }
            })
            
            # Add plugin groups (starting from group ID 4)
            for i in range(plugin_count):
                plugin_info = self.get_plugin_info(i)
                if plugin_info:
                    # Get actual port counts for this plugin
                    audio_ins = 0
                    audio_outs = 0
                    
                    try:
                        audio_port_info = self.host.get_audio_port_count_info(i)
                        if audio_port_info:
                            audio_ins = audio_port_info.ins
                            audio_outs = audio_port_info.outs
                    except:
                        # Default to stereo if can't get info
                        audio_ins = 2
                        audio_outs = 2
                    
                    groups.append({
                        'id': i + 4,  # Plugin groups start at 4
                        'name': plugin_info.get('name', f'Plugin {i}'),
                        'type': 'plugin',
                        'plugin_id': i,
                        'audio_inputs': audio_ins,
                        'audio_outputs': audio_outs,
                        'ports': {
                            'inputs': [f'Audio Input {j+1}' for j in range(audio_ins)],
                            'outputs': [f'Audio Output {j+1}' for j in range(audio_outs)]
                        }
                    })
            
            return groups
        except Exception as e:
            self.logger.error(f"Error getting patchbay groups: {e}")
            return []
    
    # --------------------------------------------------------------------------------------------------------
    # Session Management
    
    def load_project(self, filename: str) -> bool:
        """
        Load a Carla project file (.carxp)
        
        Args:
            filename: Path to the project file
            
        Returns:
            True if project was loaded successfully
        """
        if not self.is_engine_running():
            self.logger.error("Cannot load project: engine not running")
            return False
            
        try:
            success = self.host.load_project(filename)
            if success:
                self.logger.info(f"Successfully loaded project: {filename}")
            else:
                self.logger.error(f"Failed to load project: {filename}")
            return success
        except Exception as e:
            self.logger.error(f"Error loading project {filename}: {e}")
            return False
    
    def save_project(self, filename: str) -> bool:
        """
        Save current state as a Carla project file (.carxp)
        
        Args:
            filename: Path where to save the project file
            
        Returns:
            True if project was saved successfully
        """
        if not self.is_engine_running():
            self.logger.error("Cannot save project: engine not running")
            return False
            
        try:
            success = self.host.save_project(filename)
            if success:
                self.logger.info(f"Successfully saved project: {filename}")
            else:
                self.logger.error(f"Failed to save project: {filename}")
            return success
        except Exception as e:
            self.logger.error(f"Error saving project {filename}: {e}")
            return False
    
    def get_current_project_filename(self) -> Optional[str]:
        """
        Get the filename of the currently loaded project
        
        Returns:
            Current project filename or None
        """
        try:
            filename = self.host.get_current_project_filename()
            return filename if filename else None
        except Exception as e:
            self.logger.error(f"Error getting current project filename: {e}")
            return None
    
    def clear_project_filename(self) -> bool:
        """
        Clear the current project filename (mark as unsaved)
        
        Returns:
            True if successful
        """
        try:
            self.host.clear_project_filename()
            return True
        except Exception as e:
            self.logger.error(f"Error clearing project filename: {e}")
            return False
    
    def load_plugin_state(self, plugin_id: int, filename: str) -> bool:
        """
        Load a plugin state from file (.carxs)
        
        Args:
            plugin_id: Plugin ID (0-based index)
            filename: Path to the state file
            
        Returns:
            True if state was loaded successfully
        """
        try:
            success = self.host.load_plugin_state(plugin_id, filename)
            if success:
                self.logger.info(f"Successfully loaded plugin {plugin_id} state from: {filename}")
            else:
                self.logger.error(f"Failed to load plugin {plugin_id} state from: {filename}")
            return success
        except Exception as e:
            self.logger.error(f"Error loading plugin {plugin_id} state: {e}")
            return False
    
    def save_plugin_state(self, plugin_id: int, filename: str) -> bool:
        """
        Save a plugin state to file (.carxs)
        
        Args:
            plugin_id: Plugin ID (0-based index)
            filename: Path where to save the state file
            
        Returns:
            True if state was saved successfully
        """
        try:
            success = self.host.save_plugin_state(plugin_id, filename)
            if success:
                self.logger.info(f"Successfully saved plugin {plugin_id} state to: {filename}")
            else:
                self.logger.error(f"Failed to save plugin {plugin_id} state to: {filename}")
            return success
        except Exception as e:
            self.logger.error(f"Error saving plugin {plugin_id} state: {e}")
            return False
    
    def set_custom_data(self, plugin_id: int, type_: str, key: str, value: str) -> bool:
        """
        Set custom data for a plugin
        
        Args:
            plugin_id: Plugin ID (0-based index)
            type_: Custom data type (e.g. CUSTOM_DATA_TYPE_PATH)
            key: Custom data key (e.g. "file")
            value: Custom data value (e.g. file path)
            
        Returns:
            True if custom data was set successfully
        """
        try:
            self.host.set_custom_data(plugin_id, type_, key, value)
            self.logger.info(f"Successfully set custom data for plugin {plugin_id}: {type_}:{key} = {value}")
            return True
        except Exception as e:
            self.logger.error(f"Error setting custom data for plugin {plugin_id}: {e}")
            return False
    
    def get_custom_data_value(self, plugin_id: int, type_: str, key: str) -> Optional[str]:
        """
        Get custom data value for a plugin
        
        Args:
            plugin_id: Plugin ID (0-based index)
            type_: Custom data type (e.g. CUSTOM_DATA_TYPE_PATH)
            key: Custom data key (e.g. "file")
            
        Returns:
            Custom data value if found, None otherwise
        """
        try:
            value = self.host.get_custom_data_value(plugin_id, type_, key)
            return value if value else None
        except Exception as e:
            self.logger.error(f"Error getting custom data for plugin {plugin_id}: {e}")
            return None
    
    # --------------------------------------------------------------------------------------------------------
    # Resource Management and Cleanup
    
    def cleanup(self):
        """
        Clean up resources and prepare for shutdown
        
        This method should be called before the bridge is destroyed
        to ensure proper cleanup of any resources or connections.
        """
        if self._cleanup_performed:
            return
        
        try:
            self.logger.info("Cleaning up CarlaBackendBridge resources...")
            
            # Validate engine state before attempting cleanup
            if self.host and hasattr(self.host, 'is_engine_running'):
                if self.is_engine_running():
                    self.logger.info("Engine is still running during cleanup - this is expected")
                else:
                    self.logger.info("Engine already stopped during cleanup")
            
            # Mark cleanup as performed
            self._cleanup_performed = True
            self.logger.info("CarlaBackendBridge cleanup completed successfully")
            
        except Exception as e:
            self.logger.error(f"Error during CarlaBackendBridge cleanup: {e}")
            # Still mark as performed to prevent repeated attempts
            self._cleanup_performed = True
    
    def __del__(self):
        """Destructor to ensure cleanup is performed"""
        if not self._cleanup_performed:
            self.cleanup()