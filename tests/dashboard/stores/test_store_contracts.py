from __future__ import annotations

import inspect

import pytest
from dojo import MaterializationLimitError

import dojoagents.dashboard.services.kline_store as kline_store_module
from dojoagents.dashboard.schemas.portfolio import CreatePortfolioRequest, PortfolioDetail
from dojoagents.dashboard.schemas.stock_kline import ConstituentKlineBatchResponse
from dojoagents.dashboard.schemas.stock import Stock, StockQuote
from dojoagents.dashboard.schemas.stock_sector import StockSectorLabel
from dojoagents.dashboard.services.kline_store import KlineStore
from dojoagents.dashboard.services.kline_bar_utils import KLINE_WARM_MAX_SYMBOLS
from dojoagents.dashboard.services.portfolio_allocation import initial_shares_for_new_holding
from dojoagents.dashboard.services.portfolio_service import PortfolioService
from dojoagents.dashboard.services.portfolio_store import PortfolioStore
from dojoagents.dashboard.services.sector_store import ResolvedSectorPath
from dojoagents.dashboard.services.stock_sector_store import StockSectorStore
from dojoagents.dashboard.services.stock_store import StockStore
from tests.dashboard.fakes.fake_dojo import FakeDojo


def _sector_path() -> ResolvedSectorPath:
    return ResolvedSectorPath(
        level1_id="1",
        level2_id="2",
        level3_id="3",
        level1_zh="科技",
        level1_en="Technology",
        level2_zh="软件",
        level2_en="Software",
        level3_zh="应用软件",
        level3_en="Application Software",
    )


def _quoted_stock(ticker: str = "AAPL", market: str = "us") -> Stock:
    return Stock(
        ticker=ticker,
        market=market,
        short_name=ticker,
        stock_quote=StockQuote(
            ticker=ticker,
            name=ticker,
            last_price=100.0,
            pre_close=99.0,
            open=99.0,
            high=101.0,
            low=98.0,
            change=1.0,
            change_percent=1.0,
            volume=100,
            amount=10_000.0,
            avg_price=100.0,
            market_cap=1_000_000.0,
            turn_rate=1.0,
            pe=20.0,
            pb=3.0,
        ),
    )


def test_in_memory_stock_and_sector_getters_are_synchronous() -> None:
    client = FakeDojo()
    stocks = StockStore(client)
    sectors = StockSectorStore(client)
    stock = _quoted_stock()
    label = StockSectorLabel(ticker="AAPL", market="us")
    stocks.by_ticker["us:AAPL"] = stock
    sectors._cache["us"]["AAPL"] = label

    assert not inspect.iscoroutinefunction(stocks.get)
    assert not inspect.iscoroutinefunction(sectors.get)
    assert stocks.get("us", "AAPL") is stock
    assert sectors.get("us", "AAPL") is label
    assert inspect.iscoroutinefunction(stocks.load)
    assert inspect.iscoroutinefunction(sectors.load)


@pytest.mark.asyncio
async def test_kline_get_or_fetch_and_load_all_share_memory_cache() -> None:
    def kline_rows(*, symbol: str, **_kwargs):
        return [
            {
                "symbol": symbol,
                "bar_time": "2026-06-20",
                "open": 99,
                "high": 101,
                "low": 98,
                "close": 100,
            }
        ]

    client = FakeDojo(stocks={"get_kline": kline_rows})
    store = KlineStore(client, StockStore(client), StockSectorStore(client))

    response = await store.get_or_fetch_kline("AAPL", kline_t="1D", limit=20)

    assert response is not None
    assert response.symbol == "AAPL"
    assert response.bars[0].close == 100
    assert response.as_of == "2026-06-20"
    assert client.stocks.calls == [
        ("get_kline", {"symbol": "AAPL", "limit": 20, "kline_t": "1D"}),
    ]


@pytest.mark.asyncio
async def test_kline_batch_calls_single_symbol_sdk_contract() -> None:
    def kline_rows(*, symbol: str, **_kwargs):
        return [
            {
                "symbol": symbol,
                "bar_time": "2026-06-20",
                "open": 1,
                "high": 2,
                "low": 1,
                "close": 2,
            }
        ]

    client = FakeDojo(stocks={"get_kline": kline_rows})
    store = KlineStore(client, StockStore(client), StockSectorStore(client))

    result = await store.get_klines(["AAPL", "MSFT"], limit=15)

    assert set(result.items) == {"AAPL", "MSFT"}
    assert client.stocks.calls == [
        ("get_kline", {"symbol": "AAPL", "limit": 15}),
        ("get_kline", {"symbol": "MSFT", "limit": 15}),
    ]


@pytest.mark.asyncio
async def test_kline_stats_reports_memory_state() -> None:
    def kline_rows(*, symbol: str, **_kwargs):
        return [
            {
                "symbol": symbol,
                "bar_time": "2026-06-20",
                "open": 99,
                "high": 101,
                "low": 98,
                "close": 100,
            }
        ]

    client = FakeDojo(stocks={"get_kline": kline_rows})
    store = KlineStore(client, StockStore(client), StockSectorStore(client))
    store.member_symbols = 2
    await store.get_or_fetch_kline("AAPL", limit=20)

    stats = await store.stats()

    assert stats.member_symbols == 2
    assert stats.tracked_symbols == 1
    assert stats.loaded_symbols == 1
    assert stats.initial_load_in_progress is False


def test_kline_response_cache_is_invalidated_when_snapshot_token_changes() -> None:
    client = FakeDojo()
    store = KlineStore(client, StockStore(client), StockSectorStore(client))
    response = kline_store_module.StockKlineResponse(
        symbol="AAPL",
        as_of="2026-06-20",
        bars=[],
    )
    first_snapshot = {
        "backend": "huggingface",
        "repo_id": "AlphaDojo/dojo_stock_kline",
        "snapshot_token": "token-1",
        "resolved_revision": "revision-1",
    }
    store._observe_snapshot(first_snapshot)
    key = store._response_cache_key(
        "AAPL",
        market=None,
        kline_t="1D",
        start_time=None,
        end_time=None,
        min_bar_time=None,
        price_adj_type="pre",
        limit=20,
    )
    store._cache_put(key, response)
    assert len(store._cache) == 1

    store._observe_snapshot(
        {
            "backend": "huggingface",
            "repo_id": "AlphaDojo/dojo_stock_kline",
            "snapshot_token": "token-2",
            "resolved_revision": "revision-2",
        }
    )
    assert not store._cache
    assert store.snapshot_metadata == {
        "backend": "huggingface",
        "repo_id": "AlphaDojo/dojo_stock_kline",
        "snapshot_token": "token-2",
        "resolved_revision": "revision-2",
    }


@pytest.mark.asyncio
async def test_kline_store_exposes_load_contract() -> None:
    client = FakeDojo()
    store = KlineStore(client, StockStore(client), StockSectorStore(client))

    assert inspect.iscoroutinefunction(store.load)


@pytest.mark.asyncio
async def test_sector_klines_group_cached_rows_by_scope(monkeypatch) -> None:
    def kline_rows(*, symbol: str, **_kwargs):
        return [
            {
                "symbol": symbol,
                "bar_time": "2026-06-20",
                "open": 1,
                "high": 2,
                "low": 1,
                "close": 2,
            }
        ]

    client = FakeDojo(stocks={"get_kline": kline_rows})
    store = KlineStore(client, StockStore(client), StockSectorStore(client))
    monkeypatch.setattr(
        kline_store_module,
        "collect_sector_scope_tickers",
        lambda *_args, **_kwargs: {
            "L1": {"L1", "L2", "L3"},
            "L2": {"L2", "L3"},
            "L3": {"L3"},
        },
    )

    result = await store.get_sector_klines(_sector_path(), market="us")

    assert result.scopes["L3"].symbols == ["L3"]
    assert result.scopes["L2"].loaded_symbols == 2
    assert result.scopes["L1"].loaded_symbols == 3


@pytest.mark.asyncio
async def test_prioritize_sector_path_fetches_l3_then_l2_then_l1(monkeypatch) -> None:
    client = FakeDojo()
    store = KlineStore(client, StockStore(client), StockSectorStore(client))
    calls: list[list[str]] = []
    monkeypatch.setattr(
        kline_store_module,
        "collect_sector_scope_tickers",
        lambda *_args, **_kwargs: {
            "L1": {"L1", "L2", "L3"},
            "L2": {"L2", "L3"},
            "L3": {"L3"},
        },
    )

    async def record(
        symbols: list[str],
        limit: int = 252,
        fields: tuple[str, ...] | None = None,
    ) -> ConstituentKlineBatchResponse:
        del limit
        assert fields == ("symbol", "bar_time", "open", "high", "low", "close", "vol")
        calls.append(symbols)
        return ConstituentKlineBatchResponse()

    monkeypatch.setattr(store, "get_klines", record)

    await store.prioritize_sector_path(_sector_path(), market="us")

    assert calls == [["L3"], ["L2"], ["L1"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("symbol_count", [199, 200])
async def test_prioritize_sector_path_warms_at_or_below_limit(monkeypatch, symbol_count: int) -> None:
    client = FakeDojo()
    store = KlineStore(client, StockStore(client), StockSectorStore(client))
    symbols = {f"S{index:03d}" for index in range(symbol_count)}
    calls: list[list[str]] = []
    monkeypatch.setattr(
        kline_store_module,
        "collect_sector_scope_tickers",
        lambda *_args, **_kwargs: {"L1": symbols, "L2": symbols, "L3": symbols},
    )

    async def record(requested: list[str], **_kwargs) -> ConstituentKlineBatchResponse:
        calls.append(requested)
        return ConstituentKlineBatchResponse()

    monkeypatch.setattr(store, "get_klines", record)
    await store.prioritize_sector_path(_sector_path(), market="us")

    assert len(calls) == 1
    assert len(calls[0]) == symbol_count


@pytest.mark.asyncio
async def test_prioritize_sector_path_skips_large_level_before_query_and_keeps_dedup(monkeypatch, caplog) -> None:
    client = FakeDojo()
    store = KlineStore(client, StockStore(client), StockSectorStore(client))
    l3 = {f"L3-{index:03d}" for index in range(KLINE_WARM_MAX_SYMBOLS + 1)}
    l2_additions = {"L2-A", "L2-B"}
    l1_additions = {"L1-A"}
    calls: list[list[str]] = []
    monkeypatch.setattr(
        kline_store_module,
        "collect_sector_scope_tickers",
        lambda *_args, **_kwargs: {
            "L3": l3,
            "L2": l3 | l2_additions,
            "L1": l3 | l2_additions | l1_additions,
        },
    )

    async def record(requested: list[str], **_kwargs) -> ConstituentKlineBatchResponse:
        calls.append(requested)
        return ConstituentKlineBatchResponse()

    monkeypatch.setattr(store, "get_klines", record)
    with caplog.at_level("INFO", logger="dojoagents"):
        await store.prioritize_sector_path(_sector_path(), market="us")

    assert calls == [["L2-A", "L2-B"], ["L1-A"]]
    assert "Skipped kline cache warm before query" in caplog.text
    assert "symbols=201 max=200" in caplog.text


@pytest.mark.asyncio
async def test_prioritize_sector_path_materialization_limit_is_best_effort(monkeypatch, caplog) -> None:
    client = FakeDojo()
    store = KlineStore(client, StockStore(client), StockSectorStore(client))
    monkeypatch.setattr(
        kline_store_module,
        "collect_sector_scope_tickers",
        lambda *_args, **_kwargs: {"L3": {"AAPL"}, "L2": {"AAPL"}, "L1": {"AAPL"}},
    )

    async def fail(*_args, **_kwargs):
        raise MaterializationLimitError(limit=100, observed_at_least=101)

    monkeypatch.setattr(store, "get_klines", fail)
    with caplog.at_level("WARNING", logger="dojoagents"):
        await store.prioritize_sector_path(_sector_path(), market="us")

    assert "exceeded materialization limit" in caplog.text


@pytest.mark.asyncio
async def test_prioritize_sector_path_logs_unexpected_warm_error(monkeypatch, caplog) -> None:
    client = FakeDojo()
    store = KlineStore(client, StockStore(client), StockSectorStore(client))
    monkeypatch.setattr(
        kline_store_module,
        "collect_sector_scope_tickers",
        lambda *_args, **_kwargs: {"L3": {"AAPL"}, "L2": {"AAPL"}, "L1": {"AAPL"}},
    )

    async def fail(*_args, **_kwargs):
        raise RuntimeError("unexpected warm failure")

    monkeypatch.setattr(store, "get_klines", fail)
    with caplog.at_level("ERROR", logger="dojoagents"):
        await store.prioritize_sector_path(_sector_path(), market="us")

    assert "Kline cache warm failed" in caplog.text
    assert "unexpected warm failure" in caplog.text


@pytest.mark.asyncio
async def test_initial_holding_shares_awaits_market_cap_allocation() -> None:
    client = FakeDojo()
    stocks = StockStore(client)
    stock = _quoted_stock()
    stocks.by_ticker["us:AAPL"] = stock

    shares = await initial_shares_for_new_holding(stocks, [], "us", "AAPL", capital=1_000.0)

    assert shares == 10


@pytest.mark.asyncio
async def test_portfolio_create_returns_resolved_detail(tmp_path) -> None:
    client = FakeDojo()
    service = PortfolioService(
        PortfolioStore(tmp_path),
        StockStore(client),
        StockSectorStore(client),
        KlineStore(client, StockStore(client), StockSectorStore(client)),
    )

    result = await service.create(CreatePortfolioRequest(name="Long Term"))

    assert isinstance(result, PortfolioDetail)
    assert result.name == "Long Term"
