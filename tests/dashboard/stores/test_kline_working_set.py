from __future__ import annotations

import pytest

from dojoagents.dashboard.services.dojo_data_gateway import GatewayResult
from dojoagents.dashboard.services.kline_store import KlineStore
from dojoagents.dashboard.services.stock_sector_store import StockSectorStore
from dojoagents.dashboard.services.stock_store import StockStore
from tests.dashboard.fakes.fake_dojo import FakeDojo


class KlineGateway:
    def __init__(
        self,
        responses: list[list[dict]] | None = None,
        *,
        all_klines: list[dict] | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.all_klines = all_klines
        self.calls: list[tuple[str, list[str], dict]] = []
        self.all_klines_calls: list[dict[str, object]] = []

    async def stock_klines(self, market, symbols, **window):
        self.calls.append((market, symbols, window))
        if not self.responses:
            return GatewayResult([], None, "sdk_online", False)
        return GatewayResult(self.responses.pop(0), None, "sdk_online", False)

    async def stock_all_klines(self, *, symbols=None, **window):
        self.all_klines_calls.append({"symbols": symbols, **window})
        if self.all_klines is not None:
            rows = self.all_klines
        elif self.responses:
            rows = self.responses.pop(0)
        else:
            rows = []
        return GatewayResult(rows, None, "sdk_snapshot", False)


def _store(gateway, tmp_path) -> KlineStore:
    client = FakeDojo()
    return KlineStore(
        gateway,
        StockStore(client),
        StockSectorStore(client),
        data_root=tmp_path,
        schema_version=2,
    )


@pytest.mark.asyncio
async def test_kline_store_uses_parquet_and_filters_window(tmp_path) -> None:
    # First, simulate load() to create parquet
    gateway = KlineGateway(
        all_klines=[
            {"symbol": "AAPL", "bar_time": "2026-06-18", "close": 98},
            {"symbol": "AAPL", "bar_time": "2026-06-19", "close": 99},
            {"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100},
        ]
    )
    store = _store(gateway, tmp_path)
    await store.load()

    assert (tmp_path / "working-set" / "dojo_stock_kline.parquet").exists()

    result = await store.get_or_fetch_kline(
        " aapl ",
        market="US",
        kline_t="1D",
        price_adj_type="none",
        start_time="2026-06-19",
        end_time="2026-06-20",
        limit=1,
    )

    assert result is not None
    assert [bar.bar_time for bar in result.bars] == ["2026-06-20"]
    assert result.symbol == "AAPL"


@pytest.mark.asyncio
async def test_refresh_merges_and_deduplicates_bars(tmp_path) -> None:
    gateway = KlineGateway(
        [
            [
                {"symbol": "AAPL", "bar_time": "2026-06-19", "close": 99},
                {"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100},
            ],
            [
                {"symbol": "AAPL", "bar_time": "2026-06-20", "close": 101},
                {"symbol": "AAPL", "bar_time": "2026-06-21", "close": 102},
            ],
        ]
    )
    store = _store(gateway, tmp_path)

    # first call will fetch from gateway because it's not in parquet
    await store.get_or_fetch_kline("AAPL", market="us")

    # second call with refresh=True will fetch again and merge
    result = await store.get_or_fetch_kline("AAPL", market="us", refresh=True)

    assert result is not None
    assert [(bar.bar_time, bar.close) for bar in result.bars] == [
        ("2026-06-19", 99),
        ("2026-06-20", 101),
        ("2026-06-21", 102),
    ]


@pytest.mark.asyncio
async def test_restart_recovers_parquet_without_sdk_call(tmp_path) -> None:
    first_gateway = KlineGateway(all_klines=[{"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100}])
    await _store(first_gateway, tmp_path).load()

    second_gateway = KlineGateway([])

    result = await _store(second_gateway, tmp_path).get_or_fetch_kline("aapl", market="us")

    assert result is not None
    assert result.bars[0].close == 100
    assert len(second_gateway.calls) == 1


@pytest.mark.asyncio
async def test_corrupt_parquet_is_ignored_and_fetches(tmp_path) -> None:
    path = tmp_path / "working-set" / "dojo_stock_kline.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"broken")

    gateway = KlineGateway([[{"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100}]])

    result = await _store(gateway, tmp_path).get_or_fetch_kline("AAPL", market="us")

    assert result is not None
    assert result.bars[0].close == 100
    assert len(gateway.calls) == 1


@pytest.mark.asyncio
async def test_load_prefills_symbol_cache_and_skips_repeat_fetch(tmp_path) -> None:
    gateway = KlineGateway(
        all_klines=[
            {"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100},
            {"symbol": "MSFT", "bar_time": "2026-06-20", "close": 200},
        ]
    )
    client = FakeDojo()
    stock_store = StockStore(client)
    store = KlineStore(
        gateway,
        stock_store,
        StockSectorStore(client),
        data_root=tmp_path,
    )

    await store.load(limit=252)

    assert store.initial_load_complete is True
    assert store.member_symbols == 2
    assert store.load_all("AAPL")[0]["close"] == 100
    assert store.load_all("MSFT")[0]["close"] == 200
    assert gateway.all_klines_calls == [{}]
    assert gateway.calls == []

    # Should fetch from local parquet, not gateway
    result = await store.get_or_fetch_kline("AAPL", market="us", limit=252)

    assert result is not None
    assert result.bars[0].close == 100
    assert gateway.all_klines_calls == [{}]


@pytest.mark.asyncio
async def test_fetches_again_when_cached_window_does_not_cover_requested_start(tmp_path) -> None:
    gateway = KlineGateway(
        [
            [{"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100}],
            [
                {"symbol": "AAPL", "bar_time": "2025-01-01", "close": 80},
                {"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100},
            ],
        ]
    )
    store = _store(gateway, tmp_path)

    first = await store.get_or_fetch_kline("AAPL", market="us", limit=1)
    second = await store.get_or_fetch_kline(
        "AAPL",
        market="us",
        start_time="2025-01-01",
        end_time="2026-06-20",
        limit=0,
    )

    assert first is not None
    assert second is not None
    assert [bar.bar_time for bar in second.bars] == ["2025-01-01", "2026-06-20"]
    assert len(gateway.calls) == 2


@pytest.mark.asyncio
async def test_get_klines_batch_fetch_logic(tmp_path) -> None:
    # Set up some parquet cache for AAPL and MSFT
    gateway_init = KlineGateway(
        all_klines=[
            {"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100},
            {"symbol": "MSFT", "bar_time": "2026-06-20", "close": 200},
        ]
    )
    store_init = _store(gateway_init, tmp_path)
    await store_init.load()

    # New store instance to test batch reading from parquet
    gateway = KlineGateway([])
    client = FakeDojo()
    stock_store = StockStore(client)
    stock_store.by_ticker = {
        "us:AAPL": type("Stock", (), {"ticker": "AAPL"})(),
        "us:MSFT": type("Stock", (), {"ticker": "MSFT"})(),
    }
    store = KlineStore(
        gateway,
        stock_store,
        StockSectorStore(client),
        data_root=tmp_path,
    )

    result = await store.get_klines(["AAPL", "MSFT"], limit=15)

    assert set(result.items.keys()) == {"AAPL", "MSFT"}
    # Because it fetched from Parquet successfully, no gateway calls were made
    assert gateway.calls == []
