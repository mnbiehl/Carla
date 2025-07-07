"""
Validation utilities for Carla MCP Server

Input validation and sanitization functions.
"""

from typing import Any, Union


def validate_plugin_id(plugin_id: Any) -> int:
    """
    Validate plugin ID parameter
    
    Args:
        plugin_id: Plugin ID to validate
        
    Returns:
        Validated plugin ID as integer
        
    Raises:
        ValueError: If plugin ID is invalid
    """
    if not isinstance(plugin_id, int):
        try:
            plugin_id = int(plugin_id)
        except (ValueError, TypeError):
            raise ValueError("Plugin ID must be an integer")
    
    if plugin_id < 0:
        raise ValueError("Plugin ID must be non-negative")
    
    return plugin_id


def validate_parameter_id(parameter_id: Any) -> int:
    """
    Validate parameter ID
    
    Args:
        parameter_id: Parameter ID to validate
        
    Returns:
        Validated parameter ID as integer
        
    Raises:
        ValueError: If parameter ID is invalid
    """
    if not isinstance(parameter_id, int):
        try:
            parameter_id = int(parameter_id)
        except (ValueError, TypeError):
            raise ValueError("Parameter ID must be an integer")
    
    if parameter_id < 0:
        raise ValueError("Parameter ID must be non-negative")
    
    return parameter_id


def validate_volume(volume: Any) -> float:
    """
    Validate volume level
    
    Args:
        volume: Volume level to validate
        
    Returns:
        Validated volume as float
        
    Raises:
        ValueError: If volume is out of range
    """
    if not isinstance(volume, (int, float)):
        try:
            volume = float(volume)
        except (ValueError, TypeError):
            raise ValueError("Volume must be a number")
    
    if not (0.0 <= volume <= 1.27):
        raise ValueError("Volume must be between 0.0 and 1.27")
    
    return float(volume)


def validate_midi_channel(channel: Any) -> int:
    """
    Validate MIDI channel
    
    Args:
        channel: MIDI channel to validate
        
    Returns:
        Validated MIDI channel as integer
        
    Raises:
        ValueError: If MIDI channel is out of range
    """
    if not isinstance(channel, int):
        try:
            channel = int(channel)
        except (ValueError, TypeError):
            raise ValueError("MIDI channel must be an integer")
    
    if not (0 <= channel <= 15):
        raise ValueError("MIDI channel must be between 0 and 15")
    
    return channel


def validate_midi_note(note: Any) -> int:
    """
    Validate MIDI note number
    
    Args:
        note: MIDI note to validate
        
    Returns:
        Validated MIDI note as integer
        
    Raises:
        ValueError: If MIDI note is out of range
    """
    if not isinstance(note, int):
        try:
            note = int(note)
        except (ValueError, TypeError):
            raise ValueError("MIDI note must be an integer")
    
    if not (0 <= note <= 127):
        raise ValueError("MIDI note must be between 0 and 127")
    
    return note


def validate_midi_velocity(velocity: Any) -> int:
    """
    Validate MIDI velocity
    
    Args:
        velocity: MIDI velocity to validate
        
    Returns:
        Validated MIDI velocity as integer
        
    Raises:
        ValueError: If MIDI velocity is out of range
    """
    if not isinstance(velocity, int):
        try:
            velocity = int(velocity)
        except (ValueError, TypeError):
            raise ValueError("MIDI velocity must be an integer")
    
    if not (0 <= velocity <= 127):
        raise ValueError("MIDI velocity must be between 0 and 127")
    
    return velocity