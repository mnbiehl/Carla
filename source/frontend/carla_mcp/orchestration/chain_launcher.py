"""Launches and manages Carla child processes for effects chains."""

import os
import subprocess
import logging
from ..state.instance_manager import CarlaInstance, InstanceManager

logger = logging.getLogger(__name__)


class ChainLauncher:
    """Spawns Carla instances as separate processes."""

    def __init__(self, instance_manager: InstanceManager, carla_binary: str = "./bin/Carla"):
        self._manager = instance_manager
        self._carla_binary = carla_binary

    def launch(self, name: str) -> CarlaInstance:
        if self._manager.get(name) is not None:
            raise ValueError(f"Chain '{name}' already exists")

        mcp_port = self._manager.allocate_port()
        jack_name = f"CarlaChain_{name}"

        env = os.environ.copy()
        env["CARLA_MCP_PORT"] = str(mcp_port)
        env["CARLA_CLIENT_NAME"] = jack_name

        proc = subprocess.Popen([self._carla_binary], env=env)

        instance = CarlaInstance(
            name=name,
            process=proc,
            mcp_port=mcp_port,
            jack_client_name=jack_name,
        )
        self._manager.register(instance)
        logger.info(f"Launched chain '{name}' on MCP port {mcp_port}, JACK client {jack_name}")
        return instance

    def terminate(self, name: str) -> None:
        instance = self._manager.get(name)
        if instance is None:
            raise ValueError(f"Chain '{name}' not found")

        if instance.process and instance.is_running:
            instance.process.terminate()
            try:
                instance.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                instance.process.kill()
                logger.warning(f"Had to kill chain '{name}'")

        if instance.mcp_port is not None:
            self._manager.release_port(instance.mcp_port)

        self._manager.unregister(name)
        logger.info(f"Terminated chain '{name}'")
