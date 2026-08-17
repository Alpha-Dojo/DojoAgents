from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dojoagents.dashboard.server import create_app
from dojoagents.dashboard.services.app_container import (
    DashboardAppServices,
    DashboardAppServicesConfig,
)
from dojoagents.dashboard.store_manager import GlobalStores, stores
from tests.dashboard.fakes.fake_dojo import FakeDojo


class FakeRuntime:
    config_store = None

    class Agent:
        async def run(self, request):
            raise AssertionError("agent should not run in lifecycle tests")

    agent = Agent()
    scheduler = None
    extensions = None


class ClosableFakeDojo(FakeDojo):
    def __init__(self) -> None:
        super().__init__()
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class RecordingRegistry:
    def __init__(self) -> None:
        self.calls: list[tuple[object, Path, bool]] = []
        self.reset_count = 0

    client = None

    async def init_and_load_all(
        self,
        client: object,
        *,
        data_root: Path,
        preload: bool = True,
        portfolio_data_root=None,
        kline_max_concurrent=50,
    ) -> None:
        self.client = client
        self.calls.append((client, data_root, preload))

    def reset(self) -> None:
        self.reset_count += 1


def test_create_app_defers_sdk_and_store_initialization_to_lifespan(tmp_path) -> None:
    clients: list[ClosableFakeDojo] = []
    registry = RecordingRegistry()

    def factory(**_kwargs) -> ClosableFakeDojo:
        client = ClosableFakeDojo()
        clients.append(client)
        return client

    runtime = FakeRuntime()
    services = DashboardAppServices(
        DashboardAppServicesConfig(
            api_key=None,
            base_url=None,
            timeout=60,
            max_retries=1,
            sdk_cache_dir=tmp_path / "cache",
            data_root=tmp_path,
            portfolio_data_root=tmp_path / "portfolios",
            refresh_enabled=False,
        ),
        client_factory=factory,
        registry_factory=lambda: registry,
    )
    app = create_app(
        runtime,
        app_services=services,
        app_services_owned=True,
    )

    assert clients == []
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
        assert len(clients) == 1
        assert registry.calls == [(clients[0], tmp_path, True)]

    assert clients[0].closed is True
    assert registry.reset_count == 1


@pytest.mark.asyncio
async def test_global_stores_share_one_gateway_and_explicit_data_root(tmp_path) -> None:
    class IsolatedStores(GlobalStores):
        pass

    client = FakeDojo()

    await IsolatedStores.init_and_load_all(client, data_root=tmp_path, preload=False)

    assert IsolatedStores.gateway is not None
    assert IsolatedStores.stock_event_store.gateway is IsolatedStores.gateway
    assert IsolatedStores.stock_news_store.gateway is IsolatedStores.gateway
    assert IsolatedStores.stock_fin_indicators_store.gateway is IsolatedStores.gateway
    assert IsolatedStores.stock_income_store.gateway is IsolatedStores.gateway
    assert IsolatedStores.forex_store.gateway is IsolatedStores.gateway
    assert IsolatedStores.portfolio_store.root == tmp_path / "portfolio"
    assert IsolatedStores.kline_store.gateway is IsolatedStores.gateway


@pytest.mark.asyncio
async def test_preload_failure_is_isolated_and_does_not_abort(tmp_path) -> None:
    class IsolatedStores(GlobalStores):
        pass

    await IsolatedStores.init_and_load_all(FakeDojo(), data_root=tmp_path, preload=False)

    async def fail() -> None:
        raise RuntimeError("expected preload failure")

    IsolatedStores.stock_store.load = fail

    errors = await IsolatedStores.preload(["stock_store"])

    assert len(errors) == 1
    assert isinstance(errors[0], RuntimeError)


def test_financial_dependency_before_lifespan_has_clear_error() -> None:
    from dojoagents.dashboard.deps import get_stock_store

    stores.reset()

    with pytest.raises(RuntimeError, match="stock_store is not initialized"):
        get_stock_store()


@pytest.mark.asyncio
async def test_cancel_startup_interrupts_preload_and_restores_resources(tmp_path) -> None:
    preload_started = asyncio.Event()

    class BlockingClient:
        closed = False
        cancel_requested = False

        async def preload_offline_data(self) -> None:
            preload_started.set()
            await asyncio.Event().wait()

        def cancel_preload_offline_data(self) -> None:
            self.cancel_requested = True

        async def aclose(self) -> None:
            self.closed = True

    client = BlockingClient()
    services = DashboardAppServices(
        DashboardAppServicesConfig(
            api_key=None,
            base_url=None,
            timeout=60,
            max_retries=1,
            sdk_cache_dir=tmp_path / "cache",
            data_root=tmp_path,
            portfolio_data_root=tmp_path / "portfolios",
            refresh_enabled=False,
        ),
        client_factory=lambda **_kwargs: client,
        registry_factory=RecordingRegistry,
    )
    original_cache_dir = os.environ.get("DOJO_CACHE_DIR")
    original_online = os.environ.get("DOJO_ONLINE")
    startup_task = asyncio.create_task(services.startup())
    await asyncio.wait_for(preload_started.wait(), timeout=1)

    services.cancel_startup()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(startup_task, timeout=1)

    assert client.closed is True
    assert client.cancel_requested is True
    assert services.client is None
    assert services.registry is None
    assert os.environ.get("DOJO_CACHE_DIR") == original_cache_dir
    assert os.environ.get("DOJO_ONLINE") == original_online
