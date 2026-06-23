from __future__ import annotations

import json

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
async def test_working_set_uses_canonical_key_and_post_filters_window(tmp_path) -> None:
    gateway = KlineGateway(
        [
            [
                {"symbol": "aapl", "bar_time": "2026-06-18", "close": 98},
                {"symbol": "aapl", "bar_time": "2026-06-19", "close": 99},
                {"symbol": "aapl", "bar_time": "2026-06-20", "close": 100},
            ]
        ]
    )
    store = _store(gateway, tmp_path)

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
    assert gateway.calls == [
        (
            "us",
            ["AAPL"],
            {
                "kline_t": "1D",
                "start_time": "2026-06-19",
                "end_time": "2026-06-20",
                "price_adj_type": "none",
                "limit": 1,
            },
        )
    ]
    path = tmp_path / "working-set" / "stock-kline" / "us" / "AAPL" / "1D-none.jsonl"
    assert path.exists()


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

    await store.get_or_fetch_kline("AAPL", market="us")
    result = await store.get_or_fetch_kline("AAPL", market="us", refresh=True)

    assert result is not None
    assert [(bar.bar_time, bar.close) for bar in result.bars] == [
        ("2026-06-19", 99),
        ("2026-06-20", 101),
        ("2026-06-21", 102),
    ]


@pytest.mark.asyncio
async def test_restart_recovers_working_set_without_sdk_call(tmp_path) -> None:
    first_gateway = KlineGateway([[{"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100}]])
    await _store(first_gateway, tmp_path).get_or_fetch_kline("AAPL", market="us")
    second_gateway = KlineGateway([])

    result = await _store(second_gateway, tmp_path).get_or_fetch_kline("aapl", market="us")

    assert result is not None
    assert result.bars[0].close == 100
    assert second_gateway.calls == []


@pytest.mark.asyncio
async def test_corrupt_working_set_is_preserved_then_rebuilt(tmp_path) -> None:
    path = tmp_path / "working-set" / "stock-kline" / "us" / "AAPL" / "1D-none.jsonl"
    path.parent.mkdir(parents=True)
    path.write_text("{broken", encoding="utf-8")
    gateway = KlineGateway([[{"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100}]])

    result = await _store(gateway, tmp_path).get_or_fetch_kline("AAPL", market="us")

    assert result is not None
    assert json.loads(path.read_text(encoding="utf-8").splitlines()[0]) == {"schema_version": 2}
    invalid = list(path.parent.glob("1D-none.jsonl.invalid-*"))
    assert len(invalid) == 1
    assert invalid[0].read_text(encoding="utf-8") == "{broken"


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
async def test_get_klines_uses_single_batch_gateway_call(tmp_path) -> None:
    gateway = KlineGateway(
        [
            [
                {"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100},
                {"symbol": "MSFT", "bar_time": "2026-06-20", "close": 200},
            ]
        ]
    )
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

    assert set(result.items) == {"AAPL", "MSFT"}
    assert gateway.all_klines_calls == [{"symbols": ["AAPL", "MSFT"]}]
    assert gateway.calls == []
