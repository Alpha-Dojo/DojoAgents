from __future__ import annotations

import asyncio

import pytest

from dojoagents.harnesses.built_in.financial.services.dojo_data_gateway import (
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
    import pandas as pd

    client = FakeDojo(
        stocks={
            "get_all_klines_with_df": pd.DataFrame(
                [
                    {"symbol": "AAPL", "bar_time": "2026-06-20", "close": 10.0},
                    {"symbol": "MSFT", "bar_time": "2026-06-20", "close": 20.0},
                ]
            )
        }
    )
    gateway = DojoDataGateway(client)

    result = await gateway.stock_all_klines(symbols=[" aapl ", "MSFT"])

    assert list(result.data["symbol"]) == ["AAPL", "MSFT"]
    assert client.stocks.calls == [("get_all_klines_with_df", {})]


@pytest.mark.asyncio
async def test_stock_all_klines_uses_sdk_contract() -> None:
    import pandas as pd

    client = FakeDojo(
        stocks={
            "get_all_klines_with_df": pd.DataFrame(
                [
                    {"symbol": "AAPL", "bar_time": "2026-06-20", "close": 10.0},
                    {"symbol": "MSFT", "bar_time": "2026-06-20", "close": 20.0},
                ]
            )
        }
    )
    gateway = DojoDataGateway(client)

    result = await gateway.stock_all_klines()

    assert list(result.data["symbol"]) == ["AAPL", "MSFT"]
    assert client.stocks.calls == [("get_all_klines_with_df", {})]


@pytest.mark.asyncio
async def test_stock_klines_reuses_symbol_index_without_reloading_bulk() -> None:
    import pandas as pd

    client = FakeDojo(
        stocks={
            "get_all_klines_with_df": pd.DataFrame(
                [
                    {"symbol": "AAPL", "bar_time": "2026-06-20", "close": 10.0},
                    {"symbol": "MSFT", "bar_time": "2026-06-20", "close": 20.0},
                ]
            )
        }
    )
    gateway = DojoDataGateway(client)

    first = await gateway.stock_klines(["AAPL"])
    second = await gateway.stock_klines(["MSFT"])

    assert list(first.data["symbol"]) == ["AAPL"]
    assert list(second.data["symbol"]) == ["MSFT"]
    assert gateway.kline_index_ready is True
    assert client.stocks.calls == [("get_all_klines_with_df", {})]


@pytest.mark.asyncio
async def test_warm_kline_index_builds_lookup_table() -> None:
    import pandas as pd

    client = FakeDojo(
        stocks={
            "get_all_klines_with_df": pd.DataFrame(
                [
                    {"symbol": "AAPL", "bar_time": "2026-06-19", "close": 9.0},
                    {"symbol": "AAPL", "bar_time": "2026-06-20", "close": 10.0},
                    {"symbol": "MSFT", "bar_time": "2026-06-20", "close": 20.0},
                ]
            )
        }
    )
    gateway = DojoDataGateway(client)

    await gateway.warm_kline_index()

    assert gateway.kline_index_ready is True
    assert set(gateway._kline_symbol_index) == {"AAPL", "MSFT"}
    result = await gateway.stock_klines(["AAPL"], limit=1)
    assert len(result.data) == 1
    assert float(result.data.iloc[-1]["close"]) == 10.0
    assert client.stocks.calls == [("get_all_klines_with_df", {})]


@pytest.mark.asyncio
async def test_stock_kline_fetches_each_symbol_and_normalizes_rows() -> None:
    import pandas as pd

    client = FakeDojo(
        stocks={
            "get_all_klines_with_df": pd.DataFrame(
                [
                    {"symbol": "600000", "bar_time": "2026-06-20", "close": 10.0},
                    {"symbol": "000001", "bar_time": "2026-06-20", "close": 10.0},
                ]
            )
        }
    )
    gateway = DojoDataGateway(client)

    result = await gateway.stock_klines(["600000", "000001"])

    assert list(result.data["symbol"]) == ["600000", "000001"]
    assert client.stocks.calls == [("get_all_klines_with_df", {})]


@pytest.mark.asyncio
async def test_stock_klines_falls_back_to_per_symbol_when_missing_from_bulk() -> None:
    import pandas as pd

    client = FakeDojo(
        stocks={
            "get_all_klines_with_df": pd.DataFrame(
                [
                    {"symbol": "AAPL", "bar_time": "2026-06-20", "close": 10.0},
                ]
            ),
            "get_kline": {
                "klines": [
                    {"symbol": "2513.HK", "bar_time": "2026-06-20", "close": 12.0},
                ]
            },
        }
    )
    gateway = DojoDataGateway(client)

    result = await gateway.stock_klines(["AAPL", "2513.HK"], limit=100)

    assert set(result.data["symbol"]) == {"AAPL", "2513.HK"}
    assert client.stocks.calls == [
        ("get_all_klines_with_df", {}),
        ("get_kline", {"symbol": "2513.HK", "limit": 100}),
    ]


@pytest.mark.asyncio
async def test_stock_klines_uses_per_symbol_fetch_for_date_window() -> None:
    import pandas as pd

    client = FakeDojo(
        stocks={
            "get_all_klines_with_df": pd.DataFrame(
                [
                    {"symbol": "0700.HK", "bar_time": "2025-06-20", "close": 10.0},
                ]
            ),
            "get_kline": {
                "klines": [
                    {"symbol": "0700.HK", "bar_time": "2025-01-02", "close": 8.0},
                    {"symbol": "0700.HK", "bar_time": "2026-06-30", "close": 12.0},
                ]
            },
        }
    )
    gateway = DojoDataGateway(client)

    result = await gateway.stock_klines(
        ["0700.HK"],
        start_time="2025-01-01",
        end_time="2026-06-30",
        limit=500,
    )

    assert list(result.data["bar_time"]) == ["2025-01-02", "2026-06-30"]
    assert client.stocks.calls == [
        ("get_kline", {"symbol": "0700.HK", "start_time": "2025-01-01", "end_time": "2026-06-30", "limit": 500}),
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
