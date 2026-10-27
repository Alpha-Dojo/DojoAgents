from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from dojo.datasource.registry import HF_REGISTRY

from dojoagents.config.loader import ConfigStore
from dojoagents.config.models import (
    AgentsConfig,
    DEFAULT_DOJOSDK_STARTUP_PATHS,
    DojoSDKConfig,
    DojoSDKOfflineConfig,
)
from dojoagents.dashboard.server import create_app
from dojoagents.dashboard.services.app_container import (
    DashboardAppServices,
    DashboardAppServicesConfig,
)
from dojoagents.harnesses.built_in.financial.config import FinancialHarnessConfig


def test_financial_config_has_safe_separate_defaults() -> None:
    agents = AgentsConfig()
    config = agents.dashboard.financial

    assert config.enabled is True
    assert agents.dojosdk.offline.cache_path == Path("~/.cache/huggingface/hub").expanduser()
    assert config.dashboard_data_path == Path("~/.dojo/dashboard-data").expanduser()
    assert agents.dojosdk.offline.cache_path != config.dashboard_data_path
    assert config.stock_quote_refresh_seconds > 0
    assert config.constituent_kline_max_concurrent == 50
    assert config.market_calendar_provider == "exchange_calendars"
    assert config.startup_preload_stores == ("sector_store", "benchmark_store")
    assert agents.dojosdk.offline.startup_paths == DEFAULT_DOJOSDK_STARTUP_PATHS
    assert set(DEFAULT_DOJOSDK_STARTUP_PATHS) == set(HF_REGISTRY)


def test_financial_config_loads_overrides_and_expands_paths(tmp_path, monkeypatch) -> None:
    sdk_root = tmp_path / "sdk"
    dashboard_root = tmp_path / "dashboard"
    monkeypatch.setenv("TEST_SDK_CACHE", str(sdk_root))
    config_file = tmp_path / "agents.yaml"
    config_file.write_text(
        f"""
dojosdk:
  offline:
    cache_dir: ${{TEST_SDK_CACHE}}
dashboard:
  financial:
    enabled: false
    dashboard_data_root: {dashboard_root}
    stock_quote_refresh_seconds: 9
    constituent_kline_max_concurrent: 3
    startup_preload_stores:
      - sector_store
    ticker_market_cap_min_us: 2000000000
    derived_cache_schema_version: 4
""",
        encoding="utf-8",
    )

    agents = ConfigStore(config_file).snapshot()
    config = agents.dashboard.financial

    assert config.enabled is False
    assert agents.dojosdk.offline.cache_path == sdk_root
    assert config.dashboard_data_path == dashboard_root
    assert config.stock_quote_refresh_seconds == 9
    assert config.constituent_kline_max_concurrent == 3
    assert config.startup_preload_stores == ("sector_store",)
    assert config.ticker_market_cap_min_us == 2_000_000_000
    assert config.derived_cache_schema_version == 4


def test_financial_config_rejects_scalar_startup_preload_stores(tmp_path) -> None:
    config_file = tmp_path / "agents.yaml"
    config_file.write_text(
        "dashboard:\n  financial:\n    startup_preload_stores: sector_store\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="startup_preload_stores"):
        ConfigStore(config_file).snapshot()


def test_dojosdk_offline_config_is_canonical_and_harness_can_override(tmp_path) -> None:
    canonical_cache = tmp_path / "canonical-cache"
    harness_cache = tmp_path / "harness-cache"
    config_file = tmp_path / "agents.yaml"
    config_file.write_text(
        f"""
dojosdk:
  offline:
    enabled: true
    cache_dir: {canonical_cache}
    backend: modelscope
    local_files_only: true
    startup_paths:
      - /api/qdata/v1/stock/kline
    startup_repos:
      - AlphaDojo/example
""",
        encoding="utf-8",
    )
    agents = ConfigStore(config_file).snapshot()

    assert agents.dojosdk.offline.cache_path == canonical_cache
    assert agents.dojosdk.offline.backend == "modelscope"

    context = SimpleNamespace(
        config=agents,
        harness_config={
            "cache_dir": str(harness_cache),
            "offline_mode": False,
            "data_backend": "huggingface",
            "local_files_only": False,
        },
        config_dir=tmp_path,
    )
    financial = FinancialHarnessConfig.from_context(context)

    assert financial.sdk.cache_dir == harness_cache
    assert financial.sdk.offline_mode is False
    assert financial.sdk.backend == "huggingface"
    assert financial.sdk.local_files_only is False


def test_financial_services_disable_offline_work_from_config() -> None:
    agents_config = AgentsConfig(
        dojosdk=DojoSDKConfig(offline=DojoSDKOfflineConfig(enabled=False))
    )
    config = DashboardAppServicesConfig.from_agents_config(agents_config)

    assert config.offline_mode is False
    assert config.ensure_offline_snapshots is False
    assert config.refresh_enabled is False


def test_server_injects_configured_offline_settings_into_sdk(tmp_path) -> None:
    sdk_root = tmp_path / "sdk-cache"
    dashboard_root = tmp_path / "dashboard-data"
    config_file = tmp_path / "agents.yaml"
    config_file.write_text(
        f"""
    dojosdk:
      offline:
        cache_dir: {sdk_root}
        backend: modelscope
        local_files_only: true
        startup_paths: []
    dashboard:
      financial:
        dashboard_data_root: {dashboard_root}
""",
        encoding="utf-8",
    )
    received: dict[str, object] = {}

    class Client:
        async def aclose(self):
            return None

    def factory(**kwargs):
        received["sdk_cache"] = kwargs["offline_config"].cache_dir
        received["backend"] = kwargs["offline_config"].backend
        received["local_files_only"] = kwargs["offline_config"].local_only
        received["online"] = kwargs["online"]
        return Client()

    class Registry:
        client = None

        async def init_and_load_all(
            self,
            client,
            *,
            data_root,
            preload,
            portfolio_data_root=None,
            kline_max_concurrent=50,
        ):
            self.client = client
            received["data_root"] = data_root
            received["preload"] = preload
            received["kline_max_concurrent"] = kline_max_concurrent

        async def preload_startup(self, store_names):
            received["startup_preload_stores"] = tuple(store_names)

        def reset(self):
            return None

    runtime = SimpleNamespace(
        config_store=ConfigStore(config_file),
        agent=None,
        scheduler=None,
        extensions=None,
    )
    services = DashboardAppServices(
        DashboardAppServicesConfig.from_agents_config(runtime.config_store.snapshot()),
        client_factory=factory,
        registry_factory=Registry,
    )
    app = create_app(
        runtime,
        app_services=services,
        app_services_owned=True,
    )

    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200

    assert received == {
        "sdk_cache": str(sdk_root),
        "backend": "modelscope",
        "local_files_only": True,
        "online": False,
        "data_root": dashboard_root,
        "preload": False,
        "kline_max_concurrent": 50,
        "startup_preload_stores": ("sector_store", "benchmark_store"),
    }
