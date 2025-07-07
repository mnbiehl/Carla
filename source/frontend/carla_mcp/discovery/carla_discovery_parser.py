"""
Parser for Carla discovery tool output

Parses the structured output from carla-discovery-native to extract
plugin metadata and information.
"""

import logging
import subprocess
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class PluginInfo:
    """Plugin information extracted from discovery"""
    name: str
    maker: str
    label: str
    category: str
    plugin_type: str
    plugin_path: str
    
    # Audio/MIDI capabilities
    audio_ins: int = 0
    audio_outs: int = 0
    cv_ins: int = 0
    cv_outs: int = 0
    midi_ins: int = 0
    midi_outs: int = 0
    
    # Parameters
    parameters_ins: int = 0
    parameters_outs: int = 0
    
    # Additional metadata
    hints: int = 0
    unique_id: Optional[int] = None
    build: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        # Map plugin type strings to GUI constants (matching carla_backend.py)
        PLUGIN_TYPE_MAP = {
            "internal": 1, "ladspa": 2, "dssi": 3, "lv2": 4, "vst2": 5,
            "vst3": 6, "au": 7, "sf2": 8, "sfz": 9, "jack": 12
        }
        
        return {
            'name': self.name,
            'maker': self.maker,
            'label': self.label,
            'category': self.category,
            'plugin_type': self.plugin_type,  # Keep original for MCP API
            'type': PLUGIN_TYPE_MAP.get(self.plugin_type.lower(), 4),  # GUI-compatible integer (default to LV2=4)
            'filename': self.plugin_path,  # Always use bundle path for filename
            'plugin_path': self.plugin_path,
            'audio_ins': self.audio_ins,
            'audio_outs': self.audio_outs,
            'cv_ins': self.cv_ins,
            'cv_outs': self.cv_outs,
            'midi_ins': self.midi_ins,
            'midi_outs': self.midi_outs,
            'parameters_ins': self.parameters_ins,
            'parameters_outs': self.parameters_outs,
            'hints': self.hints,
            'unique_id': self.unique_id,
            'uniqueId': self.unique_id,  # GUI-compatible field name
            'build': self.build
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PluginInfo':
        """Create from dictionary, filtering out extra fields"""
        import inspect
        
        # Get the valid field names from the dataclass
        sig = inspect.signature(cls.__init__)
        valid_fields = set(sig.parameters.keys()) - {'self'}
        
        # Filter the data to only include valid fields
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        
        return cls(**filtered_data)


class CarlaDiscoveryParser:
    """Parser for carla-discovery-native output"""
    
    DISCOVERY_TOOL_PATH = "/usr/lib/carla/carla-discovery-native"
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def discover_plugin(self, plugin_type: str, plugin_path: str) -> Optional[PluginInfo]:
        """
        Discover a single plugin using carla-discovery-native
        
        Args:
            plugin_type: Plugin type (lv2, ladspa, vst2, vst3, etc.)
            plugin_path: Path to plugin file or bundle
            
        Returns:
            PluginInfo object or None if discovery failed
        """
        try:
            # Run carla-discovery-native
            cmd = [self.DISCOVERY_TOOL_PATH, plugin_type.lower(), plugin_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode != 0:
                self.logger.warning(f"Discovery failed for {plugin_path}: {result.stderr}")
                return None
            
            # Parse the output
            return self._parse_discovery_output(result.stdout, plugin_type, plugin_path)
            
        except subprocess.TimeoutExpired:
            self.logger.error(f"Discovery timeout for {plugin_path}")
            return None
        except Exception as e:
            self.logger.error(f"Discovery error for {plugin_path}: {e}")
            return None
    
    def _parse_discovery_output(self, output: str, plugin_type: str, plugin_path: str) -> Optional[PluginInfo]:
        """
        Parse carla-discovery-native output
        
        Args:
            output: Raw output from discovery tool
            plugin_type: Plugin type
            plugin_path: Plugin path
            
        Returns:
            PluginInfo object or None if parsing failed
        """
        try:
            lines = output.strip().split('\n')
            
            # Initialize plugin info
            plugin_info = {
                'plugin_type': plugin_type,
                'plugin_path': plugin_path,
                'name': '',
                'maker': '',
                'label': '',
                'category': 'none',
                'audio_ins': 0,
                'audio_outs': 0,
                'cv_ins': 0,
                'cv_outs': 0,
                'midi_ins': 0,
                'midi_outs': 0,
                'parameters_ins': 0,
                'parameters_outs': 0,
                'hints': 0,
                'unique_id': None,
                'build': None
            }
            
            # Parse each line
            for line in lines:
                if '::' not in line:
                    continue
                
                parts = line.split('::', 2)
                if len(parts) < 3:
                    continue
                
                key = parts[1]
                value = parts[2]
                
                # Map discovery fields to our plugin info
                if key == 'name':
                    plugin_info['name'] = value
                elif key == 'maker':
                    plugin_info['maker'] = value
                elif key == 'label':
                    plugin_info['label'] = value
                elif key == 'category':
                    plugin_info['category'] = value
                elif key == 'hints':
                    plugin_info['hints'] = int(value) if value.isdigit() else 0
                elif key == 'uniqueId':
                    plugin_info['unique_id'] = int(value) if value.isdigit() else None
                elif key == 'build':
                    plugin_info['build'] = int(value) if value.isdigit() else None
                elif key == 'audio.ins':
                    plugin_info['audio_ins'] = int(value) if value.isdigit() else 0
                elif key == 'audio.outs':
                    plugin_info['audio_outs'] = int(value) if value.isdigit() else 0
                elif key == 'cv.ins':
                    plugin_info['cv_ins'] = int(value) if value.isdigit() else 0
                elif key == 'cv.outs':
                    plugin_info['cv_outs'] = int(value) if value.isdigit() else 0
                elif key == 'midi.ins':
                    plugin_info['midi_ins'] = int(value) if value.isdigit() else 0
                elif key == 'midi.outs':
                    plugin_info['midi_outs'] = int(value) if value.isdigit() else 0
                elif key == 'parameters.ins':
                    plugin_info['parameters_ins'] = int(value) if value.isdigit() else 0
                elif key == 'parameters.outs':
                    plugin_info['parameters_outs'] = int(value) if value.isdigit() else 0
            
            # Validate required fields
            if not plugin_info['name']:
                self.logger.warning(f"No name found for plugin {plugin_path}")
                return None
            
            return PluginInfo(**plugin_info)
            
        except Exception as e:
            self.logger.error(f"Error parsing discovery output for {plugin_path}: {e}")
            return None
    
    def get_plugin_categories(self) -> List[str]:
        """Get list of known plugin categories"""
        return [
            'none',
            'synth',
            'delay',
            'eq',
            'filter',
            'distortion',
            'dynamics',
            'modulator',
            'utility',
            'other'
        ]
    
    def is_discovery_tool_available(self) -> bool:
        """Check if carla-discovery-native is available"""
        try:
            # Check if file exists and is executable
            import os
            if not os.path.isfile(self.DISCOVERY_TOOL_PATH):
                return False
            if not os.access(self.DISCOVERY_TOOL_PATH, os.X_OK):
                return False
            
            # Test that it runs and shows usage
            result = subprocess.run([self.DISCOVERY_TOOL_PATH], 
                                  capture_output=True, text=True, timeout=5)
            # Tool should exit with error when called without arguments and show usage
            return "usage:" in result.stderr.lower() or "usage:" in result.stdout.lower()
        except Exception as e:
            self.logger.debug(f"Discovery tool check failed: {e}")
            return False