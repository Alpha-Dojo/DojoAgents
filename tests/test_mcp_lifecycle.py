"""MCP supervisor lifecycle: open, keepalive, reconnect, close (S7 / S8).

These tests drive :class:`MCPToolRuntime` exactly as the Runtime does — a fake
transport on the real portal loop — so the ordering guarantees that make the
session safe to unwind are exercised for real.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import anyio
import pytest

import dojoagents.tools.mcp_tool as mcp_tool
from dojoagents.tools.mcp_tool import MCPServerTask, MCPStartupError, MCPToolRuntime


class _FakeSession:
    """Async context manager standing in for ``mcp.ClientSession``."""

    def __init__(self, state: dict) -> None:
        self.state = state
        self.closed = False
        self.pings = 0

    async def __aenter__(self) -> "_FakeSession":
        self.state["session_enters"] = self.state.get("session_enters", 0) + 1
        return self

    async def __aexit__(self, *exc) -> None:
        self.closed = True
        self.state["session_exits"] = self.state.get("session_exits", 0) + 1

    async def initialize(self) -> None:
        self.state["initialized"] = self.state.get("initialized", 0) + 1

    async def list_tools(self):
        self.pings += 1
        if self.state.get("fail_pings") and self.pings > 1:
            raise RuntimeError("transport closed")
        tool = MagicMock()
        tool.name = "ping_tool"
        tool.description = "health check"
        tool.inputSchema = {"type": "object", "properties": {}}
        return MagicMock(tools=[tool])

    async def call_tool(self, name, *, arguments):
        self.state["calls"] = self.state.get("calls", 0) + 1
        return {"content": f"{name}-ok"}


@contextmanager
def _patched_transport(state: dict):
    transport = MagicMock()
    transport.__aenter__ = AsyncMock(return_value=("read_stream", "write_stream"))
    transport.__aexit__ = AsyncMock(return_value=None)

    def _open_transport(*_args, **_kwargs):
        state["transport_enters"] = state.get("transport_enters", 0) + 1
        return transport

    with patch("dojoagents.tools.mcp_tool.stdio_client", side_effect=_open_transport), \
         patch("dojoagents.tools.mcp_tool.ClientSession", side_effect=lambda *a, **k: _FakeSession(state)):
        yield


def _start_runtime(name: str, state: dict) -> tuple[MCPToolRuntime, MCPServerTask]:
    runtime = MCPToolRuntime(name=name)
    server = MCPServerTask("fake_server", {"command": "echo", "args": []})
    runtime.start_server(server)
    return runtime, server


def _eventually(predicate, *, timeout: float, interval: float = 0.02) -> bool:
    """Poll ``predicate`` without assuming a fixed number of supervisor cycles."""

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return bool(predicate())


def test_serve_opens_the_session_and_shutdown_closes_it() -> None:
    state: dict = {}
    with _patched_transport(state):
        runtime, server = _start_runtime("test-mcp-lifecycle-open", state)
        ident = runtime.portal.loop_thread_ident
        try:
            assert server.ready.is_set()
            assert state["session_enters"] == 1
            assert [tool.name for tool in server.tools] == ["ping_tool"]
        finally:
            runtime.shutdown()
            runtime.shutdown()

    assert state["session_exits"] == 1
    assert server.stopped.wait(5.0)
    assert not runtime.portal.running
    assert [t for t in threading.enumerate() if t.ident == ident] == []


def test_keepalive_failure_reconnects_the_session() -> None:
    state: dict = {"fail_pings": True}
    with _patched_transport(state), patch.object(mcp_tool, "MCP_KEEPALIVE_INTERVAL_SECONDS", 0.05), patch.object(
        mcp_tool, "MCP_KEEPALIVE_TIMEOUT_SECONDS", 0.5
    ), patch.object(mcp_tool, "MCP_RECONNECT_BACKOFF_SECONDS", 0.05):
        runtime, server = _start_runtime("test-mcp-lifecycle-reconnect", state)
        try:
            assert _eventually(lambda: state.get("session_enters", 0) >= 2, timeout=5.0), "keepalive failure did not rebuild the session"
            assert state.get("transport_enters", 0) >= 2
            assert server.reconnect_count >= 1
            assert server.last_reconnect_at is not None
            assert runtime.portal.running
        finally:
            runtime.shutdown()

    assert state["session_exits"] >= 1


def test_explicit_reconnect_request_rebuilds_the_session() -> None:
    state: dict = {}
    with _patched_transport(state), patch.object(mcp_tool, "MCP_RECONNECT_BACKOFF_SECONDS", 0.05):
        runtime, server = _start_runtime("test-mcp-lifecycle-request-reconnect", state)
        try:
            assert runtime.request_reconnect("fake_server") is True
            assert _eventually(lambda: state.get("session_enters", 0) >= 2, timeout=5.0)
        finally:
            runtime.shutdown()

    assert runtime.request_reconnect("unknown_server") is False


def test_start_server_reports_a_bounded_startup_failure() -> None:
    state: dict = {}
    transport = MagicMock()
    transport.__aenter__ = AsyncMock(side_effect=RuntimeError("boom"))
    transport.__aexit__ = AsyncMock(return_value=None)

    with patch("dojoagents.tools.mcp_tool.stdio_client", return_value=transport):
        runtime = MCPToolRuntime(name="test-mcp-lifecycle-failure")
        server = MCPServerTask("broken_server", {"command": "echo", "args": []})
        try:
            with pytest.raises(MCPStartupError, match="failed to start"):
                runtime.start_server(server, timeout=5.0)
            assert isinstance(server.startup_error, RuntimeError)
            assert "broken_server" not in runtime.servers
        finally:
            runtime.shutdown()


@pytest.mark.anyio
async def test_ashutdown_stops_servers_and_closes_the_portal() -> None:
    state: dict = {}
    with _patched_transport(state):
        runtime, server = _start_runtime("test-mcp-lifecycle-ashutdown", state)
        await runtime.ashutdown()

    assert server.stopped.wait(5.0)
    assert not runtime.portal.running
    await runtime.ashutdown()


def test_stop_server_is_scoped_to_one_server() -> None:
    state: dict = {}
    with _patched_transport(state):
        runtime, server = _start_runtime("test-mcp-lifecycle-stop-one", state)
        try:
            assert runtime.stop_server("fake_server") is True
            assert server.stopped.wait(5.0)
            assert runtime.stop_server("fake_server") is False
            assert runtime.portal.running
        finally:
            runtime.shutdown()


def test_concurrent_tool_calls_do_not_deadlock() -> None:
    state: dict = {}
    with _patched_transport(state):
        runtime, server = _start_runtime("test-mcp-lifecycle-concurrency", state)
        results: dict[int, dict] = {}

        def worker(index: int) -> None:
            results[index] = anyio.run(server.call_tool, "ping_tool", {"index": index})

        try:
            workers = [threading.Thread(target=worker, args=(index,)) for index in range(6)]
            for thread in workers:
                thread.start()
            for thread in workers:
                thread.join()
            assert len(results) == 6
            assert {entry["content"] for entry in results.values()} == {"ping_tool-ok"}
        finally:
            runtime.shutdown()

    assert state["calls"] == 6
