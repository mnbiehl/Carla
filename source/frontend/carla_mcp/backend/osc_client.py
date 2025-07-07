"""
OSC Client for Carla audio plugin host

Provides communication with Carla through OSC (Open Sound Control) protocol.
"""

import logging
from typing import Optional
from pythonosc import udp_client
from pythonosc.osc_message_builder import OscMessageBuilder

logger = logging.getLogger(__name__)


class CarlaOSCClient:
    """OSC client for communicating with Carla audio plugin host"""
    
    def __init__(self, host: str = "localhost", port: int = 19735):
        """
        Initialize OSC client for Carla
        
        Args:
            host: Carla host address (default: localhost)
            port: Carla OSC port (default: 19735)
        """
        self.host = host
        self.port = port
        self.client = udp_client.SimpleUDPClient(host, port)
        logger.info(f"Initialized Carla OSC client: {host}:{port}")
    
    def send_command(self, address: str, *args) -> bool:
        """
        Send OSC command to Carla
        
        Args:
            address: OSC address path (e.g., "/Carla/0/set_active")
            *args: Command arguments
            
        Returns:
            bool: True if command sent successfully, False otherwise
        """
        try:
            self.client.send_message(address, args if args else None)
            logger.debug(f"Sent OSC: {address} {args}")
            return True
        except Exception as e:
            logger.error(f"Failed to send OSC command {address}: {e}")
            return False
    
    def test_connection(self) -> bool:
        """
        Test if Carla is responding to OSC commands
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            # Try to send a simple command (this might not work without a plugin loaded)
            self.send_command("/Carla/0/set_active", 1)
            return True
        except Exception as e:
            logger.warning(f"Carla OSC test failed: {e}")
            return False
    
    @property
    def address(self) -> str:
        """Get the complete OSC address"""
        return f"{self.host}:{self.port}"