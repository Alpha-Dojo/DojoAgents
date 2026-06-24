from __future__ import annotations

import asyncio

import pytest

from dojoagents.dashboard.services.dojo_data_gateway import (
    DojoDataGateway,
    GatewayBadResponseError,
    GatewayTimeoutError,
    GatewayUnavailableError,
)
from tests.dashboard.fakes.fake_dojo import FakeDojo


@pytest.mark.asyncio
async def test_stock_catalog_profile_and_quote_use_sdk_contracts() -> None:
    client = FakeDojo(
        stocks={
            "get_ystock_info": {"stocks": [{"ticker": "AAPL", "market": "us"}]},
            "get_info": {"info": {"ticker": "AAPL", "name": "Apple"}},
            "get_quote": {"quotes": [{"ticker": "AAPL", "last_price": 200.0}]},
        }
    )
    gateway = DojoDataGateway(client)

    catalog = await gateway.stocks(market="us")
    profile = await gateway.stock_profile("us", " aapl ")
    quotes = await gateway.stock_quotes("us", [" aapl "])

    assert catalog.data == [{"ticker": "AAPL", "market": "us"}]
    assert profile.data == {"ticker": "AAPL", "name": "Apple"}
    assert quotes.data == [{"ticker": "AAPL", "last_price": 200.0}]
    assert client.stocks.calls == [
        ("get_ystock_info", {"market": "us"}),
        ("get_info", {"symbol": "AAPL"}),
        ("get_quote", {"symbols": ["AAPL"]}),
    ]


@pytest.mark.asyncio
async def test_stock_all_klines_accepts_symbols_filter() -> None:
    client = FakeDojo(
        stocks={
            "get_all_klines": [
                {"symbol": "AAPL", "bar_time": "2026-06-20", "close": 10.0},
                {"symbol": "MSFT", "bar_time": "2026-06-20", "close": 20.0},
            ]
        }
    )
    gateway = DojoDataGateway(client)

    result = await gateway.stock_all_klines(symbols=[" aapl ", "MSFT"])

    assert [row["symbol"] for row in result.data] == ["AAPL", "MSFT"]
    assert client.stocks.calls == [("get_all_klines", {"symbols": ["AAPL", "MSFT"]})]


@pytest.mark.asyncio
async def test_stock_all_klines_uses_sdk_contract() -> None:
    client = FakeDojo(
        stocks={
            "get_all_klines": [
                {"symbol": "AAPL", "bar_time": "2026-06-20", "close": 10.0},
                {"symbol": "MSFT", "bar_time": "2026-06-20", "close": 20.0},
            ]
        }
    )
    gateway = DojoDataGateway(client)

    result = await gateway.stock_all_klines()

    assert [row["symbol"] for row in result.data] == ["AAPL", "MSFT"]
    assert client.stocks.calls == [("get_all_klines", {})]


@pytest.mark.asyncio
async def test_stock_kline_fetches_each_symbol_and_normalizes_rows() -> None:
    def klines(symbols: list, **_: object) -> list:
        return [{"symbol": symbol, "bar_time": "2026-06-20", "close": 10.0} for symbol in symbols]

    client = FakeDojo(stocks={"get_all_klines": klines})
    gateway = DojoDataGateway(client)

    result = await gateway.stock_klines(
        "sh",
        ["600000", "000001"],
        start_time="2026-01-01",
        end_time="2026-06-20",
        limit=100,
    )

    assert [row["symbol"] for row in result.data] == ["600000", "000001"]
    assert client.stocks.calls == [
        (
            "get_all_klines",
            {
                "symbols": ["600000", "000001"],
            },
        )
    ]


@pytest.mark.asyncio
async def test_event_news_financial_and_income_use_exact_methods_and_pagination() -> None:
    client = FakeDojo(
        stocks={
            "get_event_remind": {"data": [{"event_date": "2026-06-21"}]},
            "get_news": {"news": [{"publish_time": "2026-06-21"}]},
            "get_fin_indicators": {"data": [{"std_report_date": "2026-03-31"}]},
            "get_main_income": {"data": [{"report_date": "2025-12-31"}]},
        }
    )
    gateway = DojoDataGateway(client)

    events = await gateway.stock_events("us", "aapl", page=2, page_size=7)
    news = await gateway.stock_news("us", "aapl", page=3, page_size=8)
    indicators = await gateway.stock_financial_indicators("us", "aapl", report_type="quarter", limit=9)
    income = await gateway.stock_income("us", "aapl", page=4, page_size=10)

    assert len(events.data) == len(news.data) == len(indicators.data) == len(income.data) == 1
    assert client.stocks.calls == [
        ("get_event_remind", {"symbol": "AAPL", "page": 2, "page_size": 7}),
        ("get_news", {"symbol": "AAPL", "page": 3, "page_size": 8}),
        (
            "get_fin_indicators",
            {"symbol": "AAPL", "report_type": "quarter", "limit": 9},
        ),
        ("get_main_income", {"symbol": "AAPL", "page": 4, "page_size": 10}),
    ]


@pytest.mark.asyncio
async def test_sector_benchmark_and_forex_contracts() -> None:
    client = FakeDojo(
        sectors={
            "get_info": {"sectors": [{"id": 1, "name": "Technology"}]},
            "get_symbol_relations": {"data": [{"symbol": "AAPL"}]},
        },
        benchmark={"get_kline": {"klines": [["2026-06-20", 1, 2, 1, 2]]}},
        forex={"get_kline": {"klines": [["2026-06-20", 7.1, 7.2, 7.0, 7.15]]}},
    )
    gateway = DojoDataGateway(client)

    sectors = await gateway.sector_taxonomy(tree=True)
    relations = await gateway.sector_relations(symbol="AAPL")
    benchmark = await gateway.benchmark_klines("^SPX", limit=20)
    forex = await gateway.forex("USDCNY", limit=30)

    assert sectors.data[0]["name"] == "Technology"
    assert relations.data == [{"symbol": "AAPL"}]
    assert benchmark.data[0][0] == "2026-06-20"
    assert forex.data[0][0] == "2026-06-20"
    assert client.forex.calls == [("get_kline", {"symbol": "USDCNY", "limit": 30})]


@pytest.mark.asyncio
async def test_metadata_is_explicit_and_accepts_snapshot_aliases() -> None:
    client = FakeDojo(
        stocks={
            "get_news": {
                "news": [],
                "as_of": "2026-06-20T08:00:00Z",
                "source": "local",
                "stale": True,
            }
        }
    )

    result = await DojoDataGateway(client).stock_news("us", "AAPL")

    assert result.as_of == "2026-06-20T08:00:00Z"
    assert result.source == "sdk_snapshot"
    assert result.stale is True


@pytest.mark.asyncio
async def test_malformed_envelope_raises_bad_response() -> None:
    client = FakeDojo(stocks={"get_news": {"news": "not-a-list"}})

    with pytest.raises(GatewayBadResponseError, match="stock_news"):
        await DojoDataGateway(client).stock_news("us", "AAPL")


@pytest.mark.asyncio
async def test_timeout_is_classified_without_exposing_sdk_exception() -> None:
    client = FakeDojo(stocks={"get_news": asyncio.TimeoutError("secret upstream detail")})

    with pytest.raises(GatewayTimeoutError, match="stock_news") as error:
        await DojoDataGateway(client).stock_news("us", "AAPL")

    assert "secret upstream detail" not in str(error.value)


@pytest.mark.asyncio
async def test_unavailable_source_is_classified_without_leaking_details() -> None:
    client = FakeDojo(stocks={"get_news": ConnectionError("api-key=secret")})

    with pytest.raises(GatewayUnavailableError, match="stock_news") as error:
        await DojoDataGateway(client).stock_news("us", "AAPL")

    assert "api-key=secret" not in str(error.value)


@pytest.mark.asyncio
async def test_offline_raw_list_envelope_is_supported() -> None:
    client = FakeDojo(stocks={"get_ystock_info": [{"ticker": "AAPL", "market": "us"}]})

    result = await DojoDataGateway(client).stocks(market="us")

    assert result.data == [{"ticker": "AAPL", "market": "us"}]
