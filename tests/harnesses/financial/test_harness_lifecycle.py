from __future__ import annotations

from dataclasses import replace
import os

import pytest

from dojoagents.agent.runtime import Runtime
from dojoagents.config.models import AgentsConfig, HarnessConfig, SessionsConfig, StoreProviderConfig
from dojoagents.harnesses.built_in.financial import FinancialHarness
from dojoagents.harnesses.built_in.financial.services import get_financial_service_container
from dojoagents.harnesses.errors import HarnessLifecycleError

from tests.test_runtime_multi_agent_plan import _make_store


class FakeDojoClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.preload_calls = 0
        self.close_calls = 0

    async def preload_offline_data(self):
        self.preload_calls += 1

    async def aclose(self):
        self.close_calls += 1


class FakeRegistry:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.client = None
        self.gateway = None
        self.init_calls = 0
        self.refresh_calls = 0
        self.reset_calls = 0

    async def init_and_load_all(self, client, *, data_root, preload=True, portfolio_data_root=None):
        self.init_calls += 1
        self.client = client
        self.gateway = object()
        self.data_root = data_root
        self.preload = preload
        self.portfolio_data_root = portfolio_data_root
        if self.fail:
            raise RuntimeError("registry failed")

    async def refresh_after_offline_data_update(self):
        self.refresh_calls += 1

    def reset(self):
        self.reset_calls += 1
        self.client = None
        self.gateway = None


def _config(tmp_path, **harness_options):
    return AgentsConfig(
        harness=HarnessConfig(
            id="financial",
            factory="dojoagents.harnesses.built_in.financial:create_harness",
            config={
                "data_root": str(tmp_path / "financial-data"),
                "portfolio_data_root": str(tmp_path / "portfolio-data"),
                "preload_offline_data": True,
                "preload_registry": True,
                "refresh_enabled": False,
                **harness_options,
            },
        ),
        sessions=SessionsConfig(
            store=StoreProviderConfig(options={"root": str(tmp_path / "sessions")}),
            blob_store=StoreProviderConfig(options={"root": str(tmp_path / "blobs")}),
        ),
    )


def test_descriptor_and_legacy_config_are_adapted_once(tmp_path):
    config = _config(tmp_path)
    runtime = Runtime.compose(_make_store(config), host="dashboard")

    assert runtime.harness.descriptor.id == "financial"
    assert runtime.harness.descriptor.version == "1.0.0"
    assert runtime.harness.descriptor.state_schema_version == 1
    assert runtime.harness.descriptor.supported_channels == ("dashboard", "cli", "gateway", "api")
    assert runtime.harness.config.sdk.timeout == config.dojosdk.timeout
    assert runtime.harness.config.tasks.enabled == config.tasks.enabled
    assert runtime.harness.config.data_root == (tmp_path / "financial-data").resolve()
    assert runtime.harness.config.refresh_enabled is False


@pytest.mark.asyncio
async def test_one_runtime_owns_one_container_for_all_consumers_and_shutdown_is_idempotent(tmp_path, monkeypatch):
    monkeypatch.setenv("DOJO_CACHE_DIR", "/existing/cache")
    monkeypatch.setenv("DOJO_ONLINE", "1")
    runtime = Runtime.compose(_make_store(_config(tmp_path)), host="dashboard")
    harness = runtime.harness
    assert isinstance(harness, FinancialHarness)
    client = FakeDojoClient()
    registry = FakeRegistry()
    harness.service_container.replace_factories_for_testing(
        client_factory=lambda **kwargs: client,
        registry_factory=lambda: registry,
    )

    await runtime.startup()

    dashboard_container = get_financial_service_container(runtime)
    cli_container = get_financial_service_container(runtime)
    direct_api_container = runtime.harness_runtime_context.services["financial-domain"]
    assert dashboard_container is cli_container is direct_api_container is harness.service_container
    assert client.preload_calls == 1
    assert registry.init_calls == 1
    assert (await dashboard_container.health()).healthy is True

    await dashboard_container.refresh()
    assert client.preload_calls == 2
    assert registry.refresh_calls == 1
    assert dashboard_container.market_data_revision["revision"]

    await runtime.shutdown()
    await runtime.shutdown()
    assert client.close_calls == 1
    assert registry.reset_calls == 1
    assert os.environ["DOJO_CACHE_DIR"] == "/existing/cache"
    assert os.environ["DOJO_ONLINE"] == "1"


@pytest.mark.asyncio
async def test_startup_failure_rolls_back_and_closes_async_dojo(tmp_path):
    runtime = Runtime.compose(_make_store(_config(tmp_path)), host="api")
    client = FakeDojoClient()
    registry = FakeRegistry(fail=True)
    runtime.harness.service_container.replace_factories_for_testing(
        client_factory=lambda **kwargs: client,
        registry_factory=lambda: registry,
    )

    with pytest.raises(HarnessLifecycleError, match="registry failed"):
        await runtime.startup()

    assert runtime.state == "failed"
    assert client.close_calls == 1
    assert registry.reset_calls == 1


def test_financial_config_rejects_invalid_refresh_interval(tmp_path):
    runtime = Runtime.compose(_make_store(_config(tmp_path)), host="api")
    with pytest.raises(ValueError, match="refresh_poll_seconds"):
        replace(runtime.harness.config, refresh_poll_seconds=0)
