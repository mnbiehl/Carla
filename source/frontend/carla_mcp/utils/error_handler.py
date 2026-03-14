"""
Centralized error handling utilities for Carla MCP Server

Provides consistent error reporting with Carla backend error details.
"""

import logging
from typing import Optional, Any
from ..backend.carla_client import CarlaBackendClient

logger = logging.getLogger(__name__)


class CarlaErrorHandler:
    """Centralized error handler for Carla MCP operations"""
    
    def __init__(self, backend_client: Optional[CarlaBackendClient] = None):
        self.backend_client = backend_client
    
    def format_error(self, 
                    operation: str, 
                    base_message: str, 
                    exception: Optional[Exception] = None,
                    include_carla_error: bool = True) -> str:
        """
        Format a comprehensive error message
        
        Args:
            operation: The operation that failed (e.g., "add plugin", "initialize engine")
            base_message: Base error message
            exception: Python exception if any
            include_carla_error: Whether to include Carla backend error
            
        Returns:
            Formatted error message
        """
        error_parts = [f"❌ {base_message}"]
        
        # Add Carla backend error if available
        if include_carla_error and self.backend_client and self.backend_client.host:
            try:
                carla_error = self.backend_client.host.get_last_error()
                if carla_error and carla_error.strip():
                    # Clean up ANSI color codes from Carla errors
                    clean_error = self._clean_ansi_codes(carla_error)
                    error_parts.append(f"Carla error: {clean_error}")
            except Exception as e:
                logger.debug(f"Could not get Carla error: {e}")
        
        # Add Python exception if provided
        if exception:
            error_parts.append(f"Python error: {str(exception)}")
            logger.error(f"Operation '{operation}' failed: {exception}", exc_info=True)
        
        # Log the full error
        full_message = "\n".join(error_parts)
        logger.error(f"Operation '{operation}' failed: {full_message}")
        
        return full_message
    
    def format_success(self, message: str, operation: str = "") -> str:
        """
        Format a success message
        
        Args:
            message: Success message
            operation: The operation that succeeded
            
        Returns:
            Formatted success message
        """
        if operation:
            logger.info(f"Operation '{operation}' succeeded: {message}")
        else:
            logger.info(f"Success: {message}")
        
        return f"✅ {message}"
    
    def format_warning(self, message: str, operation: str = "") -> str:
        """
        Format a warning message
        
        Args:
            message: Warning message
            operation: The operation that generated the warning
            
        Returns:
            Formatted warning message
        """
        if operation:
            logger.warning(f"Operation '{operation}' warning: {message}")
        else:
            logger.warning(f"Warning: {message}")
        
        return f"⚠️ {message}"
    
    def _clean_ansi_codes(self, text: str) -> str:
        """Remove ANSI color codes from text"""
        import re
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        return ansi_escape.sub('', text)
    
    def handle_backend_operation(self, 
                                operation: str,
                                operation_func,
                                success_message: str,
                                error_message: str,
                                *args, **kwargs) -> str:
        """
        Handle a backend operation with consistent error reporting
        
        Args:
            operation: Name of the operation
            operation_func: Function to execute
            success_message: Message to return on success
            error_message: Base error message
            *args, **kwargs: Arguments to pass to operation_func
            
        Returns:
            Formatted result message
        """
        try:
            result = operation_func(*args, **kwargs)
            
            if isinstance(result, bool):
                if result:
                    return self.format_success(success_message, operation)
                else:
                    return self.format_error(operation, error_message)
            else:
                # Assume success if we got a result
                return self.format_success(success_message, operation)
                
        except Exception as e:
            return self.format_error(operation, error_message, exception=e)
    
    def check_prerequisites(self, 
                          backend_required: bool = True,
                          engine_required: bool = False) -> Optional[str]:
        """
        Check if prerequisites are met for an operation
        
        Args:
            backend_required: Whether backend client is required
            engine_required: Whether initialized engine is required
            
        Returns:
            Error message if prerequisites not met, None if OK
        """
        if backend_required:
            if not self.backend_client:
                return self.format_error("prerequisite check", 
                                       "Backend client not available")
            
            try:
                from ..backend.carla_client import CARLA_BACKEND_AVAILABLE
                if not CARLA_BACKEND_AVAILABLE:
                    return self.format_error("prerequisite check",
                                           "Carla backend API not available. Please install Carla with Python bindings.")
            except ImportError:
                return self.format_error("prerequisite check",
                                       "Carla backend module not found")
        
        if engine_required and self.backend_client:
            if not self.backend_client.initialized:
                return self.format_error("prerequisite check",
                                       "Carla engine not initialized. Please initialize the engine first.")
        
        return None


# Global error handler instance - will be initialized with backend client
error_handler: Optional[CarlaErrorHandler] = None


def init_error_handler(backend_client: Optional[CarlaBackendClient] = None):
    """Initialize the global error handler"""
    global error_handler
    error_handler = CarlaErrorHandler(backend_client)


def get_error_handler() -> CarlaErrorHandler:
    """Get the global error handler (creates one if not initialized)"""
    global error_handler
    if error_handler is None:
        error_handler = CarlaErrorHandler()
    return error_handler


# Convenience functions for common error patterns
def backend_error(operation: str, base_message: str, exception: Optional[Exception] = None) -> str:
    """Quick backend error formatting"""
    return get_error_handler().format_error(operation, base_message, exception)


def backend_success(message: str, operation: str = "") -> str:
    """Quick success formatting"""
    return get_error_handler().format_success(message, operation)


def backend_warning(message: str, operation: str = "") -> str:
    """Quick warning formatting"""
    return get_error_handler().format_warning(message, operation)


def check_prerequisites(backend_required: bool = True, engine_required: bool = False) -> Optional[str]:
    """Quick prerequisite check"""
    return get_error_handler().check_prerequisites(backend_required, engine_required)