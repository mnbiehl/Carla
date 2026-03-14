"""Launches and manages Carla child processes for effects chains."""

import os
import subprocess
import logging
from ..state.instance_manager import CarlaInstance, InstanceManager

logger = logging.getLogger(__name__)


class ChainLauncher:
    """Spawns Carla instances as separate processes."""

    def __init__(self, instance_manager: InstanceManager, carla_script: str = None):
        self._manager = instance_manager
        if carla_script is None:
            # Default: carla.py in the frontend directory
            self._carla_script = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "..", "..", "carla.py"
            )
        else:
            self._carla_script = carla_script

    def launch(self, name: str) -> CarlaInstance:
        if self._manager.get(name) is not None:
            raise ValueError(f"Chain '{name}' already exists")

        mcp_port = self._manager.allocate_port()
        jack_name = f"CarlaChain_{name}"

        env = os.environ.copy()
        env["CARLA_MCP_PORT"] = str(mcp_port)
        env["CARLA_CLIENT_NAME"] = jack_name

        # Use /usr/bin/python3 (system Python with PyQt5), not the venv python
        log_file = open(f"/tmp/carla-chain-{name}.log", "w")
        proc = subprocess.Popen(
            ["pw-jack", "/usr/bin/python3", self._carla_script],
            env=env,
            cwd=os.path.dirname(self._carla_script),
            stdout=log_file,
            stderr=log_file,
        )

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
