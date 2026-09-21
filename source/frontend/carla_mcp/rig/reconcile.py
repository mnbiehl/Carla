"""
Pure diff/plan engine for the rig reconciler.

NO I/O in this module — no subprocess, no sockets, no clock.  Everything
operates on a desired RigGraph and an ObservedState snapshot so the whole
correctness surface is unit-testable against fabricated states.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from carla_mcp.rig.graph import Edge, Node, RigGraph
from carla_mcp.rig.observe import Link, ObservedState

LOOPER_MIDI_IN = "loopers:loopers_midi_in"

# Same hardware-monitor shape as utils/pw_link.py:137 — duplicated here (two
# lines of regex) so this module stays import-light and pure.
_MONITOR_INPUT_RE = re.compile(r"^alsa_output\..*pro-output.*:playback_AUX\d+$")

_RIG_CLIENT_RE = re.compile(r"^(Carla|CarlaChain_[^:]+|loopers):")

# a2j names ports "a2j:<device> [<alsa client>] (capture|playback): <port>".
_A2J_DEVICE_RE = re.compile(r"^(.*?) \[\d+\] \((?:capture|playback)\)")


def is_rig_port(port: str) -> bool:
    """True for a port on a client the rig itself runs (Carla, a chain, loopers)."""
    return bool(_RIG_CLIENT_RE.match(port))


def port_device(port: str) -> str:
    """The device a port belongs to: its client, or the a2j-bridged MIDI device."""
    client, _, rest = port.partition(":")
    if client == "a2j":
        m = _A2J_DEVICE_RE.match(rest)
        if m:
            return f"a2j:{m.group(1)}"
    return client


@dataclass(frozen=True)
class PortPair:
    """One concrete desired connection between two live ports."""

    src: str
    dst: str
    kind: str = "audio"


def resolve_stereo_ports(base: str, available: List[str]) -> List[str]:
    """Resolve a port base to concrete ports: _l/_r, then 1/2, then mono."""
    available_set = set(available)
    if f"{base}_l" in available_set and f"{base}_r" in available_set:
        return [f"{base}_l", f"{base}_r"]
    if f"{base}1" in available_set and f"{base}2" in available_set:
        return [f"{base}1", f"{base}2"]
    if base in available_set:
        return [base]
    return []


def make_port_pairs(
    src_ports: List[str], dst_ports: List[str]
) -> List[Tuple[str, str]]:
    """Pair ports by the rig's mono/stereo rules (L->L R->R; fan-out; sum)."""
    n_src, n_dst = len(src_ports), len(dst_ports)
    if n_src == 0 or n_dst == 0:
        return []
    if n_src == 2 and n_dst == 2:
        return [(src_ports[0], dst_ports[0]), (src_ports[1], dst_ports[1])]
    if n_src == 1 and n_dst == 2:
        return [(src_ports[0], dst_ports[0]), (src_ports[0], dst_ports[1])]
    if n_src == 2 and n_dst == 1:
        return [(src_ports[0], dst_ports[0]), (src_ports[1], dst_ports[0])]
    return [(src_ports[0], dst_ports[0])]


def node_output_ports(node: Node, live_outputs: List[str]) -> List[str]:
    """Live output ports for *node* (only ports that actually exist)."""
    live = set(live_outputs)
    if node.kind in ("track", "bus"):
        want = [f"{node.jack_client}:audio-out1", f"{node.jack_client}:audio-out2"]
        return [p for p in want if p in live]
    if node.kind == "loop":
        want = [f"loopers:loop{node.port_index}_out_l",
                f"loopers:loop{node.port_index}_out_r"]
        return [p for p in want if p in live]
    if node.kind == "midi":
        if not node.port_pattern:
            return []
        rx = re.compile(node.port_pattern)
        return sorted(p for p in live_outputs if rx.search(p))
    if node.kind == "app":
        return []
    return resolve_stereo_ports(node.jack_client or node.name, live_outputs)


def node_input_ports(node: Node, live_inputs: List[str]) -> List[str]:
    """Live input ports for *node* (only ports that actually exist)."""
    live = set(live_inputs)
    if node.kind in ("track", "bus"):
        want = [f"{node.jack_client}:audio-in1", f"{node.jack_client}:audio-in2"]
        return [p for p in want if p in live]
    if node.kind == "loop":
        want = [f"loopers:loop{node.port_index}_in_l",
                f"loopers:loop{node.port_index}_in_r"]
        return [p for p in want if p in live]
    if node.kind == "app":
        return [LOOPER_MIDI_IN] if LOOPER_MIDI_IN in live else []
    if node.kind == "midi":
        return []
    if node.name == "out:main" and not node.jack_client:
        return sorted(p for p in live_inputs if _MONITOR_INPUT_RE.match(p))[:2]
    return resolve_stereo_ports(node.jack_client or node.name, live_inputs)


def canonical_ports(node: Node) -> List[str]:
    """Port names knowable without live state — what we can wait for."""
    if node.kind in ("track", "bus") and node.jack_client:
        c = node.jack_client
        return [f"{c}:audio-in1", f"{c}:audio-in2", f"{c}:audio-out1", f"{c}:audio-out2"]
    if node.kind == "loop":
        n = node.port_index
        return [f"loopers:loop{n}_in_l", f"loopers:loop{n}_in_r",
                f"loopers:loop{n}_out_l", f"loopers:loop{n}_out_r"]
    if node.kind == "app":
        return [LOOPER_MIDI_IN]
    return []


@dataclass(frozen=True)
class DeadEdge:
    """An explicit-port edge that cannot connect: some of its ports are not live."""

    src: str
    dst: str
    missing: Tuple[str, ...]


def _dead_edge_text(dead: DeadEdge) -> str:
    return f"edge {dead.src} -> {dead.dst}: port(s) not live: " + ", ".join(dead.missing)


@dataclass
class Expansion:
    """Result of expanding node-level edges into concrete port pairs."""

    pairs: List[PortPair] = field(default_factory=list)
    dead_ports: List[str] = field(default_factory=list)
    dead_edges: List[DeadEdge] = field(default_factory=list)
    absent_devices: List[str] = field(default_factory=list)
    absent_nodes: List[str] = field(default_factory=list)
    waitable_ports: List[str] = field(default_factory=list)


def expand_edges(
    graph: RigGraph, live_outputs: List[str], live_inputs: List[str]
) -> Expansion:
    """Expand every desired edge to live port pairs; name what can't resolve."""
    exp = Expansion()
    live_all = set(live_outputs) | set(live_inputs)
    live_devices = {port_device(p) for p in live_all}

    for node in graph.nodes.values():
        outs = node_output_ports(node, live_outputs)
        ins = node_input_ports(node, live_inputs)
        if not outs and not ins:
            exp.absent_nodes.append(node.name)
            exp.waitable_ports.extend(canonical_ports(node))

    for edge in graph.edges:
        if edge.src_port and edge.dst_port:
            missing = [p for p in (edge.src_port, edge.dst_port) if p not in live_all]
            if missing:
                dead = DeadEdge(edge.src, edge.dst, tuple(missing))
                exp.dead_edges.append(dead)
                exp.dead_ports.append(_dead_edge_text(dead))
                exp.waitable_ports.extend(missing)
                for port in missing:
                    device = port_device(port)
                    if device not in live_devices and device not in exp.absent_devices:
                        exp.absent_devices.append(device)
            else:
                exp.pairs.append(PortPair(edge.src_port, edge.dst_port, edge.kind))
            continue
        src_ports = node_output_ports(graph.get_node(edge.src), live_outputs)
        dst_ports = node_input_ports(graph.get_node(edge.dst), live_inputs)
        if not src_ports or not dst_ports:
            side = edge.src if not src_ports else edge.dst
            exp.dead_ports.append(
                f"edge {edge.src} -> {edge.dst}: no live ports for '{side}'"
            )
            continue
        for s, d in make_port_pairs(src_ports, dst_ports):
            exp.pairs.append(PortPair(s, d, edge.kind))
    return exp


def edges_kept_for_absent_hardware(
    graph: RigGraph, live_outputs: List[str], live_inputs: List[str]
) -> List[Edge]:
    """Desired edges that are dead only because external hardware is not there.

    These stay in the session across a save, the way a DAW keeps a project's
    audio device while it is unplugged. An edge qualifies when everything it
    is missing is outside rig port space and its rig side is still live; an
    edge whose loop or chain is gone is a real change and does not qualify.
    """
    live_all = set(live_outputs) | set(live_inputs)
    kept: List[Edge] = []
    for edge in graph.edges:
        if edge.src_port and edge.dst_port:
            missing = [p for p in (edge.src_port, edge.dst_port) if p not in live_all]
            if missing and not any(is_rig_port(p) for p in missing):
                kept.append(edge)
            continue
        src, dst = graph.get_node(edge.src), graph.get_node(edge.dst)
        dead = [n for n, ports in ((src, node_output_ports(src, live_outputs)),
                                   (dst, node_input_ports(dst, live_inputs))) if not ports]
        if dead and all(n.kind in ("endpoint", "midi") and not is_rig_port(n.jack_client or n.name)
                        for n in dead):
            kept.append(edge)
    return kept


def stand_in_links(
    graph: RigGraph, links: List[Link], live_outputs: List[str], live_inputs: List[str]
) -> List[Link]:
    """Live links that replace an absent session device with other hardware.

    With the session's interface unplugged, the PipeWire session manager links
    e.g. the metronome to the onboard speakers. Such a link shares its rig end
    with an edge kept by edges_kept_for_absent_hardware and has other hardware
    on its far end. It is not part of the session.
    """
    live_all = set(live_outputs) | set(live_inputs)
    rig_srcs, rig_dsts = set(), set()
    for edge in edges_kept_for_absent_hardware(graph, live_outputs, live_inputs):
        if edge.src_port and edge.dst_port:
            if edge.src_port in live_all:
                rig_srcs.add(edge.src_port)
            if edge.dst_port in live_all:
                rig_dsts.add(edge.dst_port)
        else:
            rig_srcs.update(node_output_ports(graph.get_node(edge.src), live_outputs))
            rig_dsts.update(node_input_ports(graph.get_node(edge.dst), live_inputs))
    return [l for l in links
            if (l.src in rig_srcs and not is_rig_port(l.dst))
            or (l.dst in rig_dsts and not is_rig_port(l.src))]


def in_rig_port_space(src: str, dst: str) -> bool:
    """True when a connection touches rig-owned port space.

    Rig port space is any connection with at least one endpoint on Carla,
    a CarlaChain_* child, or the loopers engine (audio or MIDI).  Unrelated
    desktop audio never matches and is never touched.
    """
    return is_rig_port(src) or is_rig_port(dst)


@dataclass
class RigDiff:
    """Named deviations between desired graph and observed reality."""

    missing_edges: List[PortPair] = field(default_factory=list)
    unexpected_connections: List[Link] = field(default_factory=list)
    absent_nodes: List[str] = field(default_factory=list)
    down_units: List[str] = field(default_factory=list)
    dead_ports: List[str] = field(default_factory=list)
    dead_edges: List[DeadEdge] = field(default_factory=list)
    absent_devices: List[str] = field(default_factory=list)
    stand_in_connections: List[Link] = field(default_factory=list)
    unresolved_effects: List[str] = field(default_factory=list)
    waitable_ports: List[str] = field(default_factory=list)

    def _missing_port_issues(self) -> List[str]:
        """One line per absent device (or per missing port of a live device),
        however many session edges hang off it."""
        edges_on: Dict[str, int] = {}
        for dead in self.dead_edges:
            for port in dead.missing:
                edges_on[port] = edges_on.get(port, 0) + 1
        out: List[str] = []
        for device in self.absent_devices:
            ports = [p for p in edges_on if port_device(p) == device]
            count = sum(1 for dead in self.dead_edges
                        if any(port_device(p) == device for p in dead.missing))
            names = ", ".join(p.partition(":")[2] for p in ports)
            out.append(f"device not found: {device} ({count} session edges kept, "
                       f"not connected; ports: {names})")
        out += [f"port not live: {port} ({n} session edges kept, not connected)"
                for port, n in edges_on.items() if port_device(port) not in self.absent_devices]
        return out

    def issues(self) -> List[str]:
        """Every deviation as a report-ready line. A missing device or port is
        one line carrying its edge count; its endpoint nodes and edges are not
        repeated as absent-node and dead-port lines."""
        grouped = {_dead_edge_text(dead) for dead in self.dead_edges}
        explained = {name for dead in self.dead_edges for name in (dead.src, dead.dst)}
        out: List[str] = []
        out += [f"missing edge: {p.src} -> {p.dst} ({p.kind})" for p in self.missing_edges]
        out += [f"unexpected connection: {l.src} -> {l.dst}" for l in self.unexpected_connections]
        out += [f"absent node: {n}" for n in self.absent_nodes if n not in explained]
        out += [f"down unit: {u}" for u in self.down_units]
        out += self._missing_port_issues()
        out += [f"dead port reference: {m}" for m in self.dead_ports if m not in grouped]
        out += [f"unresolved effect: {m}" for m in self.unresolved_effects]
        return out

    @property
    def issue_count(self) -> int:
        return len(self.issues())

    @property
    def is_clean(self) -> bool:
        return self.issue_count == 0

    @property
    def verdict(self) -> str:
        return "OK" if self.is_clean else f"DEGRADED: {self.issue_count} issues"


def diff(graph: RigGraph, observed: ObservedState) -> RigDiff:
    """Pure structural diff between the desired graph and observed state."""
    exp = expand_edges(graph, observed.output_ports, observed.input_ports)
    live = {(l.src, l.dst) for l in observed.links}
    want = {(p.src, p.dst) for p in exp.pairs}

    missing = [p for p in exp.pairs if (p.src, p.dst) not in live]
    unexpected = [
        l for l in observed.links
        if (l.src, l.dst) not in want and in_rig_port_space(l.src, l.dst)
    ]
    down = [
        u.name for u in graph.runtime_units.values()
        if not observed.unit_status.get(u.name, False)
    ]
    unresolved: List[str] = []
    for node in graph.nodes.values():
        if node.kind not in ("track", "bus") or not node.effects:
            continue
        handles = observed.instance_handles.get(node.name)
        if handles is None:
            continue  # instance not probed; its liveness is covered by unit status
        have = set(handles.values())
        for eff in node.effects:
            if eff.handle not in have:
                unresolved.append(
                    f"{node.name}: effect '{eff.handle}' not resolved on child instance"
                )

    return RigDiff(
        missing_edges=missing,
        unexpected_connections=unexpected,
        absent_nodes=exp.absent_nodes,
        down_units=down,
        dead_ports=exp.dead_ports,
        dead_edges=exp.dead_edges,
        absent_devices=exp.absent_devices,
        stand_in_connections=stand_in_links(graph, unexpected, observed.output_ports,
                                            observed.input_ports),
        unresolved_effects=unresolved,
        waitable_ports=sorted(set(exp.waitable_ports)),
    )


UNIT_START_ORDER = {
    "looper-engine": 0,
    "looper-mcp": 1,
    "a2j": 2,
    "carla-main": 3,
    "carla-child": 4,
}


@dataclass(frozen=True)
class Action:
    """One ordered fix step produced by plan()."""

    op: str  # "start_unit" | "wait_ports" | "disconnect" | "connect"
    unit: Optional[str] = None
    ports: Tuple[str, ...] = ()
    src: Optional[str] = None
    dst: Optional[str] = None
    kind: str = "audio"


def plan(d: RigDiff, graph: RigGraph) -> List[Action]:
    """Turn a diff into ordered fix actions: processes -> ports -> connections."""
    actions: List[Action] = []

    def _order(unit_name: str) -> Tuple[int, str]:
        unit = graph.runtime_units.get(unit_name)
        rank = UNIT_START_ORDER.get(unit.kind, 9) if unit else 9
        return (rank, unit_name)

    for name in sorted(d.down_units, key=_order):
        actions.append(Action(op="start_unit", unit=name))

    waits = tuple(sorted(set(d.waitable_ports)))
    if waits:
        actions.append(Action(op="wait_ports", ports=waits))

    for link in d.unexpected_connections:
        actions.append(Action(op="disconnect", src=link.src, dst=link.dst))

    for pair in d.missing_edges:
        actions.append(Action(op="connect", src=pair.src, dst=pair.dst, kind=pair.kind))

    return actions


def render_report(verdict: str, sections: List[Tuple[str, List[str]]]) -> str:
    """Render a tool report: verdict line first, then non-empty sections."""
    lines = [verdict]
    for title, items in sections:
        if not items:
            continue
        lines.append(f"[{title}]")
        lines.extend(f"  {item}" for item in items)
    return "\n".join(lines)
