from __future__ import annotations

import pytest

from dojoagents.dashboard.services.benchmark_store import BenchmarkStore
from dojoagents.dashboard.services.dojo_data_gateway import GatewayResult
from dojoagents.dashboard.services.sector_store import SectorStore
from dojoagents.dashboard.services.stock_sector_store import StockSectorStore
from dojoagents.dashboard.services.stock_store import StockStore


class BaseGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def stocks(self, *, market=None):
        self.calls.append(("stocks", market))
        rows = [{"ticker": "AAPL", "market": "us", "short_name": "Apple"}] if market == "us" else []
        return GatewayResult(rows, None, "sdk_snapshot", False)

    async def stock_quotes(self, market, symbols):
        self.calls.append(("stock_quotes", (market, symbols)))
        return GatewayResult(
            [
                {
                    "symbol": "AAPL",
                    "name": "Apple",
                    "last_price": 200,
                    "market_cap": 3_000_000_000,
                    "volume": 10,
                }
            ],
            "2026-06-20",
            "sdk_snapshot",
            False,
        )

    async def sector_taxonomy(self, **filters):
        self.calls.append(("sector_taxonomy", filters))
        return GatewayResult(
            [
                {
                    "id": 1,
                    "name": "Technology",
                    "name_alias": "科技",
                    "level": 1,
                    "children": [
                        {
                            "id": 2,
                            "parent_id": 1,
                            "name": "Software",
                            "name_alias": "软件",
                            "level": 2,
                            "children": [
                                {
                                    "id": 3,
                                    "parent_id": 2,
                                    "name": "Application Software",
                                    "name_alias": "应用软件",
                                    "level": 3,
                                }
                            ],
                        }
                    ],
                }
            ],
            None,
            "sdk_snapshot",
            False,
        )

    async def sector_relations(self, **filters):
        self.calls.append(("sector_relations", filters))
        return GatewayResult(
            [
                {
                    "symbol": "AAPL",
                    "market": "us",
                    "primary": {
                        "level_1": {"zh": "科技", "en": "Technology"},
                        "level_2": {"zh": "软件", "en": "Software"},
                        "level_3": {"zh": "应用软件", "en": "Application Software"},
                    },
                }
            ],
            None,
            "sdk_snapshot",
            False,
        )

    async def benchmark_klines(self, symbol, **window):
        self.calls.append(("benchmark_klines", (symbol, window)))
        return GatewayResult(
            [
                {
                    "bar_time": "2026-06-20",
                    "open": 100,
                    "high": 102,
                    "low": 99,
                    "close": 101,
                }
            ],
            "2026-06-20",
            "sdk_snapshot",
            False,
        )


@pytest.mark.asyncio
async def test_stock_store_loads_catalog_and_quotes_through_gateway() -> None:
    gateway = BaseGateway()
    store = StockStore(gateway)

    await store.load()

    stock = store.get("us", "AAPL")
    assert stock is not None
    assert stock.stock_quote.last_price == 200
    assert ("stocks", "us") in gateway.calls
    assert ("stock_quotes", ("us", ["AAPL"])) in gateway.calls


@pytest.mark.asyncio
async def test_sector_stores_load_taxonomy_and_relations_through_gateway() -> None:
    gateway = BaseGateway()
    taxonomy = SectorStore(gateway)
    relations = StockSectorStore(gateway)

    await taxonomy.load()
    await relations.load()

    assert taxonomy.find_resolved_path("1", "2", "3") is not None
    assert relations.get("us", "AAPL").primary.level_3.en == "Application Software"
    assert ("sector_taxonomy", {"tree": True}) in gateway.calls
    assert ("sector_relations", {}) in gateway.calls


@pytest.mark.asyncio
async def test_benchmark_store_loads_kline_through_gateway() -> None:
    gateway = BaseGateway()
    store = BenchmarkStore(gateway)

    result = await store.get_kline("^SPX", limit=30)

    assert result is not None
    assert result.bars[0].close == 101
    assert gateway.calls == [("benchmark_klines", ("^SPX", {"limit": 30}))]


@pytest.mark.asyncio
async def test_benchmark_store_accepts_online_array_bars() -> None:
    class ArrayGateway(BaseGateway):
        async def benchmark_klines(self, symbol, **window):
            return GatewayResult(
                [["2026-06-20", 100, 102, 99, 101, 1_000, 100_000]],
                "2026-06-20",
                "sdk_online",
                False,
            )

    result = await BenchmarkStore(ArrayGateway()).get_kline("^SPX")

    assert result is not None
    assert result.bars[0].bar_time == "2026-06-20"
    assert result.bars[0].close == 101
    assert result.bars[0].vol == 1_000
