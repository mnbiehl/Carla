"""
Carla Backend Client for direct API integration

Provides comprehensive control over Carla through the native backend API.
"""

import logging
import sys
import os
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)

# Add Carla path to system path
CARLA_PATH = "/usr/share/carla"
if CARLA_PATH not in sys.path:
    sys.path.append(CARLA_PATH)

try:
    from carla_backend import CarlaHostDLL
    CARLA_BACKEND_AVAILABLE = True
    logger.info("Carla backend API available")
except ImportError as e:
    CARLA_BACKEND_AVAILABLE = False
    logger.warning(f"Carla backend API not available: {e}")
    # Create a dummy class for compatibility
    class CarlaHostDLL:
        pass


class CarlaBackendClient:
    """Client for communicating with Carla through direct backend API"""
    
    def __init__(self, engine_name: str = "MCP-Carla"):
        """
        Initialize Carla backend client
        
        Args:
            engine_name: Name for the Carla engine instance
        """
        self.engine_name = engine_name
        self.host = None
        self.initialized = False
        
        if not CARLA_BACKEND_AVAILABLE:
            logger.error("Carla backend API not available")
            raise RuntimeError("Carla backend API not available")
        
        try:
            self.host = CarlaHostDLL("/usr/lib/carla/libcarla_standalone2.so", False)
            logger.info("Carla backend client initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Carla backend: {e}")
            raise
    
    def initialize_engine(self, driver_name: str = "JACK", device_name: str = "") -> bool:
        """
        Initialize the Carla engine
        
        Args:
            driver_name: Audio driver to use (JACK, ALSA, etc.)
            device_name: Specific device name (optional, not used in current API)
            
        Returns:
            bool: True if engine initialized successfully
        """
        if not self.host:
            return False
        
        try:
            # Initialize engine with client name (second parameter is client name, not device name)
            client_name = self.engine_name or "CarlaBackend"
            success = self.host.engine_init(driver_name, client_name)
            if success:
                self.initialized = True
                logger.info(f"Carla engine initialized with {driver_name}, client: {client_name}")
            else:
                error = self.host.get_last_error()
                logger.error(f"Failed to initialize engine: {error}")
            return success
        except Exception as e:
            logger.error(f"Engine initialization error: {e}")
            return False
    
    def close_engine(self):
        """Close the Carla engine"""
        if self.host and self.initialized:
            try:
                self.host.engine_close()
                self.initialized = False
                logger.info("Carla engine closed")
            except Exception as e:
                logger.error(f"Error closing engine: {e}")
    
    def test_connection(self) -> bool:
        """Test if backend connection is working"""
        try:
            if not self.host:
                return False
            # Try to get engine info as connection test
            info = self.host.get_runtime_engine_info()
            return info is not None
        except Exception as e:
            logger.warning(f"Backend connection test failed: {e}")
            return False
    
    def get_current_plugin_count(self) -> int:
        """Get number of currently loaded plugins"""
        if not self.host or not self.initialized:
            return 0
        try:
            return self.host.get_current_plugin_count()
        except Exception as e:
            logger.error(f"Error getting plugin count: {e}")
            return 0
    
    def get_max_plugin_number(self) -> int:
        """Get maximum number of plugins that can be loaded"""
        if not self.host or not self.initialized:
            return 0
        try:
            return self.host.get_max_plugin_number()
        except Exception as e:
            logger.error(f"Error getting max plugin number: {e}")
            return 0
    
    def add_plugin(self, binary_type: int, plugin_type: int, filename: str, 
                   name: str, label: str, unique_id: int = 0, 
                   extra_ptr: Any = None, options: int = 0) -> bool:
        """
        Add a new plugin to Carla
        
        Args:
            binary_type: Binary type (NATIVE, POSIX32, POSIX64, WIN32, WIN64)
            plugin_type: Plugin type (INTERNAL, LADSPA, DSSI, LV2, VST2, VST3, AU, etc.)
            filename: Plugin filename/path
            name: Display name for the plugin
            label: Plugin label/identifier
            unique_id: Unique plugin ID (for VST)
            extra_ptr: Extra pointer data
            options: Plugin options flags
            
        Returns:
            bool: True if plugin added successfully
        """
        if not self.host or not self.initialized:
            logger.error("Engine not initialized")
            return False
        
        try:
            success = self.host.add_plugin(binary_type, plugin_type, filename, 
                                         name, label, unique_id, extra_ptr, options)
            if success:
                logger.info(f"Successfully added plugin: {name}")
            else:
                error = self.host.get_last_error()
                logger.error(f"Failed to add plugin {name}: {error}")
            return success
        except Exception as e:
            logger.error(f"Error adding plugin {name}: {e}")
            return False
    
    def remove_plugin(self, plugin_id: int) -> bool:
        """
        Remove a plugin from Carla
        
        Args:
            plugin_id: ID of the plugin to remove
            
        Returns:
            bool: True if plugin removed successfully
        """
        if not self.host or not self.initialized:
            return False
        
        try:
            success = self.host.remove_plugin(plugin_id)
            if success:
                logger.info(f"Successfully removed plugin {plugin_id}")
            else:
                error = self.host.get_last_error()
                logger.error(f"Failed to remove plugin {plugin_id}: {error}")
            return success
        except Exception as e:
            logger.error(f"Error removing plugin {plugin_id}: {e}")
            return False
    
    def remove_all_plugins(self) -> bool:
        """Remove all plugins from Carla"""
        if not self.host or not self.initialized:
            return False
        
        try:
            success = self.host.remove_all_plugins()
            if success:
                logger.info("Successfully removed all plugins")
            else:
                error = self.host.get_last_error()
                logger.error(f"Failed to remove all plugins: {error}")
            return success
        except Exception as e:
            logger.error(f"Error removing all plugins: {e}")
            return False
    
    def get_plugin_info(self, plugin_id: int) -> Optional[Dict]:
        """
        Get information about a specific plugin
        
        Args:
            plugin_id: ID of the plugin
            
        Returns:
            Dict with plugin information or None if not found
        """
        if not self.host or not self.initialized:
            return None
        
        try:
            info = self.host.get_plugin_info(plugin_id)
            if info:
                return {
                    'type': info.type,
                    'category': info.category,
                    'hints': info.hints,
                    'options_available': info.optionsAvailable,
                    'options_enabled': info.optionsEnabled,
                    'filename': info.filename,
                    'name': info.name,
                    'label': info.label,
                    'maker': info.maker,
                    'copyright': info.copyright,
                    'icon_name': info.iconName,
                    'unique_id': info.uniqueId
                }
            return None
        except Exception as e:
            logger.error(f"Error getting plugin info for {plugin_id}: {e}")
            return None
    
    def get_engine_driver_count(self) -> int:
        """Get number of available audio drivers"""
        if not self.host:
            return 0
        try:
            return self.host.get_engine_driver_count()
        except Exception as e:
            logger.error(f"Error getting driver count: {e}")
            return 0
    
    def get_engine_driver_name(self, index: int) -> Optional[str]:
        """Get name of audio driver at index"""
        if not self.host:
            return None
        try:
            return self.host.get_engine_driver_name(index)
        except Exception as e:
            logger.error(f"Error getting driver name at {index}: {e}")
            return None
    
    def get_engine_driver_device_names(self, driver_index: int) -> Optional[List[str]]:
        """Get list of device names for a driver"""
        if not self.host:
            return None
        try:
            devices = self.host.get_engine_driver_device_names(driver_index)
            return list(devices) if devices else []
        except Exception as e:
            logger.error(f"Error getting device names for driver {driver_index}: {e}")
            return None
    
    def get_runtime_engine_info(self) -> Optional[Dict]:
        """Get current engine runtime information"""
        if not self.host or not self.initialized:
            return None
        try:
            info = self.host.get_runtime_engine_info()
            if info:
                return {
                    'driver': info.driverName,
                    'device': info.deviceName,
                    'buffer_size': info.bufferSize,
                    'sample_rate': info.sampleRate
                }
            return None
        except Exception as e:
            logger.error(f"Error getting engine info: {e}")
            return None
    
    def set_parameter_value(self, plugin_id: int, parameter_id: int, value: float) -> bool:
        """Set a plugin parameter value"""
        if not self.host or not self.initialized:
            return False
        try:
            self.host.set_parameter_value(plugin_id, parameter_id, value)
            return True
        except Exception as e:
            logger.error(f"Error setting parameter {parameter_id} for plugin {plugin_id}: {e}")
            return False
    
    def get_parameter_value(self, plugin_id: int, parameter_id: int) -> Optional[float]:
        """Get current parameter value"""
        if not self.host or not self.initialized:
            return None
        try:
            return self.host.get_current_parameter_value(plugin_id, parameter_id)
        except Exception as e:
            logger.error(f"Error getting parameter {parameter_id} for plugin {plugin_id}: {e}")
            return None
    
    def __del__(self):
        """Cleanup when client is destroyed"""
        self.close_engine()