"""
Human/agent-readable ASCII summary of a RigGraph.

Renders two sections — ROUTING then CHAINS — that give a complete
situational-awareness snapshot of the in-memory rig graph.

NOTE: live pw-link connection state is intentionally NOT included here;
this renders the in-memory RigGraph only.
"""

from __future__ import annotations

from carla_mcp.rig.graph import RigGraph


def _format_gain(gain_db: float) -> str:
    """Return a compact dB suffix string, e.g. ' (-12 dB)'.

    Strips trailing zeros after the decimal point.
    Returns an empty string when *gain_db* is exactly 0.0.
    """
    if gain_db == 0.0:
        return ""
    # Format with enough precision then strip trailing zeros/point.
    formatted = f"{gain_db:g}"
    return f" ({formatted} dB)"


def _routing_lines(graph: RigGraph) -> list[str]:
    """Return the body lines for the ROUTING section."""
    lines: list[str] = []
    for name in graph.nodes:
        for edge in graph.edges_from(name):
            gain_suffix = _format_gain(edge.gain_db)
            lines.append(f"  {edge.src} → {edge.dst}{gain_suffix}")
    if not lines:
        return ["  (no routes)"]
    return lines


def _chain_lines(graph: RigGraph) -> list[str]:
    """Return the body lines for the CHAINS section."""
    lines: list[str] = []
    for name, node in graph.nodes.items():
        if node.kind == "endpoint":
            continue
        if node.effects:
            roles = " ▸ ".join(
                (eff.role + "*" if eff.bypassed else eff.role)
                for eff in node.effects
            )
        else:
            roles = "(no effects)"
        suffix = " (loop: dry)" if node.kind == "track" else ""
        lines.append(f"  {name}: {roles}{suffix}")
    if not lines:
        return ["  (no chains)"]
    return lines


def describe_rig(graph: RigGraph) -> str:
    """Render a human/agent-readable ASCII summary of *graph*.

    Returns a string with two sections:

    ROUTING
      One line per edge grouped by source node in insertion order.
      Gain suffix omitted when gain_db == 0.0.

    CHAINS
      One line per track or bus node in insertion order.
      Endpoints are skipped.  Bypassed effects have a trailing ``*``.
      Track nodes append ``(loop: dry)`` to indicate the loop is captured
      pre-effects.

    Args:
        graph: The in-memory RigGraph to summarise.

    Returns:
        A multi-line string suitable for display to a human or agent.
    """
    routing = ["ROUTING"] + _routing_lines(graph)
    chains = ["CHAINS"] + _chain_lines(graph)
    return "\n".join(routing) + "\n\n" + "\n".join(chains)
