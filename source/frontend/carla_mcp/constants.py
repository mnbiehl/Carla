"""
Centralized constants for Carla MCP Server

Single source of truth for all Carla backend constants.
This module imports constants from carla_backend.py and provides
convenient mappings and utilities.
"""

import sys
import platform
import logging
from pathlib import Path
from typing import Dict, Optional

# Add parent directory to import carla_backend
carla_frontend_path = Path(__file__).parent.parent
if str(carla_frontend_path) not in sys.path:
    sys.path.insert(0, str(carla_frontend_path))

logger = logging.getLogger(__name__)

# Import all plugin type constants from carla_backend
try:
    from carla_backend import (
        # Plugin types
        PLUGIN_NONE, PLUGIN_INTERNAL, PLUGIN_LADSPA, PLUGIN_DSSI,
        PLUGIN_LV2, PLUGIN_VST2, PLUGIN_VST3, PLUGIN_AU,
        PLUGIN_DLS, PLUGIN_GIG, PLUGIN_SF2, PLUGIN_SFZ,
        PLUGIN_JACK, PLUGIN_JSFX,
        
        # Binary types
        BINARY_NONE, BINARY_POSIX32, BINARY_POSIX64,
        BINARY_WIN32, BINARY_WIN64, BINARY_OTHER,
        BINARY_NATIVE,
        
        # Engine process modes
        ENGINE_PROCESS_MODE_SINGLE_CLIENT,
        ENGINE_PROCESS_MODE_MULTIPLE_CLIENTS,
        ENGINE_PROCESS_MODE_CONTINUOUS_RACK,
        ENGINE_PROCESS_MODE_PATCHBAY,
        
        # Plugin options
        PLUGIN_OPTION_FIXED_BUFFERS,
        PLUGIN_OPTION_FORCE_STEREO,
        PLUGIN_OPTION_MAP_PROGRAM_CHANGES,
        PLUGIN_OPTION_USE_CHUNKS,
        PLUGIN_OPTION_SEND_CONTROL_CHANGES,
        PLUGIN_OPTION_SEND_CHANNEL_PRESSURE,
        PLUGIN_OPTION_SEND_NOTE_AFTERTOUCH,
        PLUGIN_OPTION_SEND_PITCHBEND,
        PLUGIN_OPTION_SEND_ALL_SOUND_OFF,
        
        # Plugin categories
        PLUGIN_CATEGORY_NONE,
        PLUGIN_CATEGORY_SYNTH,
        PLUGIN_CATEGORY_DELAY,
        PLUGIN_CATEGORY_EQ,
        PLUGIN_CATEGORY_FILTER,
        PLUGIN_CATEGORY_DISTORTION,
        PLUGIN_CATEGORY_DYNAMICS,
        PLUGIN_CATEGORY_MODULATOR,
        PLUGIN_CATEGORY_UTILITY,
        PLUGIN_CATEGORY_OTHER,
        
        # Engine options
        ENGINE_OPTION_DEBUG,
        ENGINE_OPTION_PROCESS_MODE,
        ENGINE_OPTION_TRANSPORT_MODE,
        ENGINE_OPTION_FORCE_STEREO,
        ENGINE_OPTION_PREFER_PLUGIN_BRIDGES,
        ENGINE_OPTION_PREFER_UI_BRIDGES,
        ENGINE_OPTION_UIS_ALWAYS_ON_TOP,
        ENGINE_OPTION_MAX_PARAMETERS,
        ENGINE_OPTION_RESET_XRUNS,
        ENGINE_OPTION_UI_BRIDGES_TIMEOUT,
        ENGINE_OPTION_AUDIO_BUFFER_SIZE,
        ENGINE_OPTION_AUDIO_SAMPLE_RATE,
        ENGINE_OPTION_AUDIO_TRIPLE_BUFFER,
        ENGINE_OPTION_AUDIO_DRIVER,
        ENGINE_OPTION_AUDIO_DEVICE,
        ENGINE_OPTION_OSC_ENABLED,
    )
    # Try to import newer constants that may not be available
    try:
        from carla_backend import PLUGIN_CLAP
    except ImportError:
        PLUGIN_CLAP = 14  # Default value
        
    logger.info("Successfully imported constants from carla_backend")
except ImportError as e:
    logger.error(f"Failed to import carla_backend constants: {e}")
    # Define fallback values if import fails
    PLUGIN_NONE = 0
    PLUGIN_INTERNAL = 1
    PLUGIN_LADSPA = 2
    PLUGIN_DSSI = 3
    PLUGIN_LV2 = 4
    PLUGIN_VST2 = 5
    PLUGIN_VST3 = 6
    PLUGIN_AU = 7
    PLUGIN_DLS = 8
    PLUGIN_GIG = 9
    PLUGIN_SF2 = 10
    PLUGIN_SFZ = 11
    PLUGIN_JACK = 12
    PLUGIN_JSFX = 13
    PLUGIN_CLAP = 14
    
    BINARY_NONE = 0
    BINARY_POSIX32 = 1
    BINARY_POSIX64 = 2
    BINARY_WIN32 = 3
    BINARY_WIN64 = 4
    BINARY_OTHER = 5
    BINARY_NATIVE = 0  # Will be corrected by get_native_binary_type()
    
    ENGINE_PROCESS_MODE_SINGLE_CLIENT = 0
    ENGINE_PROCESS_MODE_MULTIPLE_CLIENTS = 1
    ENGINE_PROCESS_MODE_CONTINUOUS_RACK = 2
    ENGINE_PROCESS_MODE_PATCHBAY = 3
    
    # Plugin options
    PLUGIN_OPTION_FIXED_BUFFERS = 0x001
    PLUGIN_OPTION_FORCE_STEREO = 0x002
    PLUGIN_OPTION_MAP_PROGRAM_CHANGES = 0x004
    PLUGIN_OPTION_USE_CHUNKS = 0x008
    PLUGIN_OPTION_SEND_CONTROL_CHANGES = 0x010
    PLUGIN_OPTION_SEND_CHANNEL_PRESSURE = 0x020
    PLUGIN_OPTION_SEND_NOTE_AFTERTOUCH = 0x040
    PLUGIN_OPTION_SEND_PITCHBEND = 0x080
    PLUGIN_OPTION_SEND_ALL_SOUND_OFF = 0x100
    
    # Plugin categories
    PLUGIN_CATEGORY_NONE = 0
    PLUGIN_CATEGORY_SYNTH = 1
    PLUGIN_CATEGORY_DELAY = 2
    PLUGIN_CATEGORY_EQ = 3
    PLUGIN_CATEGORY_FILTER = 4
    PLUGIN_CATEGORY_DISTORTION = 5
    PLUGIN_CATEGORY_DYNAMICS = 6
    PLUGIN_CATEGORY_MODULATOR = 7
    PLUGIN_CATEGORY_UTILITY = 8
    PLUGIN_CATEGORY_OTHER = 9
    
    # Engine options
    ENGINE_OPTION_DEBUG = 0
    ENGINE_OPTION_PROCESS_MODE = 1
    ENGINE_OPTION_TRANSPORT_MODE = 2
    ENGINE_OPTION_FORCE_STEREO = 3
    ENGINE_OPTION_PREFER_PLUGIN_BRIDGES = 4
    ENGINE_OPTION_PREFER_UI_BRIDGES = 5
    ENGINE_OPTION_UIS_ALWAYS_ON_TOP = 6
    ENGINE_OPTION_MAX_PARAMETERS = 7
    ENGINE_OPTION_RESET_XRUNS = 8
    ENGINE_OPTION_UI_BRIDGES_TIMEOUT = 9
    ENGINE_OPTION_AUDIO_BUFFER_SIZE = 10
    ENGINE_OPTION_AUDIO_SAMPLE_RATE = 11
    ENGINE_OPTION_AUDIO_TRIPLE_BUFFER = 12
    ENGINE_OPTION_AUDIO_DRIVER = 13
    ENGINE_OPTION_AUDIO_DEVICE = 14
    ENGINE_OPTION_OSC_ENABLED = 15

# Create mappings for easy lookup
PLUGIN_TYPE_TO_STRING: Dict[int, str] = {
    PLUGIN_INTERNAL: "internal",
    PLUGIN_LADSPA: "ladspa",
    PLUGIN_DSSI: "dssi",
    PLUGIN_LV2: "lv2",
    PLUGIN_VST2: "vst2",
    PLUGIN_VST3: "vst3",
    PLUGIN_AU: "au",
    PLUGIN_DLS: "dls",
    PLUGIN_GIG: "gig", 
    PLUGIN_SF2: "sf2",
    PLUGIN_SFZ: "sfz",
    PLUGIN_JACK: "jack",
    PLUGIN_JSFX: "jsfx",
}

# Add CLAP if available
if 'PLUGIN_CLAP' in globals():
    PLUGIN_TYPE_TO_STRING[PLUGIN_CLAP] = "clap"

PLUGIN_STRING_TO_TYPE: Dict[str, int] = {v: k for k, v in PLUGIN_TYPE_TO_STRING.items()}

# Category mappings
PLUGIN_CATEGORY_TO_STRING: Dict[int, str] = {
    PLUGIN_CATEGORY_NONE: "none",
    PLUGIN_CATEGORY_SYNTH: "synth",
    PLUGIN_CATEGORY_DELAY: "delay",
    PLUGIN_CATEGORY_EQ: "eq",
    PLUGIN_CATEGORY_FILTER: "filter",
    PLUGIN_CATEGORY_DISTORTION: "distortion",
    PLUGIN_CATEGORY_DYNAMICS: "dynamics",
    PLUGIN_CATEGORY_MODULATOR: "modulator",
    PLUGIN_CATEGORY_UTILITY: "utility",
    PLUGIN_CATEGORY_OTHER: "other"
}

PLUGIN_STRING_TO_CATEGORY: Dict[str, int] = {v: k for k, v in PLUGIN_CATEGORY_TO_STRING.items()}

# Engine mode mappings
ENGINE_MODE_TO_STRING: Dict[int, str] = {
    ENGINE_PROCESS_MODE_SINGLE_CLIENT: "single_client",
    ENGINE_PROCESS_MODE_MULTIPLE_CLIENTS: "multiple_clients",
    ENGINE_PROCESS_MODE_CONTINUOUS_RACK: "continuous_rack",
    ENGINE_PROCESS_MODE_PATCHBAY: "patchbay"
}

ENGINE_STRING_TO_MODE: Dict[str, int] = {v: k for k, v in ENGINE_MODE_TO_STRING.items()}

# Patchbay port offset constants (from CarlaEngineGraph.cpp)
PATCHBAY_PORT_MAX = 255
PATCHBAY_PORT_AUDIO_INPUT_OFFSET = 255   # kAudioInputPortOffset
PATCHBAY_PORT_AUDIO_OUTPUT_OFFSET = 510  # kAudioOutputPortOffset
PATCHBAY_PORT_MIDI_INPUT_OFFSET = 1530   # From debug logs
PATCHBAY_PORT_MIDI_OUTPUT_OFFSET = 1275  # From debug logs

# Null plugin options constant
PLUGIN_OPTIONS_NULL = 0x0


def get_native_binary_type() -> int:
    """
    Get the correct binary type for the current platform.
    
    Returns:
        int: The BINARY_* constant for the current platform
    """
    # Check if we already cached the result
    if hasattr(sys, '_BINARY_NATIVE_CACHED'):
        return sys._BINARY_NATIVE_CACHED
    
    # Try to use the imported BINARY_NATIVE first
    if BINARY_NATIVE != BINARY_NONE:
        sys._BINARY_NATIVE_CACHED = BINARY_NATIVE
        return BINARY_NATIVE
    
    # Fallback: detect based on platform
    is_64bit = platform.machine() in ('x86_64', 'AMD64', 'aarch64', 'arm64')
    is_windows = platform.system() == 'Windows'
    
    if is_windows:
        native = BINARY_WIN64 if is_64bit else BINARY_WIN32
    else:
        native = BINARY_POSIX64 if is_64bit else BINARY_POSIX32
    
    logger.info(f"Detected native binary type: {native} (platform: {platform.system()}, arch: {platform.machine()})")
    sys._BINARY_NATIVE_CACHED = native
    return native


def validate_plugin_type(plugin_type: str) -> bool:
    """
    Validate if a plugin type string is recognized.
    
    Args:
        plugin_type: Plugin type string to validate
        
    Returns:
        bool: True if valid, False otherwise
    """
    return plugin_type.lower() in PLUGIN_STRING_TO_TYPE


def get_plugin_type_constant(plugin_type: str, default: int = PLUGIN_LV2) -> int:
    """
    Get plugin type constant from string, with default fallback.
    
    Args:
        plugin_type: Plugin type string
        default: Default constant if type not found
        
    Returns:
        int: Plugin type constant
    """
    return PLUGIN_STRING_TO_TYPE.get(plugin_type.lower(), default)


def get_plugin_type_string(plugin_type: int) -> Optional[str]:
    """
    Get plugin type string from constant.
    
    Args:
        plugin_type: Plugin type constant
        
    Returns:
        str: Plugin type string or None if not found
    """
    return PLUGIN_TYPE_TO_STRING.get(plugin_type)


def get_category_constant(category: str, default: int = PLUGIN_CATEGORY_NONE) -> int:
    """
    Get category constant from string.
    
    Args:
        category: Category string
        default: Default constant if category not found
        
    Returns:
        int: Category constant
    """
    return PLUGIN_STRING_TO_CATEGORY.get(category.lower(), default)


def get_category_string(category: int) -> Optional[str]:
    """
    Get category string from constant.
    
    Args:
        category: Category constant
        
    Returns:
        str: Category string or None if not found
    """
    return PLUGIN_CATEGORY_TO_STRING.get(category)


# Export commonly used values
NATIVE_BINARY_TYPE = get_native_binary_type()