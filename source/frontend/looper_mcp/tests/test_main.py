import pytest
from looper_mcp.main import LOOPER_PORT, LOOPER_HOST, MCP_PORT


def test_default_port():
    assert LOOPER_PORT == "8088"


def test_default_host():
    assert LOOPER_HOST == "127.0.0.1"


def test_default_mcp_port():
    assert MCP_PORT == 3002
