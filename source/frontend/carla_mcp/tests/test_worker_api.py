import threading
import time
from unittest.mock import MagicMock

import pytest

from carla_mcp.worker.api import ALLOWLIST, RpcError, WorkerApi
from carla_mcp.worker.patchbay import PatchbayCache


def _host(count=2):
    h = MagicMock()
    h.get_current_plugin_count.return_value = count
    h.is_engine_running.return_value = True
    h.get_buffer_size.return_value = 256
    h.get_sample_rate.return_value = 48000.0
    h.get_plugin_info.side_effect = lambda pid: {
        "name": f"P{pid}", "label": f"lbl{pid}", "filename": f"/f{pid}", "type": 4,
        "uniqueId": 0, "maker": "m", "category": 0, "hints": 0,
    }
    h.get_custom_data_value.side_effect = lambda pid, t, k: "strat/comp" if pid == 1 else ""
    h.get_parameter_count.return_value = 1
    h.get_parameter_info.return_value = {"name": "Threshold", "symbol": "th", "unit": "dB",
                                         "comment": "", "groupName": "", "scalePointCount": 0}
    h.get_parameter_ranges.return_value = {"def": -20.0, "min": -60.0, "max": 0.0,
                                           "step": 0.1, "stepSmall": 0.01, "stepLarge": 1.0}
    h.get_current_parameter_value.return_value = -12.0
    h.get_audio_port_count_info.return_value = {"ins": 2, "outs": 2}
    h.add_plugin.return_value = True
    h.remove_plugin.return_value = True
    h.set_custom_data.return_value = True
    h.patchbay_refresh.return_value = True
    h.patchbay_connect.return_value = True
    h.patchbay_disconnect.return_value = True
    h.save_project.return_value = True
    h.load_project.return_value = True
    h.get_last_error.return_value = "boom"
    return h


def _api(host=None, **kw):
    return WorkerApi(host or _host(), PatchbayCache(), version="v-test", **kw)


def test_allowlist_is_exactly_the_spec_set():
    assert ALLOWLIST == frozenset({
        "ping", "version", "engine_info", "plugins", "plugin_info", "add_plugin",
        "remove_plugin", "set_active", "param_list", "param_get", "param_set",
        "custom_data_get", "custom_data_set", "audio_port_counts", "patchbay_refresh",
        "patchbay_list", "patchbay_connect", "patchbay_disconnect", "project_save",
        "project_load", "engine_stop",
    })


def test_every_allowlisted_method_exists_on_api():
    api = _api()
    for name in ALLOWLIST:
        assert callable(getattr(api, name)), name


def test_dispatch_rejects_unknown_method():
    with pytest.raises(RpcError) as exc:
        _api().dispatch("os_system", {"cmd": "rm"})
    assert exc.value.type == "validation"


def test_dispatch_rejects_bad_params():
    with pytest.raises(RpcError) as exc:
        _api().dispatch("plugin_info", {"nope": 1})
    assert exc.value.type == "validation"


def test_ping_version_engine_info():
    api = _api(client_name="CarlaChain_x")
    assert api.dispatch("ping", {}) == "pong"
    assert api.dispatch("version", {}) == {"worker": "v-test"}
    assert api.dispatch("engine_info", {}) == {
        "running": True, "sample_rate": 48000.0, "buffer_size": 256, "client_name": "CarlaChain_x",
    }


def test_plugins_lists_handles_and_info():
    out = _api().dispatch("plugins", {})
    assert [p["id"] for p in out] == [0, 1]
    assert out[1]["handle"] == "strat/comp" and out[0]["handle"] is None
    assert out[0]["name"] == "P0" and out[0]["type"] == 4


def test_plugin_id_out_of_range_is_not_found():
    with pytest.raises(RpcError) as exc:
        _api().dispatch("plugin_info", {"plugin_id": 7})
    assert exc.value.type == "not_found"


def test_add_plugin_returns_new_id_and_uses_native_binary():
    host = _host(count=2)
    api = _api(host)
    host.get_current_plugin_count.side_effect = [2, 3]  # before, after
    result = api.dispatch("add_plugin", {"ptype": 4, "path": "/b.lv2", "label": "urn:x", "name": ""})
    assert result == {"plugin_id": 2}
    args = host.add_plugin.call_args.args
    assert args[1:5] == (4, "/b.lv2", "", "urn:x")


def test_add_plugin_failure_reports_last_error():
    host = _host()
    host.add_plugin.return_value = False
    with pytest.raises(RpcError) as exc:
        _api(host).dispatch("add_plugin", {"ptype": 4, "path": "/b", "label": "l"})
    assert exc.value.type == "internal" and "boom" in exc.value.message


def test_param_list_and_set():
    api = _api()
    params = api.dispatch("param_list", {"plugin_id": 0})
    assert params == [{"id": 0, "name": "Threshold", "symbol": "th", "unit": "dB",
                       "min": -60.0, "max": 0.0, "default": -20.0, "step": 0.1, "value": -12.0}]
    api.dispatch("param_set", {"plugin_id": 0, "param_id": 0, "value": -3.0})
    api.host.set_parameter_value.assert_called_once_with(0, 0, -3.0)


def test_patchbay_refresh_clears_cache_then_calls_host():
    host = _host()
    cache = PatchbayCache()
    api = WorkerApi(host, cache, version="v")
    cache.on_event(-1, 0, 0, 0, 0, 0.0, "")
    api.dispatch("patchbay_refresh", {})
    host.patchbay_refresh.assert_called_once_with(False)
    assert api.dispatch("patchbay_list", {}) == {"groups": [], "connections": []}


def test_patchbay_connect_maps_args_and_failure():
    host = _host()
    api = _api(host)
    api.dispatch("patchbay_connect", {"group_out": 1, "port_out": 2, "group_in": 3, "port_in": 4})
    host.patchbay_connect.assert_called_once_with(False, 1, 2, 3, 4)
    host.patchbay_connect.return_value = False
    with pytest.raises(RpcError):
        api.dispatch("patchbay_connect", {"group_out": 1, "port_out": 2, "group_in": 3, "port_in": 4})


def test_engine_stop_invokes_callback():
    stopped = []
    api = _api(on_engine_stop=lambda: stopped.append(True))
    assert api.dispatch("engine_stop", {}) == {"stopping": True}
    assert stopped == [True]


class _FakeHost:
    """A real (non-mock) host whose plugin count is genuine mutable state,
    so a race in add_plugin's before/after count reads is actually observable.

    add_plugin sleeps ~5ms before incrementing the count, standing in for a
    real (slow) Carla host call. get_current_plugin_count also has a small
    (~1ms) delay before returning the attribute: a real call into the host
    crosses ctypes, which releases the GIL for the call's duration just like
    add_plugin's sleep does here, so without that delay CPython's GIL happens
    to execute the increment-then-read pair inside add_plugin() atomically
    enough that the race never reproduces in practice. The delay here
    reinstates that realistic window so the race is actually observable.
    """

    def __init__(self):
        self.count = 0

    def add_plugin(self, *_args, **_kwargs):
        time.sleep(0.005)
        self.count += 1
        return True

    def get_current_plugin_count(self):
        time.sleep(0.001)
        return self.count

    def get_last_error(self):
        return ""


def test_dispatch_serializes_concurrent_add_plugin():
    host = _FakeHost()
    api = _api(host)
    results = []
    errors = []

    def worker():
        try:
            result = api.dispatch("add_plugin", {"ptype": 4, "path": "/p", "label": "l"})
            results.append(result["plugin_id"])
        except Exception as exc:  # noqa: BLE001 - test needs to see any failure
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
    assert set(results) == set(range(8))


def test_non_int_plugin_id_is_validation():
    api = _api()
    with pytest.raises(RpcError) as exc:
        api.dispatch("plugin_info", {"plugin_id": "0"})
    assert exc.value.type == "validation"
    with pytest.raises(RpcError) as exc:
        api.dispatch("plugin_info", {"plugin_id": True})
    assert exc.value.type == "validation"


def test_param_set_non_numeric_value_is_validation():
    host = _host()
    api = _api(host)
    with pytest.raises(RpcError) as exc:
        api.dispatch("param_set", {"plugin_id": 0, "param_id": 0, "value": "loud"})
    assert exc.value.type == "validation"
    host.set_parameter_value.assert_not_called()


def test_param_id_non_int_is_validation():
    """Test that non-int param_id in param_get or param_set raises validation error."""
    api = _api()
    with pytest.raises(RpcError) as exc:
        api.dispatch("param_get", {"plugin_id": 0, "param_id": "3"})
    assert exc.value.type == "validation"
    assert "param_id" in exc.value.message

    with pytest.raises(RpcError) as exc:
        api.dispatch("param_set", {"plugin_id": 0, "param_id": "3", "value": -3.0})
    assert exc.value.type == "validation"
    assert "param_id" in exc.value.message


@pytest.mark.parametrize("arg_name,arg_value", [
    ("group_out", "1"),
    ("group_out", True),
    ("port_out", "2"),
    ("port_out", False),
    ("group_in", 3.14),
    ("port_in", [4]),
])
def test_patchbay_connect_all_args_non_int_is_validation(arg_name, arg_value):
    """Test that non-int args in patchbay_connect raise validation error."""
    host = _host()
    api = _api(host)
    params = {"group_out": 1, "port_out": 2, "group_in": 3, "port_in": 4}
    params[arg_name] = arg_value
    with pytest.raises(RpcError) as exc:
        api.dispatch("patchbay_connect", params)
    assert exc.value.type == "validation"
    assert arg_name in exc.value.message
    host.patchbay_connect.assert_not_called()


def test_patchbay_disconnect_non_int_connection_id_is_validation():
    """Test that non-int connection_id in patchbay_disconnect raises validation error."""
    host = _host()
    api = _api(host)
    with pytest.raises(RpcError) as exc:
        api.dispatch("patchbay_disconnect", {"connection_id": "42"})
    assert exc.value.type == "validation"
    assert "connection_id" in exc.value.message
    host.patchbay_disconnect.assert_not_called()

    with pytest.raises(RpcError) as exc:
        api.dispatch("patchbay_disconnect", {"connection_id": True})
    assert exc.value.type == "validation"
    assert "connection_id" in exc.value.message
    host.patchbay_disconnect.assert_not_called()


def test_patchbay_disconnect_valid_connection_id_calls_host():
    """Test that patchbay_disconnect with valid connection_id calls host and returns result."""
    host = _host()
    api = _api(host)
    result = api.dispatch("patchbay_disconnect", {"connection_id": 42})
    assert result == {"disconnected": 42}
    host.patchbay_disconnect.assert_called_once_with(False, 42)
