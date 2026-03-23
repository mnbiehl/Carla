"""Wrapper around pw-link for PipeWire audio connections."""

import logging
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class PwLinkResult:
    success: bool
    message: str = ""


def pw_link_connect(source: str, destination: str) -> PwLinkResult:
    """Connect two PipeWire ports via pw-link."""
    try:
        result = subprocess.run(
            ["pw-link", source, destination],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            logger.info("Connected %s -> %s", source, destination)
            return PwLinkResult(success=True)
        else:
            logger.error(
                "Failed to connect %s -> %s: %s", source, destination, result.stderr
            )
            return PwLinkResult(success=False, message=result.stderr.strip())
    except subprocess.TimeoutExpired:
        msg = f"Timeout connecting {source} -> {destination}"
        logger.error(msg)
        return PwLinkResult(success=False, message=msg)
    except FileNotFoundError:
        msg = "pw-link not found — is PipeWire installed?"
        logger.error(msg)
        return PwLinkResult(success=False, message=msg)


def pw_link_disconnect(source: str, destination: str) -> PwLinkResult:
    """Disconnect two PipeWire ports via pw-link -d."""
    try:
        result = subprocess.run(
            ["pw-link", "-d", source, destination],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            logger.info("Disconnected %s -> %s", source, destination)
            return PwLinkResult(success=True)
        else:
            logger.error(
                "Failed to disconnect %s -> %s: %s",
                source,
                destination,
                result.stderr,
            )
            return PwLinkResult(success=False, message=result.stderr.strip())
    except subprocess.TimeoutExpired:
        msg = f"Timeout disconnecting {source} -> {destination}"
        logger.error(msg)
        return PwLinkResult(success=False, message=msg)
    except FileNotFoundError:
        msg = "pw-link not found — is PipeWire installed?"
        logger.error(msg)
        return PwLinkResult(success=False, message=msg)


def pw_link_list_outputs() -> list[str]:
    """List all PipeWire output ports via pw-link -o."""
    try:
        result = subprocess.run(
            ["pw-link", "-o"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return [line for line in result.stdout.strip().splitlines() if line.strip()]
        return []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.error("Failed to list PipeWire output ports")
        return []


def pw_link_list_inputs() -> list[str]:
    """List all PipeWire input ports via pw-link -i."""
    try:
        result = subprocess.run(
            ["pw-link", "-i"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return [line for line in result.stdout.strip().splitlines() if line.strip()]
        return []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.error("Failed to list PipeWire input ports")
        return []


def pw_link_verify(source: str, destination: str) -> bool:
    """Verify a connection exists between two ports via pw-link -l.

    Parses pw-link -l output where source ports appear on non-indented lines
    and connected destinations appear on indented lines below them.
    """
    try:
        result = subprocess.run(
            ["pw-link", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return False

        current_source = None
        for line in result.stdout.splitlines():
            if not line.startswith((" ", "\t")):
                current_source = line.strip()
            else:
                if current_source == source and line.strip() == destination:
                    return True
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError):
        logger.error("Failed to verify PipeWire connection")
        return False
