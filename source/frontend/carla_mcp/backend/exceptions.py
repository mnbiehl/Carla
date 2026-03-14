"""
Custom exceptions for Carla MCP Server backend operations
"""


class CarlaBackendError(Exception):
    """Base exception for Carla backend operations"""
    pass


class CarlaConnectionError(CarlaBackendError):
    """Exception raised when connection to Carla fails"""
    pass


class CarlaPluginError(CarlaBackendError):
    """Exception raised for plugin-related operations"""
    pass


class CarlaParameterError(CarlaBackendError):
    """Exception raised for parameter operations"""
    pass


class CarlaTransportError(CarlaBackendError):
    """Exception raised for transport operations"""
    pass


class CarlaSessionError(CarlaBackendError):
    """Exception raised for session/project operations"""
    pass