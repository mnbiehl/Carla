"""Pure builder for the rig_state reply (phase 1: verdict, units, loops, links)."""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from carla_mcp.rig.describe import describe_rig
from carla_mcp.rig.graph import RigGraph, RuntimeUnit
from carla_mcp.rig.observe import ObservedState
from carla_mcp.rig.reconcile import diff, in_rig_port_space

DETAILS = ("normal", "diagram", "io")

# (name, kind) of the runtime units every rig needs — what rig_up starts, in
# start order. With no session loaded these are what rig_state observes and
# what its verdict checks (without them the verdict would say OK for a dead rig).
CORE_RUNTIME_UNITS: Tuple[Tuple[str, str], ...] = (
    ("looper:engine", "looper-engine"),
    ("a2j", "a2j"),
    ("carla:main", "carla-main"),
)


def core_runtime_units() -> List[RuntimeUnit]:
    return [RuntimeUnit(name=name, kind=kind) for name, kind in CORE_RUNTIME_UNITS]


def _focus_match(focus: Optional[str], src: str, dst: str) -> bool:
    if focus is None:
        return True
    if focus.startswith("loop:"):
        prefix = f"loopers:loop{focus[5:]}_"
        return src.startswith(prefix) or dst.startswith(prefix)
    return focus in src or focus in dst


def _loop_match(focus: Optional[str], loop: dict) -> bool:
    if focus is None:
        return True
    if focus.startswith("loop:"):
        return str(loop.get("port_index")) == focus[5:]
    return loop.get("name") == focus


def build_state(graph: Optional[RigGraph], observed: ObservedState, loopers: List[dict],
                versions: dict, session: Optional[str], focus: Optional[str] = None,
                detail: str = "normal") -> dict:
    if detail not in DETAILS:
        raise ValueError(f"detail must be one of {DETAILS}, got {detail!r}")

    issues: List[str] = []
    notes: List[str] = []
    unexpected = set()
    if graph is None:
        issues = [f"down unit: {name}" for name, _ in CORE_RUNTIME_UNITS
                  if not observed.unit_status.get(name, False)]
        verdict = "OK (no session loaded)" if not issues else f"DEGRADED: {len(issues)} issues"
        notes.append("no desired graph: links are reported as observed, not verified")
    else:
        d = diff(graph, observed)
        unexpected = {(l.src, l.dst) for l in d.unexpected_connections}
        # Hand-made rig-space links are notes, not DEGRADED (spec: "Hand
        # edits are notes, absorbed on save"). Only RigDiff.issues()'s
        # unexpected-connection lines are reclassified here; every other
        # category (missing edges, absent nodes, down units, dead port
        # references, unresolved effects) stays an issue.
        issues = [i for i in d.issues() if not i.startswith("unexpected connection: ")]
        stand_ins = {(l.src, l.dst) for l in d.stand_in_connections}
        notes.extend(
            f"stand-in: {l.src} -> {l.dst} replaces a session device that is not "
            "connected (not saved by session_save)"
            if (l.src, l.dst) in stand_ins else
            f"hand edit: unexpected connection {l.src} -> {l.dst} "
            "(absorbed on next session_save)"
            for l in d.unexpected_connections
        )
        verdict = "OK" if not issues else f"DEGRADED: {len(issues)} issues"

    units: Dict[str, dict] = {name: {"up": bool(up)} for name, up in observed.unit_status.items()}

    loops = [dict(l, node=f"loop:{l['port_index']}") for l in loopers if _loop_match(focus, l)]

    links = []
    for link in observed.links:
        if not in_rig_port_space(link.src, link.dst) or not _focus_match(focus, link.src, link.dst):
            continue
        desired: Optional[bool] = None if graph is None else (link.src, link.dst) not in unexpected
        links.append({"src": link.src, "dst": link.dst, "desired": desired})

    state = {
        "verdict": verdict,
        "issues": issues,
        "notes": notes,
        "session": session,
        "versions": dict(versions),
        "units": units,
        "loops": loops,
        "links": links,
    }
    if detail == "diagram":
        state["diagram"] = describe_rig(graph) if graph is not None else ""
    elif detail == "io":
        state["io"] = {"outputs": list(observed.output_ports), "inputs": list(observed.input_ports)}
    return state
