"""
Observed rig state: what is actually live on PipeWire, in the looper engine,
and in each managed process.

This module's data types are pure; `observe()` (added separately) gathers a
snapshot through injected callables so the bridge supplies real I/O and tests
supply fabricated state.  stdlib-only: this package is imported by the main
Carla process running system Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, List, Optional, Tuple

from carla_mcp.rig.graph import Node, RuntimeUnit


@dataclass(frozen=True)
class Link:
    """One live pw-link connection (source port -> destination port)."""

    src: str
    dst: str


@dataclass
class ObservedState:
    """Snapshot of live rig reality, consumed by the pure diff engine.

    links            — every live pw connection (audio and midi).
    output_ports     — all live output port names (pw-link -o).
    input_ports      — all live input port names (pw-link -i).
    unit_status      — runtime-unit name -> is it up?
    looper_state     — raw GetState payload (contains "loopers": [...]), or None.
    instance_handles — track/bus node name -> {plugin_id_str: handle} re-resolved
                       from each child Carla instance.
    """

    links: List[Link] = field(default_factory=list)
    output_ports: List[str] = field(default_factory=list)
    input_ports: List[str] = field(default_factory=list)
    unit_status: Dict[str, bool] = field(default_factory=dict)
    looper_state: Optional[dict] = None
    instance_handles: Dict[str, Dict[str, str]] = field(default_factory=dict)


def is_midi_port(name: str) -> bool:
    """Best-effort port classification: a2j-bridged or 'midi'-named ports."""
    return name.startswith("a2j:") or "midi" in name.lower()


def loop_nodes_from_looper_state(state: Optional[dict]) -> List[Node]:
    """Build loop:N nodes from a GetState payload's per-looper summary.

    Loop nodes are auto-discovered, never hand-created: name is
    "loop:<port_index>" (the positional index N in loopers:loopN_* ports);
    the engine looper id rides along as data.  Entries without a port_index
    (pre-contract engines) are skipped — callers report that as degraded.
    """
    nodes: List[Node] = []
    for entry in (state or {}).get("loopers", []) or []:
        idx = entry.get("port_index")
        if idx is None:
            continue
        nodes.append(
            Node(name=f"loop:{idx}", kind="loop",
                 looper_id=entry.get("id"), port_index=idx)
        )
    nodes.sort(key=lambda n: n.port_index)
    return nodes


async def observe(
    units: List["RuntimeUnit"],
    *,
    list_links: Callable[[], List[Tuple[str, str]]],
    list_outputs: Callable[[], List[str]],
    list_inputs: Callable[[], List[str]],
    unit_probe: Callable[["RuntimeUnit"], bool],
    looper_get_state: Optional[Callable[[], "Awaitable[Optional[dict]]"]] = None,
    carla_handles: Optional[Callable[[], "Awaitable[Dict[str, Dict[str, str]]]"]] = None,
) -> ObservedState:
    """Gather a full ObservedState through injected collaborators.

    Every probe is individually shielded: a failing collaborator yields an
    empty/False observation (which the diff then reports), never an exception.
    """
    def _safe_list(fn: Callable[[], list]) -> list:
        try:
            return list(fn())
        except Exception:  # noqa: BLE001 — observation must not raise
            return []

    status: Dict[str, bool] = {}
    for unit in units:
        try:
            status[unit.name] = bool(unit_probe(unit))
        except Exception:  # noqa: BLE001
            status[unit.name] = False

    looper_state = None
    if looper_get_state is not None:
        try:
            looper_state = await looper_get_state()
        except Exception:  # noqa: BLE001
            looper_state = None

    handles: Dict[str, Dict[str, str]] = {}
    if carla_handles is not None:
        try:
            handles = dict(await carla_handles() or {})
        except Exception:  # noqa: BLE001
            handles = {}

    return ObservedState(
        links=[Link(s, d) for s, d in _safe_list(list_links)],
        output_ports=_safe_list(list_outputs),
        input_ports=_safe_list(list_inputs),
        unit_status=status,
        looper_state=looper_state,
        instance_handles=handles,
    )
