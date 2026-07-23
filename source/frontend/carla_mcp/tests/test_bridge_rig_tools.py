"""Tests for the bridge's thin rig tools and managed-mode process handling."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import carla_mcp.mcp_stdio_bridge as bridge_mod


class TestManagedLooperLaunch:
    @patch("carla_mcp.mcp_stdio_bridge.subprocess.Popen")
    @patch("carla_mcp.mcp_stdio_bridge._is_looper_reachable", return_value=False)
    def test_engine_launched_with_managed_flag(self, _reach, mock_popen):
        proc = MagicMock()
        proc.poll.return_value = None
        proc.pid = 1234
        mock_popen.return_value = proc
        with patch("carla_mcp.mcp_stdio_bridge.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="loopers:loop0_out_l", returncode=0)
            with patch("carla_mcp.mcp_stdio_bridge._is_looper_running", return_value=False):
                # stop before MCP phase by making reachability stay false and
                # patching discover to no-op; we only care about the engine argv
                asyncio.run(bridge_mod._start_looper())
        argv = mock_popen.call_args_list[0].args[0]
        assert argv[0] == "pw-jack"
        assert argv[-1] == "--managed"


class TestThinTools:
    def test_load_delegates_to_do_load(self, tmp_path):
        with patch("carla_mcp.mcp_stdio_bridge.RIG_SESSION_DIR", tmp_path):
            with patch("carla_mcp.mcp_stdio_bridge.do_load",
                       new=AsyncMock(return_value="OK")) as mock_load:
                result = asyncio.run(bridge_mod.load_rig_session.fn("mysession"))
        assert result == "OK"
        name, session_dir = mock_load.await_args.args[0], mock_load.await_args.args[1]
        assert name == "mysession"
        assert session_dir == tmp_path / "mysession"

    def test_save_delegates_to_do_save(self, tmp_path):
        with patch("carla_mcp.mcp_stdio_bridge.RIG_SESSION_DIR", tmp_path):
            with patch("carla_mcp.mcp_stdio_bridge.do_save",
                       new=AsyncMock(return_value="OK")) as mock_save:
                result = asyncio.run(bridge_mod.save_rig_session.fn("mysession"))
        assert result == "OK"
        assert mock_save.await_args.args[0] == "mysession"

    def test_verify_without_session_is_failed(self):
        bridge_mod._current_graph = None
        result = asyncio.run(bridge_mod.verify_rig.fn(""))
        assert result.startswith("FAILED:")

    def test_verify_with_named_session_reads_it(self, tmp_path):
        import json
        sdir = tmp_path / "named"
        sdir.mkdir()
        (sdir / "rig_session.json").write_text(json.dumps(
            {"version": 3, "name": "named", "nodes": [], "edges": [],
             "runtime_units": []}))
        with patch("carla_mcp.mcp_stdio_bridge.RIG_SESSION_DIR", tmp_path):
            with patch("carla_mcp.mcp_stdio_bridge.do_verify",
                       new=AsyncMock(return_value="OK")) as mock_verify:
                result = asyncio.run(bridge_mod.verify_rig.fn("named"))
        assert result == "OK"
        mock_verify.assert_awaited_once()

    def test_routing_reset_delegates(self):
        with patch("carla_mcp.mcp_stdio_bridge.do_routing_reset",
                   new=AsyncMock(return_value="OK")) as mock_reset:
            result = asyncio.run(bridge_mod.rig_routing_reset.fn())
        assert result == "OK"
        mock_reset.assert_awaited_once()

    def test_stop_rig_saves_first_when_asked(self, tmp_path):
        with patch("carla_mcp.mcp_stdio_bridge.RIG_SESSION_DIR", tmp_path):
            with patch("carla_mcp.mcp_stdio_bridge.do_save",
                       new=AsyncMock(return_value="OK")) as mock_save:
                with patch("carla_mcp.mcp_stdio_bridge.do_stop",
                           new=AsyncMock(return_value="OK")) as mock_stop:
                    result = asyncio.run(bridge_mod.stop_rig.fn("keepsake"))
        mock_save.assert_awaited_once()
        mock_stop.assert_awaited_once()
        assert result.count("OK") >= 1

    def test_stop_rig_without_save(self):
        with patch("carla_mcp.mcp_stdio_bridge.do_stop",
                   new=AsyncMock(return_value="OK")) as mock_stop:
            result = asyncio.run(bridge_mod.stop_rig.fn(""))
        mock_stop.assert_awaited_once()
        assert result == "OK"

    def test_legacy_manifest_builder_is_gone(self):
        assert not hasattr(bridge_mod, "_build_rig_manifest")


class TestBridgeOpsPrimitives:
    def test_connect_returns_none_on_success(self):
        from carla_mcp.utils.pw_link import PwLinkResult
        ops = bridge_mod.BridgeOps()
        with patch("carla_mcp.mcp_stdio_bridge.pw_link_connect",
                   return_value=PwLinkResult(success=True)):
            assert ops.connect("a:1", "b:1") is None

    def test_connect_returns_message_on_failure(self):
        from carla_mcp.utils.pw_link import PwLinkResult
        ops = bridge_mod.BridgeOps()
        with patch("carla_mcp.mcp_stdio_bridge.pw_link_connect",
                   return_value=PwLinkResult(success=False, message="nope")):
            assert ops.connect("a:1", "b:1") == "nope"

    def test_wait_ports_returns_missing_after_timeout(self):
        ops = bridge_mod.BridgeOps()
        with patch("carla_mcp.mcp_stdio_bridge.pw_link_list_outputs",
                   return_value=["have:1"]):
            with patch("carla_mcp.mcp_stdio_bridge.pw_link_list_inputs",
                       return_value=[]):
                missing = ops.wait_ports(["have:1", "want:1"], timeout_s=0.1)
        assert missing == ["want:1"]


class TestLooperStateUnwrap:
    """The Rust remote nests state under a "state" key; do_save/observe read
    main_muted/loopers at the TOP level of what looper_get_state() returns, so
    BridgeOps must unwrap the envelope."""

    def test_looper_get_state_unwraps_envelope(self):
        ops = bridge_mod.BridgeOps()
        envelope = {"state": {"main_muted": True,
                              "loopers": [{"id": 1, "port_index": 0}]}}
        ops._looper.get_state = AsyncMock(return_value=envelope)
        state = asyncio.run(ops.looper_get_state())
        assert state == {"main_muted": True,
                         "loopers": [{"id": 1, "port_index": 0}]}

    def test_looper_get_state_passthrough_when_no_envelope(self):
        ops = bridge_mod.BridgeOps()
        raw = {"main_muted": False, "loopers": []}
        ops._looper.get_state = AsyncMock(return_value=raw)
        state = asyncio.run(ops.looper_get_state())
        assert state == raw

    def test_looper_get_state_none_on_connection_error(self):
        ops = bridge_mod.BridgeOps()
        ops._looper.get_state = AsyncMock(side_effect=ConnectionError("down"))
        assert asyncio.run(ops.looper_get_state()) is None


class TestGarbageLooperReply:
    """A half-open socket can yield empty/garbage bytes; LooperClient's
    json.loads(...) then raises json.JSONDecodeError (a ValueError). Per the
    RigOps contract, expected failures must return error strings/None, never
    raise."""

    def test_looper_command_returns_error_string_on_json_decode_error(self):
        ops = bridge_mod.BridgeOps()
        ops._looper.send_command = AsyncMock(
            side_effect=json.JSONDecodeError("Expecting value", "", 0))
        result = asyncio.run(ops._looper_command({"LoadSession": "x"}))
        assert isinstance(result, str)

    def test_looper_get_state_none_on_json_decode_error(self):
        ops = bridge_mod.BridgeOps()
        ops._looper.get_state = AsyncMock(
            side_effect=json.JSONDecodeError("Expecting value", "", 0))
        assert asyncio.run(ops.looper_get_state()) is None

    def test_observe_get_state_none_on_json_decode_error(self):
        ops = bridge_mod.BridgeOps()
        ops._looper.get_state = AsyncMock(
            side_effect=json.JSONDecodeError("Expecting value", "", 0))
        captured = {}

        async def fake_rig_observe(units, **kwargs):
            captured.update(kwargs)
            return "OK"

        with patch("carla_mcp.mcp_stdio_bridge.rig_observe", new=fake_rig_observe):
            result = asyncio.run(ops.observe(None))
        assert result == "OK"
        # Exercise the actual closure passed to rig_observe: it must not raise.
        assert asyncio.run(captured["looper_get_state"]()) is None
