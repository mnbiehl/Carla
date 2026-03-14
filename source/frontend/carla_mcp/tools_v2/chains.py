"""
Chain tools for MCP.

Create and delete named routing chains.
"""

from dataclasses import dataclass
from typing import List, Any
from ..state import StateManager, Chain


@dataclass
class ChainResult:
    """Result of a chain operation."""

    success: bool
    message: str
    chain_name: str = ""


def create_chain(
    state_manager: StateManager,
    jack_client: Any,
    name: str,
    components: List[str],
    instance: str = "main"
) -> ChainResult:
    """Create a named chain and connect all components.

    Args:
        state_manager: State manager instance
        jack_client: JACK client for making connections
        name: Name for the chain
        components: Ordered list [source, plugin1, plugin2, ..., destination]
        instance: Which Carla instance this chain belongs to

    Returns:
        ChainResult with success status
    """
    if name in state_manager.chains:
        return ChainResult(
            success=False,
            message=f"Chain '{name}' already exists",
            chain_name=name
        )

    chain = Chain(name=name, components=components, instance=instance)

    connection_pairs = chain.get_connection_pairs()
    connected = []

    for source, dest in connection_pairs:
        try:
            jack_client.connect(source, dest)
            state_manager.add_connection(source, dest)
            connected.append(f"{source} → {dest}")
        except Exception as e:
            for prev_src, prev_dst in chain.get_connection_pairs()[:len(connected)]:
                try:
                    jack_client.disconnect(prev_src, prev_dst)
                except:
                    pass
            return ChainResult(
                success=False,
                message=f"Chain creation failed at {source} → {dest}: {e}",
                chain_name=name
            )

    state_manager.chains[name] = chain

    return ChainResult(
        success=True,
        message=f"Created chain '{name}' with {len(connected)} connections",
        chain_name=name
    )


def delete_chain(
    state_manager: StateManager,
    jack_client: Any,
    name: str
) -> ChainResult:
    """Delete a chain and disconnect all its connections."""
    if name not in state_manager.chains:
        return ChainResult(
            success=False,
            message=f"Chain '{name}' not found",
            chain_name=name
        )

    chain = state_manager.chains[name]

    for source, dest in chain.get_connection_pairs():
        try:
            jack_client.disconnect(source, dest)
            state_manager.remove_connection(source, dest)
        except Exception:
            pass

    del state_manager.chains[name]

    return ChainResult(
        success=True,
        message=f"Deleted chain '{name}'",
        chain_name=name
    )
