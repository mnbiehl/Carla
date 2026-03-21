"""Async TCP client for looperdooper's JSON remote control server."""

import asyncio
import json
import logging

logger = logging.getLogger(__name__)


class LooperClient:
    """Connects to looperdooper's JSON TCP server and sends commands."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8088):
        self.host = host
        self.port = port

    async def _send_and_recv(self, payload: str) -> dict:
        """Send a JSON line and read the response."""
        try:
            reader, writer = await asyncio.open_connection(self.host, self.port)
        except (ConnectionRefusedError, OSError) as e:
            raise ConnectionError(
                f"Cannot connect to looperdooper at {self.host}:{self.port}: {e}"
            ) from e
        try:
            writer.write((payload + "\n").encode())
            await writer.drain()
            line = await reader.readline()
            return json.loads(line.decode())
        finally:
            writer.close()
            await writer.wait_closed()

    async def send_command(self, command) -> dict:
        """Send a Command (serde JSON) to looperdooper. Returns response dict."""
        payload = json.dumps(command)
        return await self._send_and_recv(payload)

    async def get_state(self) -> dict:
        """Query looperdooper engine state. Returns state snapshot dict."""
        return await self._send_and_recv('"GetState"')
