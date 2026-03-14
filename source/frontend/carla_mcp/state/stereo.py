"""
Stereo pair detection and handling.

Recognizes common stereo naming conventions:
- _L / _R
- _left / _right
- _1 / _2 (context dependent)
"""

import re
from typing import Tuple, Optional, Literal

ChannelType = Literal["left", "right", "mono"]

# Patterns for stereo channel detection
LEFT_PATTERNS = [r"_L$", r"_left$", r"_l$"]
RIGHT_PATTERNS = [r"_R$", r"_right$", r"_r$"]


def get_channel_type(port_name: str) -> ChannelType:
    """Determine if port is left, right, or mono."""
    for pattern in LEFT_PATTERNS:
        if re.search(pattern, port_name, re.IGNORECASE):
            return "left"
    for pattern in RIGHT_PATTERNS:
        if re.search(pattern, port_name, re.IGNORECASE):
            return "right"
    return "mono"


def split_stereo_name(port_name: str) -> Tuple[str, Optional[str]]:
    """Split port name into base and channel suffix.

    Returns:
        (base_name, channel_suffix) or (port_name, None) if mono
    """
    for pattern in LEFT_PATTERNS + RIGHT_PATTERNS:
        match = re.search(pattern, port_name, re.IGNORECASE)
        if match:
            base = port_name[:match.start()]
            suffix = port_name[match.start() + 1:]  # Skip underscore
            return base, suffix
    return port_name, None


def get_stereo_pair(port_name: str) -> Tuple[str, str]:
    """Given one channel of a stereo pair, return (left, right).

    Args:
        port_name: Either channel of a stereo pair

    Returns:
        Tuple of (left_port, right_port)
    """
    base, suffix = split_stereo_name(port_name)
    if suffix is None:
        raise ValueError(f"Port {port_name} is not part of a stereo pair")

    # Preserve case of original suffix
    if suffix.isupper():
        return f"{base}_L", f"{base}_R"
    elif suffix == "left":
        return f"{base}_left", f"{base}_right"
    elif suffix == "right":
        return f"{base}_left", f"{base}_right"
    else:
        return f"{base}_l", f"{base}_r"


def is_stereo_pair(port_a: str, port_b: str) -> bool:
    """Check if two ports form a stereo pair."""
    type_a = get_channel_type(port_a)
    type_b = get_channel_type(port_b)

    # Must be one left and one right
    if not ((type_a == "left" and type_b == "right") or
            (type_a == "right" and type_b == "left")):
        return False

    # Must have same base name
    base_a, _ = split_stereo_name(port_a)
    base_b, _ = split_stereo_name(port_b)

    return base_a == base_b
