from __future__ import annotations

import asyncio
from typing import Any

import pytest

from dojoagents.dashboard.services.dojo_data_gateway import GatewayResult
from dojoagents.dashboard.services.forex_store import ForexStore
from dojoagents.dashboard.services.stock_event_store import StockEventStore
from dojoagents.dashboard.services.stock_fin_indicators_store import StockFinIndicatorsStore
from dojoagents.dashboard.services.stock_income_store import StockIncomeStore
from dojoagents.dashboard.services.stock_news_store import StockNewsStore


class StubGateway:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = []
        self.responses: dict[str, GatewayResult[Any]] = {}

    async def _result(self, method: str, *args: Any, **kwargs: Any) -> GatewayResult[Any]:
        self.calls.append((method, args, kwargs))
        return self.responses[method]

    async def stock_events(self, *args: Any, **kwargs: Any) -> GatewayResult[list[dict]]:
        return await self._result("stock_events", *args, **kwargs)

    async def stock_news(self, *args: Any, **kwargs: Any) -> GatewayResult[list[dict]]:
        return await self._result("stock_news", *args, **kwargs)

    async def stock_financial_indicators(self, *args: Any, **kwargs: Any) -> GatewayResult[list[dict]]:
        return await self._result("stock_financial_indicators", *args, **kwargs)

    async def stock_income(self, *args: Any, **kwargs: Any) -> GatewayResult[list[dict]]:
        return await self._result("stock_income", *args, **kwargs)

    async def forex(self, *args: Any, **kwargs: Any) -> GatewayResult[list[dict]]:
        return await self._result("forex", *args, **kwargs)


@pytest.mark.asyncio
async def test_event_store_returns_complete_sorted_contract() -> None:
    gateway = StubGateway()
    gateway.responses["stock_events"] = GatewayResult(
        [
            {"event_type": "报表披露", "notice_date": "2026-07-22", "level1_content": "中报"},
            {"event_type": "分红", "notice_date": "2026-06-01", "level1_content": "派息"},
        ],
        "2026-07-22T00:00:00Z",
        "sdk_online",
        False,
    )

    result = await StockEventStore(gateway).get_for_ticker("googl", market="us", page_size=10)

    assert result.ticker == "GOOGL"
    assert result.market == "us"
    assert result.as_of == "2026-07-22"
    assert result.source == "sdk_online"
    assert result.stale is False
    assert [item["event_type"] for item in result.items] == ["报表披露", "分红"]
    assert gateway.calls == [("stock_events", ("us", "GOOGL"), {"page": 1, "page_size": 10})]


@pytest.mark.asyncio
async def test_news_store_normalizes_dates_and_removes_similar_titles() -> None:
    gateway = StubGateway()
    gateway.responses["stock_news"] = GatewayResult(
        [
            {"id": 1, "title": "Nvidia launches a new AI chip", "publish_date": "Jun 16, 2026"},
            {"id": 2, "title": "Nvidia launches a new AI chip!", "publish_date": "Jun 15, 2026"},
        ],
        None,
        "sdk_snapshot",
        True,
    )

    result = await StockNewsStore(gateway).get_for_ticker("nvda", market="us", page_size=20)

    assert result.ticker == "NVDA"
    assert result.as_of == "2026-06-16"
    assert result.source == "sdk_snapshot"
    assert result.stale is True
    assert len(result.items) == 1
    assert gateway.calls == [("stock_news", ("us", "NVDA"), {"page": 1, "page_size": 20})]


@pytest.mark.asyncio
async def test_fin_indicator_store_sets_market_report_type_and_latest_date() -> None:
    gateway = StubGateway()
    gateway.responses["stock_financial_indicators"] = GatewayResult(
        [
            {"std_report_date": "2025-12-31 00:00:00", "net_profit_attr_parent": 10},
            {"std_report_date": "2026-03-31 00:00:00", "net_profit_attr_parent": 12},
        ],
        None,
        "sdk_online",
        False,
    )

    result = await StockFinIndicatorsStore(gateway).get_for_ticker("0700.hk", market="hk", limit=20)

    assert result.ticker == "0700.HK"
    assert result.report_type == "accumulate"
    assert result.as_of == "2026-03-31"
    assert len(result.items) == 2
    assert gateway.calls == [
        (
            "stock_financial_indicators",
            ("hk", "0700.HK"),
            {"report_type": "accumulate", "limit": 20},
        )
    ]


@pytest.mark.asyncio
async def test_income_store_builds_latest_non_aggregate_distributions() -> None:
    gateway = StubGateway()
    gateway.responses["stock_income"] = GatewayResult(
        [
            {
                "report_date": "2026-03-31 00:00:00",
                "item_name": "通信解决方案",
                "main_business_income": 4_534_700_000,
                "mbi_ratio": 0.595097,
                "mainop_type": 2,
            },
            {
                "report_date": "2026-03-31 00:00:00",
                "item_name": "总计",
                "main_business_income": 7_620_000_000,
                "mbi_ratio": 1,
                "mainop_type": 2,
            },
            {
                "report_date": "2025-12-31 00:00:00",
                "item_name": "旧业务",
                "main_business_income": 1,
                "mbi_ratio": 1,
                "mainop_type": 2,
            },
        ],
        None,
        "sdk_online",
        False,
    )

    result = await StockIncomeStore(gateway).get_for_ticker("aph", market="us", page_size=100)

    assert result.report_date == "2026-03-31 00:00:00"
    product = next(item for item in result.distributions if item.mainop_type == "2")
    assert [item.item_name for item in product.items] == ["通信解决方案"]
    assert gateway.calls == [("stock_income", ("us", "APH"), {"page": 1, "page_size": 100})]


@pytest.mark.asyncio
async def test_forex_store_uses_gateway_symbol_contract(tmp_path) -> None:
    gateway = StubGateway()
    gateway.responses["forex"] = GatewayResult(
        [{"bar_time": "2026-06-20", "close": 7.15}],
        "2026-06-20",
        "sdk_online",
        False,
    )
    store = ForexStore(gateway)

    rows = await store._fetch_remote("USDCNY", limit=30)

    assert rows == [{"bar_time": "2026-06-20", "close": 7.15}]
    assert gateway.calls == [("forex", ("USDCNY",), {"limit": 30})]


@pytest.mark.asyncio
async def test_resource_stores_ignore_malformed_rows() -> None:
    gateway = StubGateway()
    gateway.responses["stock_events"] = GatewayResult(
        [None, "bad-row", {"notice_date": "2026-06-20", "event_type": "分红"}],  # type: ignore[list-item]
        None,
        "sdk_online",
        False,
    )

    result = await StockEventStore(gateway).get_for_ticker("AAPL", market="us")

    assert result.items == [{"notice_date": "2026-06-20", "event_type": "分红"}]


@pytest.mark.asyncio
async def test_income_empty_data_returns_stable_distribution_groups() -> None:
    gateway = StubGateway()
    gateway.responses["stock_income"] = GatewayResult([], None, "sdk_snapshot", True)

    result = await StockIncomeStore(gateway).get_for_ticker("AAPL", market="us")

    assert result.report_date is None
    assert [group.mainop_type for group in result.distributions] == ["1", "2", "3"]
    assert all(not group.items for group in result.distributions)


@pytest.mark.asyncio
async def test_fin_indicator_store_reuses_cached_response_and_singleflight() -> None:
    gateway = StubGateway()
    first = asyncio.Event()
    release = asyncio.Event()

    async def delayed(*args: Any, **kwargs: Any) -> GatewayResult[list[dict]]:
        gateway.calls.append(("stock_financial_indicators", args, kwargs))
        first.set()
        await release.wait()
        return GatewayResult(
            [{"std_report_date": "2026-03-31 00:00:00", "net_profit_attr_parent": 12}],
            None,
            "sdk_online",
            False,
        )

    gateway.stock_financial_indicators = delayed  # type: ignore[method-assign]
    store = StockFinIndicatorsStore(gateway)

    task1 = asyncio.create_task(store.get_for_ticker("AAPL", market="us", limit=20))
    await first.wait()
    task2 = asyncio.create_task(store.get_for_ticker("AAPL", market="us", limit=20))
    release.set()

    result1, result2 = await asyncio.gather(task1, task2)
    cached = await store.get_for_ticker("AAPL", market="us", limit=20)

    assert result1.as_of == "2026-03-31"
    assert result2.as_of == "2026-03-31"
    assert cached.as_of == "2026-03-31"
    assert gateway.calls == [
        (
            "stock_financial_indicators",
            ("us", "AAPL"),
            {"report_type": "quarter", "limit": 20},
        )
    ]


@pytest.mark.asyncio
async def test_income_store_reuses_cached_response_and_singleflight() -> None:
    gateway = StubGateway()
    first = asyncio.Event()
    release = asyncio.Event()

    async def delayed(*args: Any, **kwargs: Any) -> GatewayResult[list[dict]]:
        gateway.calls.append(("stock_income", args, kwargs))
        first.set()
        await release.wait()
        return GatewayResult(
            [{"report_date": "2026-03-31 00:00:00", "item_name": "总计", "main_business_income": 1, "mbi_ratio": 1, "mainop_type": 2}],
            None,
            "sdk_online",
            False,
        )

    gateway.stock_income = delayed  # type: ignore[method-assign]
    store = StockIncomeStore(gateway)

    task1 = asyncio.create_task(store.get_for_ticker("AAPL", market="us", page_size=100))
    await first.wait()
    task2 = asyncio.create_task(store.get_for_ticker("AAPL", market="us", page_size=100))
    release.set()

    result1, result2 = await asyncio.gather(task1, task2)
    cached = await store.get_for_ticker("AAPL", market="us", page_size=100)

    assert result1.report_date == "2026-03-31 00:00:00"
    assert result2.report_date == "2026-03-31 00:00:00"
    assert cached.report_date == "2026-03-31 00:00:00"
    assert gateway.calls == [("stock_income", ("us", "AAPL"), {"page": 1, "page_size": 100})]
