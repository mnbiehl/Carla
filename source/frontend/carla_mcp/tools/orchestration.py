"""Orchestration tools for multi-Carla instance management."""

import logging
from fastmcp import FastMCP
from ..state.instance_manager import InstanceManager
from ..orchestration.chain_launcher import ChainLauncher
from ..orchestration.jack_router import JackRouter

logger = logging.getLogger(__name__)

_launcher: ChainLauncher = None
_router: JackRouter = None
_instance_manager: InstanceManager = None


def register_orchestration_tools(
    mcp: FastMCP,
    launcher: ChainLauncher,
    router: JackRouter,
    instance_manager: InstanceManager,
):
    global _launcher, _router, _instance_manager
    _launcher = launcher
    _router = router
    _instance_manager = instance_manager

    @mcp.tool()
    def create_effects_chain(name: str, source_track: str = "") -> str:
        """
        Create a new effects chain as a separate Carla instance.
        Spawns a new Carla process with its own GUI and MCP server.
        Optionally routes a looper track to its input.

        Args:
            name: Name for the chain (e.g. "guitar", "bass")
            source_track: Looper track to route (e.g. "loop0"). Empty to skip routing.
        Returns:
            Status message with chain details
        """
        try:
            instance = _launcher.launch(name)
        except ValueError as e:
            return f"❌ {e}"
        except Exception as e:
            return f"❌ Failed to launch chain: {e}"

        msg = f"✅ Created chain '{name}' (MCP port {instance.mcp_port}, JACK client {instance.jack_client_name})"

        # Wait for JACK ports to register, then remove system auto-connections.
        # PipeWire auto-connects new clients to hardware — we need to undo that.
        # The chain has no plugins yet so it's passing silence — no pop.
        import time
        removed = 0
        for _ in range(5):
            time.sleep(1)
            n = _router.disconnect_client_from_system(instance.jack_client_name)
            removed += n
            if n == 0 and removed > 0:
                break  # No new connections appeared, we're done
        if removed:
            msg += f"\n✅ Removed {removed} system auto-connections"

        if source_track:
            route_result = _router.connect_stereo(
                f"looperdooper:{source_track}_out_l",
                f"looperdooper:{source_track}_out_r",
                f"{instance.jack_client_name}:audio-in1",
                f"{instance.jack_client_name}:audio-in2",
            )
            if route_result.success:
                msg += f"\n✅ Routed {source_track} -> {name}"
            else:
                msg += f"\n⚠️ Chain created but routing failed: {route_result.message}"
        return msg

    @mcp.tool()
    def destroy_effects_chain(name: str) -> str:
        """
        Destroy an effects chain, stopping its Carla instance.
        Args:
            name: Name of the chain to destroy
        Returns:
            Status message
        """
        try:
            _launcher.terminate(name)
            return f"✅ Destroyed chain '{name}'"
        except ValueError as e:
            return f"❌ {e}"
        except Exception as e:
            return f"❌ Failed to destroy chain: {e}"

    @mcp.tool()
    def list_effects_chains() -> str:
        """
        List all active effects chains with status.
        Returns:
            Formatted list of chains
        """
        names = _instance_manager.list_instances()
        if not names:
            return "No active effects chains"
        lines = []
        for name in names:
            inst = _instance_manager.get(name)
            status = "🟢 running" if inst.is_running else "🔴 stopped"
            lines.append(f"  {name}: {status} | MCP port {inst.mcp_port} | JACK {inst.jack_client_name}")
        return "Effects chains:\n" + "\n".join(lines)

    @mcp.tool()
    def route_track_to_chain(track: str, chain: str) -> str:
        """
        Route a looper track's output to a chain's input.
        Args:
            track: Looper track name (e.g. "loop0")
            chain: Chain name (e.g. "guitar")
        Returns:
            Status message
        """
        inst = _instance_manager.get(chain)
        if inst is None:
            return f"❌ Chain '{chain}' not found"
        result = _router.connect_stereo(
            f"looperdooper:{track}_out_l", f"looperdooper:{track}_out_r",
            f"{inst.jack_client_name}:audio-in1", f"{inst.jack_client_name}:audio-in2",
        )
        if result.success:
            return f"✅ Routed {track} -> {chain}"
        return f"❌ {result.message}"

    @mcp.tool()
    def route_chain_to_main(chain: str, main_input_pair: int = 1) -> str:
        """
        Route a chain's output to the main Carla instance's input.
        Args:
            chain: Chain name (e.g. "guitar")
            main_input_pair: Stereo input pair on main instance (1-based)
        Returns:
            Status message
        """
        inst = _instance_manager.get(chain)
        if inst is None:
            return f"❌ Chain '{chain}' not found"
        in_l = main_input_pair * 2 - 1
        in_r = main_input_pair * 2
        result = _router.connect_stereo(
            f"{inst.jack_client_name}:audio-out1", f"{inst.jack_client_name}:audio-out2",
            f"Carla:audio-in{in_l}", f"Carla:audio-in{in_r}",
        )
        if result.success:
            return f"✅ Routed {chain} -> main (inputs {in_l}/{in_r})"
        return f"❌ {result.message}"

    @mcp.tool()
    def get_routing_overview() -> str:
        """
        Show full audio routing between looper, chains, and main instance.
        Returns:
            Formatted routing overview
        """
        # Filter to only show connections involving our components
        prefixes = ["looperdooper:", "Carla:", "CarlaChain_"]
        connections = _router.list_connections(filter_prefixes=prefixes)
        if not connections:
            return "No active audio routes"
        lines = ["Audio routes:"]
        for src, dst in connections:
            lines.append(f"  {src} -> {dst}")
        return "\n".join(lines)
