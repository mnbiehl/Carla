import asyncio
from unittest.mock import AsyncMock

from carla_mcp.backends.carla import CarlaClient
from carla_mcp.worker.api import ALLOWLIST


def _client():
    rpc = AsyncMock()
    rpc.call = AsyncMock(return_value={"plugin_id": 3})
    return CarlaClient(rpc), rpc


def test_contract_client_methods_equal_worker_allowlist():
    assert CarlaClient.rpc_methods() == ALLOWLIST


def test_methods_send_name_and_params():
    client, rpc = _client()
    asyncio.run(client.add_plugin(ptype=4, path="/b.lv2", label="urn:x", name="Comp"))
    rpc.call.assert_awaited_once_with("add_plugin", {"ptype": 4, "path": "/b.lv2", "label": "urn:x", "name": "Comp"})
    rpc.call.reset_mock()
    asyncio.run(client.patchbay_connect(group_out=1, port_out=2, group_in=3, port_in=4))
    rpc.call.assert_awaited_once_with("patchbay_connect", {"group_out": 1, "port_out": 2, "group_in": 3, "port_in": 4})
    rpc.call.reset_mock()
    asyncio.run(client.ping())
    rpc.call.assert_awaited_once_with("ping", {})


def test_handles_maps_handle_to_id():
    client, rpc = _client()
    rpc.call = AsyncMock(return_value=[{"id": 0, "handle": None}, {"id": 1, "handle": "strat/comp"}])
    assert asyncio.run(client.handles()) == {"strat/comp": 1}
