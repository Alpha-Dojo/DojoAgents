"""Integration test: the Runtime adopts MCP servers through the shared portal."""

from __future__ import annotations

import threading

import anyio
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path
import tempfile

from dojoagents.config.loader import ConfigStore
from dojoagents.agent.runtime import Runtime


class _FakeMCPServerTask:
    """Stands in for MCPServerTask: reports ready and then idles until stopped.

    It implements the same supervisor contract the runtime relies on (``serve``,
    ``ready``, ``startup_error``, ``stopped``) so the test exercises the real
    portal adoption path without launching a subprocess.
    """

    instances: list["_FakeMCPServerTask"] = []

    def __init__(self, name: str, config: dict) -> None:
        self.name = name
        self.config = config
        tool = MagicMock()
        tool.name = "read_file"
        tool.description = "Read a file"
        tool.inputSchema = {"type": "object", "properties": {}}
        self.tools = [tool]
        self.portal = None
        self.ready = threading.Event()
        self.startup_error: BaseException | None = None
        self.stopped = threading.Event()
        _FakeMCPServerTask.instances.append(self)

    async def serve(self) -> None:
        self.ready.set()
        try:
            await anyio.sleep_forever()
        finally:
            self.stopped.set()

    def request_stop(self) -> None:
        self.stopped.set()

    def request_reconnect(self) -> None:
        return None

    async def call_tool(self, tool_name, arguments, *, timeout=None):  # pragma: no cover
        raise NotImplementedError


def test_runtime_registers_mcp_tools():
    content = """
version: 1
mcp_servers:
  test_filesystem:
    command: "mock_cmd"
    args: []
    enabled: true
"""
    _FakeMCPServerTask.instances.clear()
    from dojoagents.tools import mcp_tool

    with tempfile.TemporaryDirectory() as tmpdir:
        cfg_file = Path(tmpdir) / "agents.yaml"
        cfg_file.write_text(content, encoding="utf-8")
        store = ConfigStore(path=cfg_file)

        with patch("dojoagents.tools.mcp_tool.MCPServerTask", _FakeMCPServerTask):
            runtime = Runtime.from_config_store(store)
            spec = runtime.agent.tool_executor.registry.get("mcp_test_filesystem_read_file")
            assert spec is not None
            assert spec.description == "Read a file"
            assert _FakeMCPServerTask.instances[0].portal is not None

    # The shared portal is a process-wide resource; release it in the test.
    mcp_tool.shutdown_mcp_tools()
    assert all(server.stopped.wait(5.0) for server in _FakeMCPServerTask.instances)


@pytest.mark.asyncio
async def test_mcp_runtime_shutdown_is_safe_without_servers():
    from dojoagents.tools.mcp_tool import ashutdown_mcp_tools

    await ashutdown_mcp_tools()
    await ashutdown_mcp_tools()
