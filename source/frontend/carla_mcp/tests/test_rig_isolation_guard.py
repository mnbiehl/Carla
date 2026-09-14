"""Guard-of-the-guard: the autouse rig isolation fixture in conftest.py
actually blocks real rig subprocess calls and live-port connections, and
does not get in the way of anything harmless.

Note: this deliberately asserts on AssertionError (RigIsolationError's base
class) rather than importing RigIsolationError from conftest. Because
``source/frontend`` is both on pythonpath (for plain ``import carla_mcp...``)
and part of a package chain of its own (``source/frontend/__init__.py``
exists), pytest can import conftest.py as ``frontend.carla_mcp.tests.conftest``
while a module-level ``from carla_mcp.tests.conftest import ...`` here would
load the *same file* again under a different module name, producing a
second, distinct RigIsolationError class that ``pytest.raises`` would not
match. AssertionError is a builtin, so this sidesteps that entirely.
"""

import socket
import subprocess
import threading

import pytest


def test_blocks_pw_link_subprocess_run():
    with pytest.raises(AssertionError, match="blocked real rig process spawn"):
        subprocess.run(["pw-link", "-l"])


def test_blocks_pgrep_popen():
    with pytest.raises(AssertionError, match="blocked real rig process spawn"):
        subprocess.Popen(["pgrep", "x"])


def test_blocks_connect_to_live_rig_port():
    with pytest.raises(AssertionError, match="blocked connection to live rig port"):
        socket.create_connection(("127.0.0.1", 8089))


def test_allows_harmless_subprocess():
    result = subprocess.run(["true"])
    assert result.returncode == 0


def test_allows_connection_to_ephemeral_local_port():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    accepted = {}

    def _accept():
        conn, _ = server.accept()
        accepted["conn"] = conn

    acceptor = threading.Thread(target=_accept)
    acceptor.start()
    try:
        client = socket.create_connection(("127.0.0.1", port), timeout=2)
        acceptor.join(timeout=2)
        client.close()
    finally:
        server.close()
        if "conn" in accepted:
            accepted["conn"].close()
