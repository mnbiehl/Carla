import json
import socket
from unittest.mock import MagicMock

import pytest

from carla_mcp.worker import attach, detach, events
from carla_mcp.worker import __main__ as worker_main


def _ping(port):
    with socket.create_connection(("127.0.0.1", port), timeout=2) as s:
        s.sendall(json.dumps({"id": 1, "method": "ping", "params": {}}).encode() + b"\n")
        return json.loads(s.makefile("rb").readline())


def test_attach_starts_server_and_registers_cache():
    host = MagicMock()
    srv = attach(host, port=0, client_name="Carla", version="t")
    try:
        assert _ping(srv.port)["result"] == "pong"
        assert events._cache is srv.api.cache
    finally:
        detach(srv)
    assert events._cache is None


def test_attach_port_in_use_raises_and_unregisters_events():
    # Plain listening socket, no SO_REUSEADDR/SO_REUSEPORT, to occupy a port that a
    # second bind() must fail against.
    blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen(1)
        occupied_port = blocker.getsockname()[1]

        host = MagicMock()
        with pytest.raises(OSError):
            attach(host, port=occupied_port, client_name="Carla", version="t")

        # The engine-callback hook must not be left registered to an orphan cache.
        assert events._cache is None
        # events.py exposes only register()/dispatch() beyond the module state itself;
        # dispatching with nothing registered must be a safe no-op, not reach a stale cache.
        events.dispatch(1, 0, 0, 0, 0, 0.0, "")
        assert events._cache is None
    finally:
        blocker.close()


def test_headless_run_serves_until_engine_stop(monkeypatch):
    host = MagicMock()
    host.engine_init.return_value = True
    host.get_current_plugin_count.return_value = 0
    monkeypatch.setattr(worker_main, "build_host", lambda bin_dir: host)
    monkeypatch.setattr(worker_main, "IDLE_SLEEP_S", 0.001)

    captured = {}

    def fake_serve(server, host_obj, stop_event):
        captured["port"] = server.port
        with socket.create_connection(("127.0.0.1", server.port), timeout=2) as s:
            s.sendall(json.dumps({"id": 1, "method": "engine_stop", "params": {}}).encode() + b"\n")
            json.loads(s.makefile("rb").readline())
        stop_event.wait(2)

    monkeypatch.setattr(worker_main, "idle_loop", fake_serve)
    rc = worker_main.run(["--client-name", "CarlaChain_t", "--port", "0"])
    assert rc == 0
    host.engine_init.assert_called_once_with("JACK", "CarlaChain_t")
    host.engine_close.assert_called_once()


def test_headless_run_fails_when_engine_init_fails(monkeypatch):
    host = MagicMock()
    host.engine_init.return_value = False
    host.get_last_error.return_value = "no jack"
    monkeypatch.setattr(worker_main, "build_host", lambda bin_dir: host)

    captured = {}
    real_attach = worker_main.attach

    def spy_attach(*args, **kwargs):
        srv = real_attach(*args, **kwargs)
        captured["server"] = srv
        return srv

    monkeypatch.setattr(worker_main, "attach", spy_attach)

    assert worker_main.run(["--client-name", "x", "--port", "0"]) == 2

    # Teardown must have actually run on the init-failure path: detach() unregisters the
    # events cache and stops the RPC server, even though the engine itself never started.
    assert events._cache is None
    with pytest.raises(OSError):
        socket.create_connection(("127.0.0.1", captured["server"].port), timeout=2)
