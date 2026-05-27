"""
RigController: node lifecycle management for the in-memory rig graph.

Handles create_bus, create_track, remove_node, add_effect, and remove_effect
by coordinating between the rig graph, the chain launcher (which spawns Carla
sub-processes), the JACK router (which undoes PipeWire's hardware
auto-connections), and RemoteInstance (which drives each child's MCP tools).

Physical audio wiring between nodes (pw-link) is performed by route/unroute
and is called automatically from create_track.
"""

from __future__ import annotations

import logging
import time as time_module
from typing import Callable, List, Optional

from carla_mcp.rig.graph import Effect, Node, RigGraph
from carla_mcp.rig.remote import RemoteInstance
from carla_mcp.utils.pw_link import (
    find_monitor_output_ports,
    pw_link_list_inputs,
    pw_link_list_outputs,
)

logger = logging.getLogger(__name__)


class RigController:
    """Manages node lifecycle for a :class:`RigGraph`.

    Parameters
    ----------
    graph:
        The in-memory rig graph to mutate.
    instance_manager:
        Tracks live :class:`CarlaInstance` objects by name.
    chain_launcher:
        Spawns / terminates Carla sub-processes.
    jack_router:
        Issues ``pw-link`` commands to manage audio connections.
    sleep:
        Callable used to pause between settle iterations.  Defaults to
        :func:`time.sleep`; inject ``lambda *_: None`` in tests.
    """

    def __init__(
        self,
        graph: RigGraph,
        instance_manager,
        chain_launcher,
        jack_router,
        sleep: Callable[[float], None] = time_module.sleep,
        remote_factory: Optional[Callable] = None,
        list_outputs: Callable[[], List[str]] = pw_link_list_outputs,
        list_inputs: Callable[[], List[str]] = pw_link_list_inputs,
        monitor_ports: Callable[[], List[str]] = find_monitor_output_ports,
    ) -> None:
        self._graph = graph
        self._instance_manager = instance_manager
        self._chain_launcher = chain_launcher
        self._jack_router = jack_router
        self._sleep = sleep
        self._remote_factory = remote_factory
        self._list_outputs = list_outputs
        self._list_inputs = list_inputs
        self._monitor_ports = monitor_ports

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _remote(self, node: Node) -> RemoteInstance:
        """Return a RemoteInstance for *node*'s Carla child process.

        If a ``remote_factory`` was injected (e.g. in tests), call it with
        *node* and return the result.  Otherwise, build a production
        RemoteInstance over SSE using the instance's ``mcp_port``.

        Args:
            node: The graph node whose child instance to connect to.

        Returns:
            A :class:`RemoteInstance` targeting *node*'s child.
        """
        if self._remote_factory is not None:
            return self._remote_factory(node)
        instance = self._instance_manager.get(node.instance)
        sse_url = f"http://127.0.0.1:{instance.mcp_port}/sse"
        return RemoteInstance.over_sse(sse_url)

    async def _refresh_ids(self, node: Node) -> None:
        """Re-resolve every effect's plugin_id from the child's live handle map.

        Carla's plugin IDs shift on add/remove.  After any mutation, call this
        to sync ``effect.plugin_id`` values with what the child actually has.

        Args:
            node: The graph node whose effects chain to refresh.
        """
        remote = self._remote(node)
        handles = await remote.list_handles()  # {plugin_id: handle}
        inverted = {h: pid for pid, h in handles.items()}
        for eff in node.effects:
            eff.plugin_id = inverted.get(eff.handle)

    def _settle_instance(self, jack_client_name: str) -> int:
        """Undo PipeWire hardware auto-connections for a freshly spawned client.

        Mirrors the settle loop in ``tools/orchestration.py::create_effects_chain``:
        run up to 5 iterations, sleeping 1 s between each, calling
        :meth:`JackRouter.disconnect_client_from_system` each time.  Break
        early once a pass removes 0 connections *after* at least one
        connection was previously removed.

        Returns
        -------
        int
            Total number of connections removed across all iterations.
        """
        removed = 0
        for _ in range(5):
            self._sleep(1)
            n = self._jack_router.disconnect_client_from_system(jack_client_name)
            removed += n
            if n == 0 and removed > 0:
                break
        return removed

    # ------------------------------------------------------------------
    # Port-resolution helpers
    # ------------------------------------------------------------------

    def _resolve_stereo_ports(self, base: str, available: List[str]) -> List[str]:
        """Resolve a port base string to concrete port names from *available*.

        Resolution order:
        1. ``{base}_l`` and ``{base}_r`` both present → return those two.
        2. ``{base}1`` and ``{base}2`` both present → return those two.
        3. ``{base}`` itself present → return ``[base]`` (mono).
        4. Nothing matched → return ``[]``.

        Args:
            base:      The port base string to resolve (e.g. "looperdooper:loop0_out").
            available: The full list of available port names to search in.

        Returns:
            A list of one or two concrete port strings, or an empty list.
        """
        available_set = set(available)
        if f"{base}_l" in available_set and f"{base}_r" in available_set:
            return [f"{base}_l", f"{base}_r"]
        if f"{base}1" in available_set and f"{base}2" in available_set:
            return [f"{base}1", f"{base}2"]
        if base in available_set:
            return [base]
        return []

    def _source_ports(self, node: Node) -> List[str]:
        """Return the concrete output port names for *node*.

        For track/bus nodes: ``["{jack_client}:audio-out1", "{jack_client}:audio-out2"]``.
        For endpoint nodes: resolved via :meth:`_resolve_stereo_ports` against
        the live list of PipeWire output ports.

        Args:
            node: The graph node to resolve output ports for.

        Returns:
            A list of port name strings (may be empty for unresolvable endpoints).
        """
        if node.kind in ("track", "bus"):
            return [
                f"{node.jack_client}:audio-out1",
                f"{node.jack_client}:audio-out2",
            ]
        return self._resolve_stereo_ports(node.jack_client, self._list_outputs())

    def _sink_ports(self, node: Node) -> List[str]:
        """Return the concrete input port names for *node*.

        For track/bus nodes: ``["{jack_client}:audio-in1", "{jack_client}:audio-in2"]``.
        For the ``"out:main"`` endpoint: the monitor output ports from
        :attr:`_monitor_ports`.
        For other endpoint nodes: resolved via :meth:`_resolve_stereo_ports`
        against the live list of PipeWire input ports.

        Args:
            node: The graph node to resolve input ports for.

        Returns:
            A list of port name strings (may be empty for unresolvable endpoints).
        """
        if node.kind in ("track", "bus"):
            return [
                f"{node.jack_client}:audio-in1",
                f"{node.jack_client}:audio-in2",
            ]
        if node.name == "out:main":
            return self._monitor_ports()
        return self._resolve_stereo_ports(node.jack_client, self._list_inputs())

    def _connect_port_pairs(
        self, src_ports: List[str], dst_ports: List[str]
    ) -> tuple[list[tuple[str, str]], str | None]:
        """Connect port pairs according to mono/stereo pairing rules.

        Pairing rules:
        - 2 src, 2 dst → connect [0]→[0] and [1]→[1].
        - 1 src, 2 dst → connect src[0]→dst[0] and src[0]→dst[1] (mono fan-out).
        - 2 src, 1 dst → connect src[0]→dst[0] and src[1]→dst[0] (stereo sum).
        - 1 src, 1 dst → connect src[0]→dst[0].

        Args:
            src_ports: Resolved source port names.
            dst_ports: Resolved destination port names.

        Returns:
            A tuple of ``(pairs, error_message)`` where *pairs* is the list of
            ``(src, dst)`` strings that were successfully connected, and
            *error_message* is ``None`` on full success or a string describing
            the first failure.
        """
        n_src, n_dst = len(src_ports), len(dst_ports)
        if n_src == 2 and n_dst == 2:
            pairs = [(src_ports[0], dst_ports[0]), (src_ports[1], dst_ports[1])]
        elif n_src == 1 and n_dst == 2:
            pairs = [(src_ports[0], dst_ports[0]), (src_ports[0], dst_ports[1])]
        elif n_src == 2 and n_dst == 1:
            pairs = [(src_ports[0], dst_ports[0]), (src_ports[1], dst_ports[0])]
        else:
            pairs = [(src_ports[0], dst_ports[0])]

        connected: list[tuple[str, str]] = []
        for s, d in pairs:
            result = self._jack_router.connect(s, d)
            if not result.success:
                return connected, f"Failed to connect {s} -> {d}: {result.message}"
            connected.append((s, d))
        return connected, None

    # ------------------------------------------------------------------
    # route / unroute
    # ------------------------------------------------------------------

    def route(self, src: str, dst: str) -> dict:
        """Wire audio from *src* to *dst* via pw-link and record the graph edge.

        If either name is not yet in the graph it is auto-created as an
        endpoint node (so callers can route to ``"out:main"`` etc. without
        pre-declaring).

        Args:
            src: Name of the source node (or endpoint base string).
            dst: Name of the destination node (or endpoint base string).

        Returns:
            ``{"success": True, "pairs": [...]}`` on success, or
            ``{"success": False, "message": ..., "pairs": [...]}`` on failure.
            *pairs* lists the ``(src_port, dst_port)`` strings that were
            connected before any failure.
        """
        for name in (src, dst):
            if not self._graph.has_node(name):
                self._graph.add_node(Node(name=name, kind="endpoint", jack_client=name))

        src_node = self._graph.get_node(src)
        dst_node = self._graph.get_node(dst)

        src_ports = self._source_ports(src_node)
        dst_ports = self._sink_ports(dst_node)

        if not src_ports:
            return {
                "success": False,
                "message": f"Could not resolve source ports for '{src}'",
                "pairs": [],
            }
        if not dst_ports:
            return {
                "success": False,
                "message": f"Could not resolve sink ports for '{dst}'",
                "pairs": [],
            }

        connected, error = self._connect_port_pairs(src_ports, dst_ports)

        if error is not None:
            return {"success": False, "message": error, "pairs": connected}

        self._graph.add_edge(src, dst)

        return {
            "success": True,
            "message": f"Routed '{src}' -> '{dst}'",
            "pairs": connected,
        }

    def unroute(self, src: str, dst: str) -> dict:
        """Remove the audio connection from *src* to *dst* and update the graph.

        Args:
            src: Name of the source node.
            dst: Name of the destination node.

        Returns:
            ``{"success": True, "message": ..., "disconnect_failures": int}``
            on success (individual disconnect failures are reported but do not
            fail the call), or ``{"success": False, "message": ...}`` if a
            node is missing.
        """
        for name in (src, dst):
            if not self._graph.has_node(name):
                return {
                    "success": False,
                    "message": f"Node '{name}' not found in the rig graph",
                }

        src_node = self._graph.get_node(src)
        dst_node = self._graph.get_node(dst)

        src_ports = self._source_ports(src_node)
        dst_ports = self._sink_ports(dst_node)

        # Build pairs using the same pairing logic as route.
        n_src, n_dst = len(src_ports), len(dst_ports)
        if n_src == 2 and n_dst == 2:
            pairs = [(src_ports[0], dst_ports[0]), (src_ports[1], dst_ports[1])]
        elif n_src == 1 and n_dst == 2:
            pairs = [(src_ports[0], dst_ports[0]), (src_ports[0], dst_ports[1])]
        elif n_src == 2 and n_dst == 1:
            pairs = [(src_ports[0], dst_ports[0]), (src_ports[1], dst_ports[0])]
        elif n_src == 1 and n_dst == 1:
            pairs = [(src_ports[0], dst_ports[0])]
        else:
            pairs = []

        failures = 0
        for s, d in pairs:
            result = self._jack_router.disconnect(s, d)
            if not result.success:
                failures += 1
                logger.warning("Disconnect failed for %s -> %s: %s", s, d, result.message)

        # Remove the graph edge (guard against missing edge).
        note = None
        try:
            self._graph.remove_edge(src, dst)
        except KeyError:
            note = f"No graph edge '{src}' -> '{dst}' was recorded"

        msg = f"Unrouted '{src}' -> '{dst}'"
        if note:
            msg = f"{msg} (note: {note})"

        return {
            "success": True,
            "message": msg,
            "disconnect_failures": failures,
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_bus(self, name: str) -> dict:
        """Create a new bus node, launching a dedicated Carla instance.

        Parameters
        ----------
        name:
            Stable name for the bus.  Must satisfy ``^[a-zA-Z0-9_-]+$`` and
            must not already exist in the graph.

        Returns
        -------
        dict
            ``{"success": True, "message": ..., "name": ..., "jack_client": ...}``
            on success, or ``{"success": False, "message": ...}`` on failure.
        """
        if self._graph.has_node(name):
            return {
                "success": False,
                "message": f"Node '{name}' already exists in the rig graph",
            }

        try:
            instance = self._chain_launcher.launch(name)
        except ValueError as exc:
            return {"success": False, "message": str(exc)}

        self._settle_instance(instance.jack_client_name)

        self._graph.add_node(
            Node(
                name=name,
                kind="bus",
                instance=instance.name,
                jack_client=instance.jack_client_name,
            )
        )

        return {
            "success": True,
            "message": (
                f"Created bus '{name}' (JACK client {instance.jack_client_name})"
            ),
            "name": name,
            "jack_client": instance.jack_client_name,
        }

    def create_track(self, name: str, source: str) -> dict:
        """Create a new track node wired from *source*, launching a Carla instance.

        If *source* does not already exist as a graph node an endpoint node is
        auto-created for it.  After registering the track node, the source is
        physically wired to the track via :meth:`route` (which also records the
        graph edge).  If routing fails the node is still created but the return
        dict includes a ``"wiring"`` key with the route failure details.

        Parameters
        ----------
        name:
            Stable name for the track.
        source:
            Name of the endpoint (physical port base) that feeds this track.

        Returns
        -------
        dict
            ``{"success": True, ..., "wiring": {...}}`` on success, or
            ``{"success": False, "message": ...}`` on failure.
        """
        if self._graph.has_node(name):
            return {
                "success": False,
                "message": f"Node '{name}' already exists in the rig graph",
            }

        try:
            instance = self._chain_launcher.launch(name)
        except ValueError as exc:
            return {"success": False, "message": str(exc)}

        self._settle_instance(instance.jack_client_name)

        # Auto-create the source endpoint if it is not already in the graph.
        # We do this AFTER a successful launch so a launch failure cannot leave
        # a dangling endpoint node in the graph.
        source_was_new = False
        if not self._graph.has_node(source):
            self._graph.add_node(
                Node(name=source, kind="endpoint", jack_client=source)
            )
            source_was_new = True

        self._graph.add_node(
            Node(
                name=name,
                kind="track",
                instance=instance.name,
                jack_client=instance.jack_client_name,
                source=source,
            )
        )

        # Physically wire source → track (route also records the graph edge).
        route_result = self.route(source, name)
        if not route_result["success"]:
            logger.warning(
                "create_track '%s': routing from '%s' failed: %s",
                name,
                source,
                route_result.get("message"),
            )

        result: dict = {
            "success": True,
            "message": (
                f"Created track '{name}' sourced from '{source}' "
                f"(JACK client {instance.jack_client_name})"
            ),
            "name": name,
            "jack_client": instance.jack_client_name,
            "source": source,
            "source_was_new": source_was_new,
            "wiring": route_result,
        }
        if not route_result["success"]:
            result["warning"] = f"Routing failed: {route_result.get('message')}"
        return result

    def remove_node(self, name: str) -> dict:
        """Remove a node from the graph, terminating its Carla instance if any.

        Touching edges are automatically removed by
        :meth:`RigGraph.remove_node`.

        Parameters
        ----------
        name:
            Name of the node to remove.

        Returns
        -------
        dict
            ``{"success": True, "message": ...}`` or
            ``{"success": False, "message": ...}``.
        """
        if not self._graph.has_node(name):
            return {
                "success": False,
                "message": f"Node '{name}' not found in the rig graph",
            }

        node = self._graph.get_node(name)

        if node.kind in ("track", "bus") and node.instance is not None:
            try:
                self._chain_launcher.terminate(name)
            except Exception as exc:
                logger.warning(
                    "Failed to terminate Carla instance for node '%s': %s",
                    name,
                    exc,
                )

        self._graph.remove_node(name)

        return {"success": True, "message": f"Removed node '{name}'"}

    async def add_effect(
        self,
        node_name: str,
        plugin: str,
        role: str,
        position: object = "end",
    ) -> dict:
        """Add a plugin effect to a track or bus node's chain.

        Loads the plugin on the child Carla instance, stamps a stable handle,
        updates the graph, re-resolves all plugin IDs, and rewires the chain.

        Parameters
        ----------
        node_name:
            Name of the target track or bus node.
        plugin:
            Plugin name/label to load (e.g. "mcompressor").
        role:
            Human role label unique within this node (e.g. "comp").
        position:
            Insertion point — "end", "start", "before:<role>",
            "after:<role>", or an integer index.  Defaults to "end".

        Returns
        -------
        dict
            ``{"success": True, "node": ..., "role": ..., "handle": ...,
               "order": [...]}`` on success, or
            ``{"success": False, "message": ..., "error": ...}`` on failure.
        """
        try:
            node = self._graph.get_node(node_name)
        except KeyError:
            return {"success": False, "message": f"Node '{node_name}' not found"}

        if node.kind not in ("track", "bus"):
            return {
                "success": False,
                "message": (
                    f"Node '{node_name}' is kind '{node.kind}'; "
                    "effects chains are only supported on 'track' and 'bus' nodes"
                ),
            }

        try:
            remote = self._remote(node)

            # new_id = current plugin count (Carla appends, so id == count)
            new_id = len(node.effects)

            await remote.add_plugin(plugin)

            handle = f"{node_name}/{role}"
            await remote.set_handle(new_id, handle)

            effect = Effect(handle=handle, role=role, plugin=plugin, plugin_id=new_id)
            self._graph.add_effect(node_name, effect, position)

            await self._refresh_ids(node)

            ordered = [e.plugin_id for e in node.effects]
            await remote.rewire_chain(ordered)

            return {
                "success": True,
                "node": node_name,
                "role": role,
                "handle": handle,
                "order": ordered,
            }
        except Exception as exc:
            return {"success": False, "message": f"Failed to add effect: {exc}", "error": str(exc)}

    async def remove_effect(self, node_name: str, role_or_handle: str) -> dict:
        """Remove an effect from a track or bus node's chain.

        Re-resolves plugin IDs before removal to account for prior shifts,
        removes the plugin from the child Carla instance, removes the effect
        from the graph, refreshes IDs again, and rewires the chain.

        Parameters
        ----------
        node_name:
            Name of the target track or bus node.
        role_or_handle:
            The effect's role or stable handle to remove.

        Returns
        -------
        dict
            ``{"success": True, "node": ..., "removed": ..., "order": [...]}``
            on success, ``{"success": False, "message": ...}`` if the effect
            is not found, or ``{"success": False, "error": ...}`` on exception.
        """
        try:
            node = self._graph.get_node(node_name)
        except KeyError:
            return {"success": False, "message": f"Node '{node_name}' not found"}

        if node.kind not in ("track", "bus"):
            return {
                "success": False,
                "message": (
                    f"Node '{node_name}' is kind '{node.kind}'; "
                    "effects chains are only supported on 'track' and 'bus' nodes"
                ),
            }

        # Refresh IDs first so we have accurate plugin_id values
        try:
            await self._refresh_ids(node)
        except Exception as exc:
            return {"success": False, "message": f"Failed to refresh IDs: {exc}", "error": str(exc)}

        effect = self._graph.find_effect(node_name, role_or_handle)
        if effect is None:
            return {
                "success": False,
                "message": (
                    f"No effect with role or handle '{role_or_handle}' "
                    f"in node '{node_name}'"
                ),
            }

        plugin_id = effect.plugin_id

        try:
            remote = self._remote(node)
            await remote.remove_plugin(plugin_id)

            self._graph.remove_effect(node_name, role_or_handle)

            await self._refresh_ids(node)

            ordered = [e.plugin_id for e in node.effects]
            await remote.rewire_chain(ordered)

            return {
                "success": True,
                "node": node_name,
                "removed": role_or_handle,
                "order": ordered,
            }
        except Exception as exc:
            return {"success": False, "message": f"Failed to remove effect: {exc}", "error": str(exc)}

    async def move_effect(
        self,
        node_name: str,
        role_or_handle: str,
        position: object,
    ) -> dict:
        """Move an existing effect to a new position in a track or bus chain.

        Re-resolves plugin IDs before and after the move, then rewires the
        child Carla chain to match the new order.

        Parameters
        ----------
        node_name:
            Name of the target track or bus node.
        role_or_handle:
            The effect's role or stable handle to move.
        position:
            Target position — "end", "start", "before:<role>",
            "after:<role>", or an integer index.

        Returns
        -------
        dict
            ``{"success": True, "node": ..., "role_or_handle": ..., "order": [...]}``
            on success, or ``{"success": False, "message": ...}`` on failure.
        """
        try:
            node = self._graph.get_node(node_name)
        except KeyError:
            return {"success": False, "message": f"Node '{node_name}' not found"}

        if node.kind not in ("track", "bus"):
            return {
                "success": False,
                "message": (
                    f"Node '{node_name}' is kind '{node.kind}'; "
                    "effects chains are only supported on 'track' and 'bus' nodes"
                ),
            }

        try:
            await self._refresh_ids(node)

            self._graph.move_effect(node_name, role_or_handle, position)

            await self._refresh_ids(node)

            ordered = [e.plugin_id for e in node.effects]
            await self._remote(node).rewire_chain(ordered)

            return {
                "success": True,
                "node": node_name,
                "role_or_handle": role_or_handle,
                "order": ordered,
            }
        except (ValueError, IndexError) as exc:
            return {"success": False, "message": str(exc)}
        except Exception as exc:
            return {"success": False, "message": f"Failed to move effect: {exc}", "error": str(exc)}

    async def bypass(
        self,
        node_name: str,
        role_or_handle: str,
        on: bool = True,
    ) -> dict:
        """Bypass or un-bypass an effect in a track or bus chain.

        Bypass ON means the plugin is inactive in Carla (``set_active(False)``);
        bypass OFF means the plugin is active (``set_active(True)``).

        Parameters
        ----------
        node_name:
            Name of the target track or bus node.
        role_or_handle:
            The effect's role or stable handle.
        on:
            True to bypass the effect; False to un-bypass it.

        Returns
        -------
        dict
            ``{"success": True, "node": ..., "role": ..., "bypassed": ...}``
            on success, or ``{"success": False, "message": ...}`` on failure.
        """
        try:
            node = self._graph.get_node(node_name)
        except KeyError:
            return {"success": False, "message": f"Node '{node_name}' not found"}

        if node.kind not in ("track", "bus"):
            return {
                "success": False,
                "message": (
                    f"Node '{node_name}' is kind '{node.kind}'; "
                    "effects chains are only supported on 'track' and 'bus' nodes"
                ),
            }

        try:
            await self._refresh_ids(node)

            effect = self._graph.find_effect(node_name, role_or_handle)
            if effect is None:
                return {
                    "success": False,
                    "message": (
                        f"No effect with role or handle '{role_or_handle}' "
                        f"in node '{node_name}'"
                    ),
                }

            await self._remote(node).set_active(effect.plugin_id, not on)
            effect.bypassed = on

            return {
                "success": True,
                "node": node_name,
                "role": effect.role,
                "bypassed": effect.bypassed,
            }
        except Exception as exc:
            return {"success": False, "message": f"Failed to bypass effect: {exc}", "error": str(exc)}

    async def set_param(
        self,
        node_name: str,
        role_or_handle: str,
        param: str,
        value: float,
    ) -> dict:
        """Set a named parameter on an effect in a track or bus chain.

        Resolves the parameter by case-insensitive name match from the child's
        live parameter list.  Values are passed in the plugin's native units
        (no dB conversion is applied).

        Parameters
        ----------
        node_name:
            Name of the target track or bus node.
        role_or_handle:
            The effect's role or stable handle.
        param:
            Parameter name to set (case-insensitive).
        value:
            New parameter value in the plugin's native unit.

        Returns
        -------
        dict
            ``{"success": True, "node": ..., "role": ..., "param": ...,
               "param_index": ..., "value": ...}`` plus any range fields from
            the matched param dict, on success.
            ``{"success": False, "message": ...}`` on failure.
        """
        try:
            node = self._graph.get_node(node_name)
        except KeyError:
            return {"success": False, "message": f"Node '{node_name}' not found"}

        if node.kind not in ("track", "bus"):
            return {
                "success": False,
                "message": (
                    f"Node '{node_name}' is kind '{node.kind}'; "
                    "effects chains are only supported on 'track' and 'bus' nodes"
                ),
            }

        try:
            await self._refresh_ids(node)

            effect = self._graph.find_effect(node_name, role_or_handle)
            if effect is None:
                return {
                    "success": False,
                    "message": (
                        f"No effect with role or handle '{role_or_handle}' "
                        f"in node '{node_name}'"
                    ),
                }

            params = await self._remote(node).get_parameters(effect.plugin_id)

            param_lower = param.lower()
            matched: dict | None = None
            for p in params:
                name_val = p.get("name", "")
                if isinstance(name_val, str) and name_val.lower() == param_lower:
                    matched = p
                    break

            if matched is None:
                return {
                    "success": False,
                    "message": (
                        f"No parameter named '{param}' on effect '{role_or_handle}' "
                        f"in node '{node_name}'"
                    ),
                }

            # Resolve the numeric parameter index: prefer an explicit index/id
            # field, fall back to the param's position in the list.
            param_index: int | None = None
            for key in ("index", "id", "parameter_id"):
                if key in matched:
                    try:
                        param_index = int(matched[key])
                        break
                    except (TypeError, ValueError):
                        pass
            if param_index is None:
                param_index = params.index(matched)

            await self._remote(node).set_parameter(effect.plugin_id, param_index, value)

            # Build the response: always include core fields plus any range fields
            # present in the param dict so the caller sees the native scale.
            result: dict = {
                "success": True,
                "node": node_name,
                "role": effect.role,
                "param": param,
                "param_index": param_index,
                "value": value,
            }
            for range_key in ("min", "max", "default", "minimum", "maximum"):
                if range_key in matched:
                    result[range_key] = matched[range_key]

            return result
        except Exception as exc:
            return {"success": False, "message": f"Failed to set parameter: {exc}", "error": str(exc)}
