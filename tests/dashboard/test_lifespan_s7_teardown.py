"""S8 integration: the Dashboard lifespan owns the S7 portal lifecycles.

The lifespan is the single place that may create and must close the run-manager
portal and the MCP runtime.  These tests drive a real ``TestClient`` lifespan so
the shielded teardown sequence runs exactly as it does in production.
"""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from dojoagents.dashboard.agent_runs import AgentRunManager
from dojoagents.dashboard.server import create_app
from dojoagents.dashboard.services.app_container import (
    DashboardAppServices,
    DashboardAppServicesConfig,
)
from dojoagents.utils.blocking_portal import ThreadedBlockingPortal
from tests.dashboard.test_store_manager import (
    ClosableFakeDojo,
    FakeRuntime,
    RecordingRegistry,
)


def _build_app(tmp_path):
    clients: list[ClosableFakeDojo] = []
    registry = RecordingRegistry()

    def factory(**_kwargs) -> ClosableFakeDojo:
        client = ClosableFakeDojo()
        clients.append(client)
        return client

    services = DashboardAppServices(
        DashboardAppServicesConfig(
            api_key=None,
            base_url=None,
            timeout=60,
            max_retries=1,
            offline_cache_dir=tmp_path / "cache",
            data_root=tmp_path,
            portfolio_data_root=tmp_path / "portfolios",
            refresh_enabled=False,
        ),
        client_factory=factory,
        registry_factory=lambda: registry,
    )
    app = create_app(FakeRuntime(), app_services=services, app_services_owned=True)
    return app, clients, registry


def test_lifespan_closes_the_run_manager_portal_and_the_mcp_runtime(tmp_path) -> None:
    app, clients, registry = _build_app(tmp_path)
    portal = ThreadedBlockingPortal(name="lifespan-agent-runs")
    mcp_shutdowns: list[str] = []

    def run_manager_factory(**_kwargs):
        return AgentRunManager(portal=portal)

    async def fake_mcp_shutdown(*, timeout=None):
        mcp_shutdowns.append("mcp")

    with (
        patch("dojoagents.dashboard.server.AgentRunManager", run_manager_factory),
        patch("dojoagents.tools.mcp_tool.ashutdown_mcp_tools", fake_mcp_shutdown),
    ):
        with TestClient(app) as client:
            assert client.get("/api/health").status_code == 200
            assert portal.running is True
            assert app.state.agent_run_manager._portal is portal

        # Teardown runs inside a shielded scope even though the refresh task
        # group was just cancelled, so every owner is still closed.
        assert portal.state == "closed"
        assert mcp_shutdowns == ["mcp"]
        assert clients[0].closed is True
        assert registry.reset_count == 1


def test_lifespan_teardown_survives_a_failing_mcp_shutdown(tmp_path) -> None:
    app, clients, registry = _build_app(tmp_path)
    portal = ThreadedBlockingPortal(name="lifespan-agent-runs-resilient")

    def run_manager_factory(**_kwargs):
        return AgentRunManager(portal=portal)

    async def failing_mcp_shutdown(*, timeout=None):
        raise RuntimeError("mcp shutdown exploded")

    with (
        patch("dojoagents.dashboard.server.AgentRunManager", run_manager_factory),
        patch("dojoagents.tools.mcp_tool.ashutdown_mcp_tools", failing_mcp_shutdown),
    ):
        with TestClient(app) as client:
            assert client.get("/api/health").status_code == 200

        # A failing subsystem must not abort the remaining teardown steps.
        assert portal.state == "closed"
        assert clients[0].closed is True
        assert registry.reset_count == 1
