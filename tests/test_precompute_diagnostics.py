from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import pytest

from dojoagents.cli.main import build_parser
from dojoagents.dashboard.cli.precompute_sector import log_precompute_sdk_runtime, log_precompute_startup
from dojoagents.config.loader import ConfigStore
from dojoagents.dashboard.jobs.precompute.sector_daily import PrecomputeInputSnapshot, compute_sector_precomputed_frames
from dojoagents.dashboard.services.dojo_data_gateway import DojoDataGateway
from dojoagents.dashboard.services.kline_store import KlineStore
from dojoagents.logging import LOGGER, log_debug_configuration
from tests.dashboard.fakes.fake_dojo import FakeDojo


@pytest.fixture
def capture_diagnostics(monkeypatch, caplog):
    monkeypatch.setattr(LOGGER, "handlers", [*LOGGER.handlers, caplog.handler])
    caplog.set_level(logging.DEBUG, logger="dojoagents")
    return caplog


def test_debug_configuration_redacts_secrets_and_preserves_settings(capture_diagnostics) -> None:
    configuration = {
        "model": "test-model",
        "max_tokens": 4096,
        "max_input_tokens": None,
        "api_key": "provider-private",
        "gateway": {"token": "gateway-private"},
        "default_headers": {"X-Custom": "header-private"},
        "connection_url": "postgresql://user:db-private@example.test/database",
        "instructions": "Read https://user:instruction-private@example.test/data?key=query-private before running",
        "mcp": {"env": {"CUSTOM_VALUE": "env-private"}, "args": ["--key", "argument-private"], "headers": {"X-Custom": "header-private"}},
        "base_url": "https://user:password-private@example.test/api?key=query-private#fragment-private",
    }

    log_debug_configuration("test_config", configuration)

    message = capture_diagnostics.records[-1].getMessage()
    assert all(line.startswith("test_config configuration=") for line in message.splitlines())
    logged = json.loads("\n".join(line.split("configuration=", 1)[1] for line in message.splitlines()))
    assert logged["model"] == "test-model"
    assert logged["max_tokens"] == 4096
    assert logged["max_input_tokens"] is None
    assert logged["api_key"] == "***"
    assert logged["gateway"]["token"] == "***"
    assert logged["mcp"] == {"env": "***", "args": "***", "headers": "***"}
    assert logged["base_url"] == "https://example.test/api"
    assert logged["default_headers"] == "***"
    assert logged["connection_url"] == "postgresql://example.test/database"
    assert logged["instructions"] == "Read https://example.test/data before running"
    assert "private" not in message
    assert configuration["api_key"] == "provider-private"


@pytest.mark.parametrize("task", ["precompute-sector", "precompute-sector-theme-state"])
def test_debug_flag_logs_effective_configuration_and_runtime(tmp_path, monkeypatch, capture_diagnostics, task) -> None:
    config_path = tmp_path / "agents.yaml"
    config_path.write_text("dojosdk:\n  api_key: sdk-private\n  offline:\n    enabled: true\n", encoding="utf-8")
    monkeypatch.setenv("DOJO_API_KEY", "sdk-private")
    args = build_parser().parse_args([task, "--debug", "--config", str(config_path)])

    log_precompute_startup(args, ConfigStore(config_path))
    log_precompute_sdk_runtime(
        SimpleNamespace(online=True, _data_source=None, api_key="sdk-private", base_url="https://user:sdk-private@example.test/api?key=sdk-private"), role="reader"
    )

    messages = "\n".join(record.getMessage() for record in capture_diagnostics.records)
    for event in ("precompute_task_config", "precompute_agent_config", "precompute_sdk_config", "precompute_sdk_runtime"):
        assert event in messages
    assert '"online": true' in messages
    assert '"data_source": null' in messages
    assert '"authenticated": true' in messages
    assert '"enabled": true' in messages
    assert str(config_path) in messages
    assert "sdk-private" not in messages


@pytest.mark.asyncio
async def test_kline_debug_logs_raw_and_normalized_dates_without_changing_data(capture_diagnostics) -> None:
    client = FakeDojo(stocks={"get_kline": {"data": [{"symbol": "AAA", "bar_time": 1791907200000, "close": 101.0, "vol": 10.0}]}})
    client._online = True
    store = KlineStore(DojoDataGateway(client), SimpleNamespace(), SimpleNamespace())

    result = await store.get_klines(["AAA"], market="sh", start_time="2026-10-01", limit=0, refresh=True)

    assert result.items["AAA"].bars[0].bar_time == "2026-10-13"
    messages = "\n".join(record.getMessage() for record in capture_diagnostics.records)
    assert "route=online_per_symbol" in messages
    assert "dojo_kline_raw_sample" in messages and "1791907200000" in messages
    assert '"bar_time_type": "int"' in messages
    assert "dojo_kline_normalized" in messages and "max_date=2026-10-13" in messages


@pytest.mark.parametrize("bars,reason", [([("2026-10-13", 100.0)], "window"), ([("2026-10-14", 101.0)], "baseline"), ([("2026-10-13", 100.0), ("2026-10-14", 201.0)], "outliers")])
def test_empty_sector_debug_logs_distinguish_rejection_reasons(capture_diagnostics, bars, reason) -> None:
    member = {"market": "sh", "ticker": "AAA", "level1_id": "1", "level2_id": "2", "level3_id": "3", "role": "primary", "market_cap": 2_000_000_000.0, "pe": 20.0}
    rows = [{"market": "sh", "ticker": "AAA", "trade_date": day, "close": close} for day, close in bars]
    snapshot = PrecomputeInputSnapshot("2026-10-14", None, "now", [member], rows, {})

    with pytest.raises(ValueError, match="Sector daily output is empty"):
        compute_sector_precomputed_frames(snapshot)

    messages = "\n".join(record.getMessage() for record in capture_diagnostics.records)
    assert "precompute_empty_sector_output start_date=2026-10-14" in messages
    if reason == "window":
        assert "precompute_ticker_window start_date=2026-10-14 rows=0" in messages
    elif reason == "baseline":
        assert "tickers_without_baseline=1" in messages
        assert "missing_returns=1" in messages and "finite_returns=0" in messages
    else:
        assert "'outliers': 1" in messages
        assert "return_days=1 return_columns=1" in messages


def test_empty_sector_debug_logs_coverage_rejections(capture_diagnostics) -> None:
    members = [
        {"market": "sh", "ticker": ticker, "level1_id": "1", "level2_id": "2", "level3_id": "3", "role": "primary", "market_cap": cap, "pe": 20.0}
        for ticker, cap in (("BIG", 9_000_000_000.0), ("SMALL", 2_000_000_000.0))
    ]
    rows = [
        {"market": "sh", "ticker": ticker, "trade_date": day, "close": close}
        for ticker, day, close in (("BIG", "2026-10-14", 100.0), ("SMALL", "2026-10-13", 100.0), ("SMALL", "2026-10-14", 101.0))
    ]

    with pytest.raises(ValueError, match="Sector daily output is empty"):
        compute_sector_precomputed_frames(PrecomputeInputSnapshot("2026-10-14", None, "now", members, rows, {}))

    messages = "\n".join(record.getMessage() for record in capture_diagnostics.records)
    assert "finite_returns=1" in messages
    assert "'coverage': 1" in messages
