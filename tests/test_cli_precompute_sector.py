from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from dojo.client.async_client import AsyncDojo

from dojoagents.cli.main import build_parser
from dojoagents.dashboard.cli import precompute_sector as command
from dojoagents.dashboard.cli.precompute_sector import _write_api_batches
from dojoagents.dashboard.services.financial_registry import FinancialDomainRegistry
from dojoagents.dojo_sdk import close_async_dojo
from tests.dashboard.stores.test_gateway_backed_base_stores import BaseGateway


def test_precompute_sector_accepts_kline_concurrency_override() -> None:
    args = build_parser().parse_args(["precompute-sector", "--market", "us", "--kline-concurrency", "7"])

    assert args.kline_concurrency == 7


def test_precompute_sector_accepts_constituent_trade_date() -> None:
    args = build_parser().parse_args(["precompute-sector", "--market", "cn", "--trade-date", "2026-08-28", "--upload-api"])

    assert args.trade_date == "2026-08-28"


def test_precompute_sector_keeps_start_date_for_legacy_scheduled_uploads() -> None:
    args = build_parser().parse_args(["precompute-sector", "--market", "hk", "--start-date", "2026-08-31", "--upload-api"])

    assert (args.trade_date or args.start_date) == "2026-08-31"


@pytest.mark.asyncio
async def test_constituent_batches_forward_one_trade_date() -> None:
    create_constituents = AsyncMock()
    client = SimpleNamespace(sectors=SimpleNamespace(create_constituents=create_constituents))

    await _write_api_batches(client, "create_constituents", [{"ticker": "A"}, {"ticker": "B"}], trade_date="2026-08-28")

    create_constituents.assert_awaited_once_with(observations=[{"ticker": "A"}, {"ticker": "B"}], trade_date="2026-08-28")


@pytest.fixture
def precompute_runtime(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    config_path = tmp_path / "agents.yaml"
    config_path.write_text("dojosdk:\n  api_key: test-key\n", encoding="utf-8")
    args = build_parser().parse_args(["precompute-sector", "--data-root", str(tmp_path), "--config", str(config_path), "--market", "us", "--upload", "--upload-api"])
    constructor = Mock(side_effect=lambda **kwargs: SimpleNamespace(**kwargs))
    monkeypatch.setattr("dojoagents.dojo_sdk.AsyncDojo", constructor)
    registry = FinancialDomainRegistry()
    registry.init_and_load_all = AsyncMock()
    for name in (
        "sector_store",
        "stock_store",
        "stock_sector_store",
        "benchmark_store",
        "kline_store",
        "sector_precomputed_store",
        "theme_state_precomputed_store",
    ):
        setattr(registry, name, SimpleNamespace(load=AsyncMock(), reload=Mock()))
    registry.stock_fin_indicators_store = SimpleNamespace(get_for_ticker=AsyncMock())
    monkeypatch.setattr(command, "FinancialDomainRegistry", lambda: registry)
    progress = SimpleNamespace(callback=Mock(), close=Mock())
    monkeypatch.setattr(command, "_PrecomputeProgressReporter", lambda: progress)
    build = AsyncMock(return_value={"published_dir": str(tmp_path / "published")})
    theme_build = AsyncMock(return_value={"published_dir": str(tmp_path / "published")})
    upload = AsyncMock(return_value={})
    close = AsyncMock()
    monkeypatch.setattr(command, "build_sector_precomputed", build)
    monkeypatch.setattr("dojoagents.dashboard.jobs.precompute.theme_state_daily.build_theme_state_precomputed", theme_build)
    monkeypatch.setattr(command, "upload_market_precomputed", upload)
    monkeypatch.setattr(command, "close_async_dojo", close)
    return SimpleNamespace(args=args, constructor=constructor, registry=registry, progress=progress, build=build, theme_build=theme_build, upload=upload, close=close)


@pytest.mark.asyncio
@pytest.mark.parametrize("env_online", ["true", "false"])
@pytest.mark.parametrize("with_theme_state", [False, True])
async def test_precompute_uses_online_clients_and_only_required_stores(
    precompute_runtime: SimpleNamespace, monkeypatch: pytest.MonkeyPatch, env_online: str, with_theme_state: bool
) -> None:
    runtime = precompute_runtime
    monkeypatch.setenv("DOJO_ONLINE", env_online)
    monkeypatch.setenv("DOJO_HF_OFFLINE", "true")
    runtime.args.with_theme_state = with_theme_state

    assert await command.run_precompute_sector(runtime.args) == 0

    assert runtime.constructor.call_count == 2
    assert all(call.kwargs["online"] is True for call in runtime.constructor.call_args_list)
    assert runtime.registry.init_and_load_all.call_args.kwargs["preload"] is False
    required = {"sector_store", "stock_store", "stock_sector_store"}
    if with_theme_state:
        required.add("benchmark_store")
        runtime.theme_build.assert_awaited_once()
        assert runtime.theme_build.call_args.kwargs["fin_store"] is runtime.registry.stock_fin_indicators_store
    assert runtime.registry._loaded_store_names == required
    runtime.registry.sector_precomputed_store.load.assert_not_awaited()
    runtime.registry.theme_state_precomputed_store.load.assert_not_awaited()
    runtime.build.assert_awaited_once()
    runtime.upload.assert_awaited_once()
    assert runtime.close.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_store", ["sector_store", "stock_store", "stock_sector_store", "benchmark_store"])
async def test_precompute_required_store_failure_stops_before_publish(precompute_runtime: SimpleNamespace, failed_store: str) -> None:
    runtime = precompute_runtime
    runtime.args.with_theme_state = True
    error = RuntimeError("required data unavailable")
    getattr(runtime.registry, failed_store).load.side_effect = error

    with pytest.raises(RuntimeError, match="required data unavailable") as raised:
        await command.run_precompute_sector(runtime.args)

    assert raised.value is error
    assert failed_store not in runtime.registry._loaded_store_names
    runtime.build.assert_not_awaited()
    runtime.theme_build.assert_not_awaited()
    runtime.upload.assert_not_awaited()
    runtime.registry.sector_precomputed_store.reload.assert_not_called()
    runtime.progress.close.assert_called_once()
    assert runtime.close.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["writer", "init", "build", "upload"])
async def test_precompute_closes_clients_on_failure(precompute_runtime: SimpleNamespace, failure: str) -> None:
    runtime = precompute_runtime
    error = RuntimeError("precompute failed")
    if failure == "writer":
        runtime.constructor.side_effect = [SimpleNamespace(online=True), error]
    else:
        target = runtime.registry.init_and_load_all if failure == "init" else getattr(runtime, failure)
        target.side_effect = error

    with pytest.raises(RuntimeError, match="precompute failed"):
        await command.run_precompute_sector(runtime.args)

    runtime.progress.close.assert_called_once()
    assert runtime.close.await_count == (1 if failure == "writer" else 2)


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_path", [None, "/api/qdata/v1/sector/info", "/api/qdata/v1/stock/ystock_info", "/api/qdata/v1/sector/symbol_relations"])
async def test_precompute_real_registry_uses_online_sdk_without_snapshot_sync(
    precompute_runtime: SimpleNamespace, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed_path: str | None
) -> None:
    runtime = precompute_runtime
    runtime.args.with_theme_state = True
    config_path = Path(runtime.args.config)
    config_path.write_text("dojosdk:\n  api_key: test-key\n  max_retries: 0\n", encoding="utf-8")
    monkeypatch.setenv("DOJO_ONLINE", "true")
    monkeypatch.setenv("DOJO_HF_OFFLINE", "true")
    gateway = BaseGateway()
    requested: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        requested.append(path)
        if path == failed_path:
            return httpx.Response(503, json={"error": "required data unavailable"})
        if path == "/api/qdata/v1/sector/info":
            result = await gateway.sector_taxonomy(tree=True)
            payload = {"sectors": result.data}
        elif path == "/api/qdata/v1/stock/ystock_info":
            result = await gateway.stocks(market=request.url.params.get("market"))
            payload = {"stocks": result.data}
        elif path == "/api/qdata/v1/sector/symbol_relations":
            result = await gateway.sector_relations()
            payload = {"relations": result.data}
        elif path == "/api/qdata/v1/stocks/current_quote":
            result = await gateway.stock_quotes("us", ["AAPL"])
            payload = {"quotes": result.data}
        elif path == "/api/qdata/v1/stock/kline":
            payload = {"klines": [{"symbol": "AAPL", "bar_time": "2026-10-13", "close": 200, "vol": 10}]}
        elif path == "/api/qdata/v1/benchmark/kline":
            result = await gateway.benchmark_klines("^SPX")
            payload = {"klines": result.data}
        elif path == "/api/qdata/v1/stock/fin_indicators":
            payload = {"data": []}
        else:
            raise AssertionError(f"Unexpected precompute request: {path}")
        return httpx.Response(200, json=payload)

    clients: list[AsyncDojo] = []

    def constructor(**kwargs: object) -> AsyncDojo:
        assert kwargs["online"] is True
        client = AsyncDojo(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), **kwargs)
        client.ensure_offline_snapshots = AsyncMock(side_effect=AssertionError("offline snapshot sync"))
        client.stocks.get_klines = AsyncMock(side_effect=AssertionError("offline K-line batch"))
        clients.append(client)
        return client

    monkeypatch.setattr("dojoagents.dojo_sdk.AsyncDojo", constructor)
    monkeypatch.setattr(command, "close_async_dojo", close_async_dojo)
    registry = FinancialDomainRegistry()
    initialize = registry.init_and_load_all

    async def init(client: AsyncDojo, **kwargs: object) -> None:
        assert kwargs["preload"] is False
        await initialize(client, portfolio_data_root=tmp_path / "portfolios", **kwargs)

    monkeypatch.setattr(registry, "init_and_load_all", init)
    monkeypatch.setattr(command, "FinancialDomainRegistry", lambda: registry)
    old_snapshot_load = AsyncMock(side_effect=AssertionError("old snapshot preload"))
    monkeypatch.setattr("dojoagents.dashboard.services.sector_precomputed_store.SectorPrecomputedStore.load", old_snapshot_load)
    monkeypatch.setattr("dojoagents.dashboard.services.sector_precomputed_store.SectorPrecomputedStore.reload", Mock())
    monkeypatch.setattr("dojoagents.dashboard.services.theme_state_precomputed_store.ThemeStatePrecomputedStore.reload", Mock())

    async def build(**kwargs: object) -> dict[str, str]:
        assert registry.stock_store.get("us", "AAPL") is not None
        assert registry.stock_sector_store.get("us", "AAPL") is not None
        klines = await registry.kline_store.get_klines(["AAPL"], market="us", limit=0, fields=("symbol", "bar_time", "close", "vol"))
        assert klines.items["AAPL"].bars[0].close == 200
        return {"published_dir": str(tmp_path / "published")}

    async def theme_build(**kwargs: object) -> dict[str, str]:
        assert await registry.benchmark_store.get_kline("^SPX") is not None
        assert (await registry.stock_fin_indicators_store.get_for_ticker("AAPL", market="us")).items == []
        return {"published_dir": str(tmp_path / "published")}

    runtime.build.side_effect = build
    runtime.theme_build.side_effect = theme_build
    if failed_path is None:
        assert await command.run_precompute_sector(runtime.args) == 0
        assert {"/api/qdata/v1/stock/kline", "/api/qdata/v1/benchmark/kline", "/api/qdata/v1/stock/fin_indicators"}.issubset(requested)
    else:
        with pytest.raises(RuntimeError, match="upstream request failed") as raised:
            await command.run_precompute_sector(runtime.args)
        assert raised.value.__cause__.status_code == 503
        runtime.build.assert_not_awaited()
        runtime.theme_build.assert_not_awaited()
        runtime.upload.assert_not_awaited()
    old_snapshot_load.assert_not_awaited()
    assert len(clients) == 2
    for client in clients:
        assert client._client.is_closed
        client.ensure_offline_snapshots.assert_not_awaited()
        client.stocks.get_klines.assert_not_awaited()


@pytest.mark.asyncio
async def test_precompute_without_uploads_closes_only_the_read_client(precompute_runtime: SimpleNamespace) -> None:
    runtime = precompute_runtime
    runtime.args.upload = False
    runtime.args.upload_api = False

    assert await command.run_precompute_sector(runtime.args) == 0

    assert runtime.constructor.call_count == 1
    assert runtime.constructor.call_args.kwargs["online"] is True
    assert runtime.build.call_args.kwargs["upload_client"] is None
    runtime.upload.assert_not_awaited()
    runtime.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_precompute_theme_skip_flags_keep_lazy_enrichment_disabled(precompute_runtime: SimpleNamespace) -> None:
    runtime = precompute_runtime
    runtime.args.with_theme_state = True
    runtime.args.skip_fundamentals = True
    runtime.args.skip_volume_enrich = True

    assert await command.run_precompute_sector(runtime.args) == 0

    assert runtime.theme_build.call_args.kwargs["fin_store"] is None
    assert runtime.theme_build.call_args.kwargs["kline_store"] is None
