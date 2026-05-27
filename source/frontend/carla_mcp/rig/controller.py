"""
RigController: node lifecycle management for the in-memory rig graph.

Handles create_bus, create_track, and remove_node by coordinating between the
rig graph, the chain launcher (which spawns Carla sub-processes), and the
JACK router (which undoes PipeWire's hardware auto-connections).

Physical audio wiring between nodes (pw-link) is deferred to a later
increment.  This module only manages the graph and Carla process lifecycle.
"""

from __future__ import annotations

import logging
import time as time_module
from typing import Callable

from carla_mcp.rig.graph import Node, RigGraph

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
    ) -> None:
        self._graph = graph
        self._instance_manager = instance_manager
        self._chain_launcher = chain_launcher
        self._jack_router = jack_router
        self._sleep = sleep

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

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
