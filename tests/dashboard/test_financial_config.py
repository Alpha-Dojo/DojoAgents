from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from dojoagents.config.loader import ConfigStore
from dojoagents.config.models import AgentsConfig
from dojoagents.dashboard.server import create_app
from dojoagents.harnesses.built_in.financial.surfaces.dashboard_legacy import (
    LegacyFinancialDashboardSurface,
)


def test_financial_config_has_safe_separate_defaults() -> None:
    config = AgentsConfig().dashboard.financial

    assert config.enabled is True
    assert config.sdk_cache_path == Path("~/.cache/dojo").expanduser()
    assert config.dashboard_data_path == Path("~/.dojo/dashboard-data").expanduser()
    assert config.sdk_cache_path != config.dashboard_data_path
    assert config.stock_quote_refresh_seconds > 0
    assert config.constituent_kline_max_concurrent > 0
    assert config.market_calendar_provider == "exchange_calendars"


def test_financial_config_loads_overrides_and_expands_paths(tmp_path, monkeypatch) -> None:
    sdk_root = tmp_path / "sdk"
    dashboard_root = tmp_path / "dashboard"
    monkeypatch.setenv("TEST_SDK_CACHE", str(sdk_root))
    config_file = tmp_path / "agents.yaml"
    config_file.write_text(
        f"""
dashboard:
  financial:
    enabled: false
    sdk_cache_dir: ${{TEST_SDK_CACHE}}
    dashboard_data_root: {dashboard_root}
    stock_quote_refresh_seconds: 9
    constituent_kline_max_concurrent: 3
    ticker_market_cap_min_us: 2000000000
    derived_cache_schema_version: 4
""",
        encoding="utf-8",
    )

    config = ConfigStore(config_file).snapshot().dashboard.financial

    assert config.enabled is False
    assert config.sdk_cache_path == sdk_root
    assert config.dashboard_data_path == dashboard_root
    assert config.stock_quote_refresh_seconds == 9
    assert config.constituent_kline_max_concurrent == 3
    assert config.ticker_market_cap_min_us == 2_000_000_000
    assert config.derived_cache_schema_version == 4


def test_server_applies_configured_roots_before_sdk_construction(tmp_path) -> None:
    sdk_root = tmp_path / "sdk-cache"
    dashboard_root = tmp_path / "dashboard-data"
    config_file = tmp_path / "agents.yaml"
    config_file.write_text(
        f"""
dashboard:
  financial:
    sdk_cache_dir: {sdk_root}
    dashboard_data_root: {dashboard_root}
""",
        encoding="utf-8",
    )
    received: dict[str, object] = {}

    class Client:
        async def aclose(self):
            return None

    def factory(**_kwargs):
        received["sdk_cache"] = os.environ.get("DOJO_CACHE_DIR")
        return Client()

    class Registry:
        async def init_and_load_all(self, _client, *, data_root, preload):
            received["data_root"] = data_root
            received["preload"] = preload

        def reset(self):
            return None

    runtime = SimpleNamespace(
        config_store=ConfigStore(config_file),
        agent=None,
        scheduler=None,
        extensions=None,
    )
    surface = LegacyFinancialDashboardSurface.from_runtime(
        runtime,
        client_factory=factory,
        registry=Registry(),
    )
    app = create_app(runtime, dashboard_surface=surface)

    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200

    assert received == {
        "sdk_cache": str(sdk_root),
        "data_root": dashboard_root,
        "preload": True,
    }
