"""Wrapper around pw-link for PipeWire audio connections."""

import logging
import re
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


_MONITOR_OUTPUT_RE = re.compile(r"^alsa_output\..*pro-output.*:playback_AUX\d+$")
_CAPTURE_INPUT_RE = re.compile(r"^alsa_input\..*pro-input.*:capture_AUX\d+$")


def find_monitor_output_ports() -> list[str]:
    """Find ALSA pro-output playback ports (monitor outputs) via pw-link."""
    ports = pw_link_list_inputs()
    return sorted(p for p in ports if _MONITOR_OUTPUT_RE.match(p))


def find_capture_input_ports() -> list[str]:
    """Find ALSA pro-input capture ports (hardware inputs) via pw-link."""
    ports = pw_link_list_outputs()
    return sorted(p for p in ports if _CAPTURE_INPUT_RE.match(p))


def ensure_carla_to_monitors(carla_client: str = "Carla") -> dict:
    """Connect Carla audio outputs to monitor playback ports.

    Returns dict with keys: connected, already_connected, failed, monitor_ports.
    """
    monitor_ports = find_monitor_output_ports()
    connected = 0
    already_connected = 0
    failed = 0

    for i, monitor_port in enumerate(monitor_ports[:2]):
        source = f"{carla_client}:audio-out{i + 1}"
        if pw_link_verify(source, monitor_port):
            already_connected += 1
        else:
            result = pw_link_connect(source, monitor_port)
            if result.success:
                connected += 1
            else:
                failed += 1
                logger.warning(
                    "Failed to connect %s -> %s: %s",
                    source, monitor_port, result.message,
                )

    return {
        "connected": connected,
        "already_connected": already_connected,
        "failed": failed,
        "monitor_ports": monitor_ports,
    }


