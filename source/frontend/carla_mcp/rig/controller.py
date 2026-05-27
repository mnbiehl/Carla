"""
RigController: node lifecycle management for the in-memory rig graph.

Handles create_bus, create_track, remove_node, add_effect, and remove_effect
by coordinating between the rig graph, the chain launcher (which spawns Carla
sub-processes), the JACK router (which undoes PipeWire's hardware
auto-connections), and RemoteInstance (which drives each child's MCP tools).

Physical audio wiring between nodes (pw-link) is deferred to a later
increment.  This module only manages the graph and Carla process lifecycle.
"""

from __future__ import annotations

import logging
import time as time_module
from typing import Callable, Optional

from carla_mcp.rig.graph import Effect, Node, RigGraph
from carla_mcp.rig.remote import RemoteInstance

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
    ) -> None:
        self._graph = graph
        self._instance_manager = instance_manager
        self._chain_launcher = chain_launcher
        self._jack_router = jack_router
        self._sleep = sleep
        self._remote_factory = remote_factory

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
        auto-created for it.  Physical audio wiring (pw-link) is NOT performed
        here — the edge is recorded in the graph as an intent only.

        Parameters
        ----------
        name:
            Stable name for the track.
        source:
            Name of the endpoint (physical port base) that feeds this track.

        Returns
        -------
        dict
            ``{"success": True, ...}`` on success, or
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

        # Record the intent edge (physical wiring deferred to a later increment).
        self._graph.add_edge(source, name)

        return {
            "success": True,
            "message": (
                f"Created track '{name}' sourced from '{source}' "
                f"(JACK client {instance.jack_client_name})"
            ),
            "name": name,
            "jack_client": instance.jack_client_name,
            "source": source,
            "source_was_new": source_was_new,
        }

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
