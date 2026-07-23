"""
In-memory rig graph: nodes addressed by stable human names, connected by edges.

A rig graph is a directed audio graph where nodes are endpoints, tracks, or
buses, and edges carry a gain (in dB) from one node to another.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

NODE_KINDS = ("endpoint", "track", "bus", "loop", "app", "midi")
EDGE_KINDS = ("audio", "midi")


@dataclass
class Effect:
    """A single plugin in a node's effects chain.

    handle  — stable identifier stamped into Carla custom-data, e.g. "strat/comp".
    role    — human role label, unique within a node's chain, e.g. "comp".
    plugin  — plugin name/label as requested (e.g. "mcompressor").
    plugin_id — current volatile Carla plugin-id within the owning instance;
                None when not yet loaded.
    bypassed — whether the effect is currently bypassed.
    """

    handle: str
    role: str
    plugin: str
    plugin_id: Optional[int] = None
    bypassed: bool = False


@dataclass
class Node:
    """A node in the rig graph.

    name       — stable human name, e.g. "strat", "in:guitar", "reverb".
    kind       — one of "endpoint", "track", "bus", "loop", "app", or "midi".
    instance   — Carla instance name that owns this node's chain,
                 e.g. "CarlaChain_strat" (None for endpoints or unstarted nodes).
    jack_client — JACK client name for the node's audio I/O (optional).
    source     — for a track: the endpoint name it receives audio from (optional).
    effects    — ordered effects chain; only valid for "track" and "bus" nodes.
    looper_id  — loop nodes: engine looper id (volatile-ish, data only).
    port_index — loop nodes: N in loopers:loopN_{in,out}_{l,r}.
    main_muted — app:looper only.
    all_muted  — app:looper only.
    port_pattern — midi nodes: regex matched against live ports.
    chain_file — track/bus: session-relative .carxp pointer.
    """

    name: str
    kind: str
    instance: Optional[str] = None
    jack_client: Optional[str] = None
    source: Optional[str] = None
    effects: List[Effect] = field(default_factory=list)
    # v3 whole-rig fields
    looper_id: Optional[int] = None      # loop nodes: engine looper id (volatile-ish, data only)
    port_index: Optional[int] = None     # loop nodes: N in loopers:loopN_{in,out}_{l,r}
    main_muted: bool = False             # app:looper only
    all_muted: bool = False              # app:looper only
    port_pattern: Optional[str] = None   # midi nodes: regex matched against live ports
    chain_file: Optional[str] = None     # track/bus: session-relative .carxp pointer


@dataclass
class Edge:
    """A directed edge from one node to another.

    src/dst   — node names.
    gain_db   — gain applied on this connection, in dB (0.0 = unity).
    kind      — "audio" or "midi".
    src_port/dst_port — when both set, this edge binds these exact ports
                (used by the migrator and link-lifting; bypasses stereo
                expansion in the reconciler).
    """

    src: str
    dst: str
    gain_db: float = 0.0
    kind: str = "audio"
    src_port: Optional[str] = None
    dst_port: Optional[str] = None


@dataclass
class RuntimeUnit:
    """A process the rig expects to be alive, independent of port wiring.

    name — stable unit name: "carla:main", "carla:<node>", "looper:engine",
           "looper:mcp", "a2j".
    kind — "carla-main" | "carla-child" | "looper-engine" | "looper-mcp" | "a2j".
    node — owning graph node name for carla-child units (else None).
    """

    name: str
    kind: str
    node: Optional[str] = None


class RigGraph:
    """Directed audio graph of named nodes connected by edges.

    Nodes are keyed by their stable human name.  Edges are stored as a list;
    there is at most one edge between any (src, dst) pair.
    """

    def __init__(self) -> None:
        """Create an empty rig graph."""
        self.nodes: dict[str, Node] = {}
        self.edges: List[Edge] = []
        self.runtime_units: dict[str, RuntimeUnit] = {}

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    def add_node(self, node: Node) -> None:
        """Add *node* to the graph.

        Raises:
            ValueError: if a node with the same name already exists, or if
                        node.kind is not a recognized node kind.
        """
        if node.kind not in NODE_KINDS:
            raise ValueError(f"Unknown node kind '{node.kind}' for node '{node.name}'")
        if node.name in self.nodes:
            raise ValueError(f"Node '{node.name}' already exists")
        self.nodes[node.name] = node

    def remove_node(self, name: str) -> None:
        """Remove the node named *name* and any edges that touch it.

        Raises:
            KeyError: if no node with that name exists.
        """
        if name not in self.nodes:
            raise KeyError(f"Node '{name}' not found")
        del self.nodes[name]
        self.edges = [e for e in self.edges if e.src != name and e.dst != name]

    def get_node(self, name: str) -> Node:
        """Return the node named *name*.

        Raises:
            KeyError: if no such node exists.
        """
        if name not in self.nodes:
            raise KeyError(f"Node '{name}' not found")
        return self.nodes[name]

    def has_node(self, name: str) -> bool:
        """Return True if a node named *name* exists."""
        return name in self.nodes

    # ------------------------------------------------------------------
    # Edge operations
    # ------------------------------------------------------------------

    def add_edge(
        self,
        src: str,
        dst: str,
        gain_db: float = 0.0,
        kind: str = "audio",
        src_port: Optional[str] = None,
        dst_port: Optional[str] = None,
    ) -> None:
        """Add (or update) an edge from *src* to *dst*.

        Uniqueness key is (src, dst, src_port, dst_port): node-level edges
        stay unique per node pair; explicit-port edges are unique per port
        pair, so a stereo lift can record two edges between the same nodes.

        Raises:
            KeyError:   if either node does not exist.
            ValueError: if *kind* is not a valid edge kind.
        """
        if kind not in EDGE_KINDS:
            raise ValueError(f"Unknown edge kind '{kind}'")
        if src not in self.nodes:
            raise KeyError(f"Source node '{src}' not found")
        if dst not in self.nodes:
            raise KeyError(f"Destination node '{dst}' not found")
        for edge in self.edges:
            if (edge.src, edge.dst, edge.src_port, edge.dst_port) == (src, dst, src_port, dst_port):
                edge.gain_db = gain_db
                edge.kind = kind
                return
        self.edges.append(
            Edge(src=src, dst=dst, gain_db=gain_db, kind=kind,
                 src_port=src_port, dst_port=dst_port)
        )

    def add_runtime_unit(self, unit: RuntimeUnit) -> None:
        """Register (or replace) a runtime-unit expectation by name."""
        self.runtime_units[unit.name] = unit

    def remove_edge(self, src: str, dst: str) -> None:
        """Remove the edge from *src* to *dst*.

        Raises:
            KeyError: if no such edge exists.
        """
        for i, edge in enumerate(self.edges):
            if edge.src == src and edge.dst == dst:
                del self.edges[i]
                return
        raise KeyError(f"Edge '{src}' -> '{dst}' not found")

    def edges_from(self, name: str) -> List[Edge]:
        """Return all edges whose source is *name*."""
        return [e for e in self.edges if e.src == name]

    def edges_to(self, name: str) -> List[Edge]:
        """Return all edges whose destination is *name*."""
        return [e for e in self.edges if e.dst == name]

    # ------------------------------------------------------------------
    # Effect chain operations (track and bus nodes only)
    # ------------------------------------------------------------------

    def _chain_node(self, node_name: str) -> Node:
        """Return the node if it is a track or bus; raise otherwise."""
        node = self.get_node(node_name)
        if node.kind not in ("track", "bus"):
            raise ValueError(
                f"Node '{node_name}' is kind '{node.kind}'; "
                "effects chains are only supported on 'track' and 'bus' nodes"
            )
        return node

    def _resolve_position(self, chain: List[Effect], position: object) -> int:
        """Resolve a *position* specifier to a list insertion index.

        Accepted forms:
            "end"           → append after last element
            "start"         → insert before first element
            "before:<role>" → insert before the effect whose role matches
            "after:<role>"  → insert after the effect whose role matches
            int             → direct index (negative indices supported)

        Raises:
            ValueError: for unknown string specifiers or unresolvable roles.
            IndexError: for out-of-range integer indices.
        """
        n = len(chain)
        if isinstance(position, int):
            if position < 0:
                position = max(0, n + position + 1)
            if position > n:
                raise IndexError(
                    f"Position index {position} out of range for chain of length {n}"
                )
            return position
        if position == "end":
            return n
        if position == "start":
            return 0
        if isinstance(position, str):
            if position.startswith("before:"):
                role = position[len("before:"):]
                for i, eff in enumerate(chain):
                    if eff.role == role:
                        return i
                raise ValueError(
                    f"No effect with role '{role}' found for 'before:' positioning"
                )
            if position.startswith("after:"):
                role = position[len("after:"):]
                for i, eff in enumerate(chain):
                    if eff.role == role:
                        return i + 1
                raise ValueError(
                    f"No effect with role '{role}' found for 'after:' positioning"
                )
        raise ValueError(f"Unknown position specifier: {position!r}")

    def add_effect(
        self,
        node_name: str,
        effect: Effect,
        position: object = "end",
    ) -> None:
        """Append or insert *effect* into *node_name*'s effects chain.

        Args:
            node_name: Name of the target track or bus node.
            effect:    The Effect to insert.
            position:  Where to insert — "end", "start", "before:<role>",
                       "after:<role>", or an integer index.

        Raises:
            KeyError:   if the node does not exist.
            ValueError: if the node is not a track or bus, or if the position
                        specifier is invalid.
        """
        node = self._chain_node(node_name)
        idx = self._resolve_position(node.effects, position)
        node.effects.insert(idx, effect)

    def remove_effect(self, node_name: str, role_or_handle: str) -> None:
        """Remove an effect from *node_name*'s chain by role or handle.

        Args:
            node_name:      Name of the target track or bus node.
            role_or_handle: The effect's role OR its handle.

        Raises:
            KeyError:   if the node does not exist.
            ValueError: if the node is not a track/bus, or no matching effect.
        """
        node = self._chain_node(node_name)
        for i, eff in enumerate(node.effects):
            if eff.role == role_or_handle or eff.handle == role_or_handle:
                del node.effects[i]
                return
        raise ValueError(
            f"No effect with role or handle '{role_or_handle}' in node '{node_name}'"
        )

    def move_effect(
        self,
        node_name: str,
        role_or_handle: str,
        position: object,
    ) -> None:
        """Move an existing effect to a new position in *node_name*'s chain.

        Args:
            node_name:      Name of the target track or bus node.
            role_or_handle: The effect's role OR its handle.
            position:       Target position — same specifiers as add_effect.

        Raises:
            KeyError:   if the node does not exist.
            ValueError: if the node is not a track/bus, the effect is missing,
                        or the position specifier is invalid.
        """
        node = self._chain_node(node_name)
        # Find and remove the effect
        found: Optional[Effect] = None
        for i, eff in enumerate(node.effects):
            if eff.role == role_or_handle or eff.handle == role_or_handle:
                found = node.effects.pop(i)
                break
        if found is None:
            raise ValueError(
                f"No effect with role or handle '{role_or_handle}' in node '{node_name}'"
            )
        # Resolve position against the chain *after* removal, then insert
        idx = self._resolve_position(node.effects, position)
        node.effects.insert(idx, found)

    def find_effect(self, node_name: str, role_or_handle: str) -> Optional[Effect]:
        """Return the effect matching *role_or_handle* in *node_name*'s chain.

        Matches by role first, then by handle.  Returns None if not found.

        Raises:
            KeyError:   if the node does not exist.
            ValueError: if the node is not a track/bus.
        """
        node = self._chain_node(node_name)
        for eff in node.effects:
            if eff.role == role_or_handle or eff.handle == role_or_handle:
                return eff
        return None
