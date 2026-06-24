from __future__ import annotations

from types import SimpleNamespace

import pytest

import dojoagents.dashboard.services.domain_api as domain_api
from dojoagents.dashboard.schemas.benchmark import (
    BenchmarkCard,
    BenchmarkKline,
    BilingualText,
    DojoMeshBenchmarksResponse,
    MarketBenchmarks,
)


@pytest.mark.asyncio
async def test_build_market_overview_passes_days_to_benchmark_store() -> None:
    captured: dict[str, int | None] = {"days": None}

    class BenchmarkStoreStub:
        async def get_benchmarks(self, *, days: int = 1):
            captured["days"] = days
            return DojoMeshBenchmarksResponse(
                as_of="2026-06-20",
                markets={
                    "us": MarketBenchmarks(
                        default_benchmark="^SPX",
                        benchmarks=[
                            BenchmarkCard(
                                market="us",
                                symbol="^SPX",
                                name=BilingualText(zh="标普500", en="S&P 500"),
                                price=6000.0,
                                change_percent=1.2,
                                kline=[
                                    BenchmarkKline(datetime="2026-06-19", close=5900.0),
                                    BenchmarkKline(datetime="2026-06-20", close=6000.0),
                                ],
                            )
                        ],
                    )
                },
            )

    registry = SimpleNamespace(
        benchmark_store=BenchmarkStoreStub(),
        stock_store=SimpleNamespace(list_market=lambda _market: []),
    )

    response = await domain_api.build_market_overview(
        registry,
        days=5,
        market="us",
    )

    assert captured["days"] == 5
    assert response.benchmarks["us"][0].symbol == "^SPX"
    assert response.window_start == "2026-06-19"
    assert response.window_end == "2026-06-20"
