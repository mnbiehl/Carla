"""Shared test fixtures for Carla MCP tests."""

import os
import socket
import subprocess

import pytest
from unittest.mock import Mock, MagicMock

# Avoid importing the full carla_mcp package which may have dependency issues
# Tests should import specific modules directly instead


@pytest.fixture
def mock_jack_client():
    """Mock JACK client for testing without real JACK."""
    client = Mock()
    client.get_ports = Mock(return_value=[])
    client.connect = Mock()
    client.disconnect = Mock()
    return client


@pytest.fixture
def mock_carla_host():
    """Mock Carla host instance for testing without real Carla."""
    host = MagicMock()
    host.is_engine_running = Mock(return_value=True)
    host.get_current_plugin_count = Mock(return_value=0)
    host.add_plugin = Mock(return_value=True)
    host.remove_plugin = Mock(return_value=True)
    host.get_plugin_info = Mock(return_value={
        "name": "Test Plugin",
        "label": "test",
        "type": 4,  # LV2
    })
    return host


@pytest.fixture(scope="session")
def spectrum_fixtures_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("spectrum_fixtures")


# ---------------------------------------------------------------------------
# Rig isolation guard
#
# This machine runs a live audio rig (Carla GUI + looperdooper looper + a2j
# on PipeWire) while this unit test suite may be running against it. No unit
# test may ever touch that rig: no real pw-link/pgrep/etc. subprocess call,
# and no real TCP connection to any of the bridge's live ports.
#
# This autouse, function-scoped fixture wraps the subprocess and socket
# entry points those real calls go through for the duration of every test
# (except the opt-in tests under tests/live/, which are gated behind
# CARLA_MCP_LIVE and legitimately want the real thing) and raises
# RigIsolationError the moment a test tries to reach past the guard.
#
# Tests that legitimately need to exercise a subprocess/socket call site
# patch that same module attribute themselves, e.g.
# ``patch("carla_mcp.utils.pw_link.subprocess.run")``. Every module under
# carla_mcp does a plain ``import subprocess`` / ``import socket``, so a
# patch on ``<module>.subprocess.run`` targets the exact same
# ``subprocess.run`` attribute this guard sets — the test's mock simply
# takes over for the duration of that ``with``/decorator, and this guard's
# wrapper resumes once it exits. Nothing needs to special-case those tests.


class RigIsolationError(AssertionError):
    """Raised when a test tries to reach this machine's live rig."""


# Exact executable basenames that must never be spawned from a unit test.
BLOCKED_BINS = frozenset((
    "pw-link", "pw-jack", "pw-metadata", "pw-cli",
    "pgrep", "pkill", "killall",
    "a2jmidid", "loopers",
    "jack_connect", "jack_disconnect",
))

# Substrings that, anywhere in the argv, mean a test is trying to launch a
# real carla_mcp worker/bridge/legacy-carla process rather than mock it.
BLOCKED_ARGV_SUBSTRINGS = ("carla.py", "carla_mcp.worker", "carla_mcp.bridge")

# Hosts/ports the running bridge, Carla RPC worker and looper engine listen
# on for real. See carla_mcp/bridge/app.py / backends/processes.py.
LIVE_HOSTS = frozenset(("127.0.0.1", "localhost", "::1"))
LIVE_PORTS = frozenset((8088, 8089, 8101, 3001, 3002))

# Tests under this path are the opt-in live tests (pytestmark = pytest.mark.live,
# gated on CARLA_MCP_LIVE) — the guard does not apply to them.
_LIVE_TESTS_MARKER = os.path.join("carla_mcp", "tests", "live")


def _argv0(args) -> str:
    """Return the basename of the executable an argv (list or string) invokes."""
    first = args[0] if isinstance(args, (list, tuple)) else str(args).split()[0]
    return str(first).rsplit("/", 1)[-1]


def _argv_text(args) -> str:
    """Flatten a list/tuple/string argv into one string for substring checks."""
    if isinstance(args, (list, tuple)):
        return " ".join(str(a) for a in args)
    return str(args)


def _guard_argv(args, test_id: str) -> None:
    name = _argv0(args)
    text = _argv_text(args)
    if name in BLOCKED_BINS or any(needle in text for needle in BLOCKED_ARGV_SUBSTRINGS):
        raise RigIsolationError(
            f"{test_id}: blocked real rig process spawn: {args!r}"
        )


def _guard_address(address, test_id: str) -> None:
    if not (isinstance(address, tuple) and len(address) >= 2):
        return
    host, port = address[0], address[1]
    if host in LIVE_HOSTS and port in LIVE_PORTS:
        raise RigIsolationError(
            f"{test_id}: blocked connection to live rig port {address!r}"
        )


@pytest.fixture(autouse=True)
def _rig_isolation_guard(request, monkeypatch):
    """Block real rig subprocess calls and live-port connections in every
    unit test. Skipped for tests/live/, the opt-in live tests."""
    if _LIVE_TESTS_MARKER in str(request.node.path):
        yield
        return

    test_id = request.node.nodeid

    real_run = subprocess.run
    real_popen_init = subprocess.Popen.__init__
    real_check_output = subprocess.check_output
    real_call = subprocess.call
    real_create_connection = socket.create_connection
    real_socket_connect = socket.socket.connect

    def guarded_run(args, *a, **kw):
        _guard_argv(args, test_id)
        return real_run(args, *a, **kw)

    def guarded_popen_init(self, *a, **kw):
        # Popen(args, ...) and Popen(args=...) both reach here.
        _guard_argv(a[0] if a else kw.get("args"), test_id)
        return real_popen_init(self, *a, **kw)

    def guarded_check_output(args, *a, **kw):
        _guard_argv(args, test_id)
        return real_check_output(args, *a, **kw)

    def guarded_call(args, *a, **kw):
        _guard_argv(args, test_id)
        return real_call(args, *a, **kw)

    def guarded_create_connection(address, *a, **kw):
        _guard_address(address, test_id)
        return real_create_connection(address, *a, **kw)

    def guarded_socket_connect(self, address):
        _guard_address(address, test_id)
        return real_socket_connect(self, address)

    # monkeypatch.setattr restores every one of these automatically at
    # teardown, even if the test raises.
    monkeypatch.setattr(subprocess, "run", guarded_run)
    monkeypatch.setattr(subprocess.Popen, "__init__", guarded_popen_init)
    monkeypatch.setattr(subprocess, "check_output", guarded_check_output)
    monkeypatch.setattr(subprocess, "call", guarded_call)
    monkeypatch.setattr(socket, "create_connection", guarded_create_connection)
    monkeypatch.setattr(socket.socket, "connect", guarded_socket_connect)

    yield
