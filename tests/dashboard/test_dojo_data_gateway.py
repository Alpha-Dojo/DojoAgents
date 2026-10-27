from __future__ import annotations

import asyncio

import pytest

from dojoagents.dashboard.services.dojo_data_gateway import (
    DojoDataGateway,
    GatewayBadResponseError,
    GatewayTimeoutError,
    GatewayUnavailableError,
    KLINE_QUERY_FIELDS,
)
from tests.dashboard.fakes.fake_dojo import FakeDojo


@pytest.mark.asyncio
async def test_stock_catalog_profile_and_quote_use_sdk_contracts() -> None:
    client = FakeDojo(
        stocks={
            "get_ystock_info": {"stocks": [{"ticker": "AAPL", "market": "us"}]},
            "get_info": {"info": {"ticker": "AAPL", "name": "Apple"}},
            "post_quote": {"quotes": [{"ticker": "AAPL", "last_price": 200.0}]},
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
        ("post_quote", {"body": {"symbols": "AAPL"}}),
    ]


@pytest.mark.asyncio
async def test_realtime_quote_prefers_live_client_and_keeps_kline_client_offline() -> None:
    snapshot = FakeDojo(stocks={"post_quote": {"quotes": [{"ticker": "AAPL", "last_price": 100.0}]}})
    snapshot._online = False
    live = FakeDojo(stocks={"post_quote": {"quotes": [{"ticker": "AAPL", "last_price": 201.0}]}})
    live._online = True

    result = await DojoDataGateway(snapshot, live_client=live).stock_quotes("us", ["AAPL"])

    assert result.data[0]["last_price"] == 201.0
    assert result.source == "sdk_online"
    assert snapshot.stocks.calls == []
    assert live.stocks.calls == [("post_quote", {"body": {"symbols": "AAPL"}})]


@pytest.mark.asyncio
async def test_realtime_quote_falls_back_to_snapshot_and_marks_stale() -> None:
    snapshot = FakeDojo(stocks={"post_quote": {"quotes": [{"ticker": "AAPL", "last_price": 100.0}]}})
    snapshot._online = False
    live = FakeDojo(stocks={"post_quote": ConnectionError("offline")})
    live._online = True

    result = await DojoDataGateway(snapshot, live_client=live).stock_quotes("us", ["AAPL"])

    assert result.data[0]["last_price"] == 100.0
    assert result.source == "sdk_snapshot"
    assert result.stale is True


@pytest.mark.asyncio
async def test_pure_offline_quotes_are_labelled_snapshot_not_online() -> None:
    """A snapshot-only deployment must never report its quotes as live.

    The offline quote payload has no ``source`` field, so the alias default
    used to label it ``sdk_online``. Downstream consumers trust that label to
    decide whether quotes may override the independently published sector
    precompute, so a lagging quote snapshot would win over newer sector data.
    """
    client = FakeDojo(stocks={"post_quote": {"quotes": [{"ticker": "AAPL", "last_price": 100.0}]}})
    client._online = False

    result = await DojoDataGateway(client).stock_quotes("us", ["AAPL"])

    assert result.source == "sdk_snapshot"
    assert result.stale is False


@pytest.mark.asyncio
async def test_offline_quote_overlay_does_not_override_newer_sector_precompute() -> None:
    """End-to-end guard: offline quotes must not shift the sector-movers as-of.

    Reproduces the production wiring where the committed quote snapshot lags
    the sector precompute by one session for the ``us`` market.
    """
    from types import SimpleNamespace

    import pandas as pd

    from dojoagents.dashboard.services.market_window import MarketAnalysisWindow
    from dojoagents.dashboard.services.sector_movers_service import SectorMoversService

    sector_rows = pd.DataFrame(
        [
            {
                "market": "us",
                "scope": "L3",
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "3",
                "daily_return_pct": 7.5,
                "total_market_cap": 500.0,
                "member_count": 5,
            }
        ]
    )

    class Precomputed:
        load_generation = 1

        def resolve_window_bounds(self, window):
            return window.with_resolved_bounds(start="2026-10-08", end="2026-10-08")

        def get_sector_movers_window_frame_for_window(self, _window):
            return sector_rows

    service = SectorMoversService(
        sector_store=SimpleNamespace(
            find_resolved_path=lambda *_args: SimpleNamespace(level3_zh="科技", level3_en="Technology")
        ),
        stock_store=SimpleNamespace(
            quote_source="sdk_snapshot",
            quote_as_of="2026-10-07T16:00:00Z",
        ),
        sector_precomputed_store=Precomputed(),
    )

    response = service.build_market_movers_response(days=1, limit=5, market="us", include_members=False)

    assert response.as_of == "2026-10-08"
    assert response.markets["us"].gainers[0].change_percent == pytest.approx(7.5)


SNAPSHOT = {
    "backend": "huggingface",
    "repo_id": "AlphaDojo/dojo_stock_kline",
    "resolved_revision": "revision-1",
    "snapshot_token": "snapshot-1",
}


@pytest.mark.asyncio
async def test_offline_stock_klines_uses_bounded_batch_and_retains_snapshot() -> None:
    def response(**kwargs):
        return {
            "rows": [
                {"symbol": symbol, "kline_t": "1D", "bar_time": "2026-06-20", "close": 10.0}
                for symbol in kwargs["symbols"]
            ],
            "snapshot": SNAPSHOT,
        }

    client = FakeDojo(stocks={"get_klines": response})
    client._online = False
    gateway = DojoDataGateway(client)

    result = await gateway.stock_klines(
        [" aapl ", "MSFT"],
        start_time="2026-01-01",
        end_time="2026-06-30",
        limit=252,
        price_adj_type="pre",
    )

    assert list(result.data["symbol"]) == ["AAPL", "MSFT"]
    assert result.snapshot == SNAPSHOT
    assert gateway.latest_kline_snapshot == SNAPSHOT
    assert client.stocks.calls == [
        (
            "get_klines",
            {
                "symbols": ["AAPL", "MSFT"],
                "start": "2026-01-01",
                "end": "2026-06-30",
                "fields": KLINE_QUERY_FIELDS,
                "limit_per_symbol": 252,
                "adjust": "pre",
                "kline_t": None,
                "adjustment_reference_date": None,
            },
        )
    ]


@pytest.mark.asyncio
async def test_offline_limit_zero_maps_to_no_per_symbol_limit() -> None:
    client = FakeDojo(stocks={"get_klines": {"rows": [], "snapshot": SNAPSHOT}})
    client._online = False

    result = await DojoDataGateway(client).stock_klines(["AAPL"], limit=0)

    assert result.data.empty
    assert client.stocks.calls[0][1]["limit_per_symbol"] is None
    assert client.stocks.calls[0][1]["adjust"] == "pre"


@pytest.mark.asyncio
async def test_online_stock_klines_uses_adjusted_single_stock_endpoint() -> None:
    client = FakeDojo(
        stocks={
            "get_kline": {
                "data": [
                    {"symbol": "AAA", "bar_time": "2026-01-02", "close": 50.0, "adj_factor_cum": 1.0},
                    {"symbol": "AAA", "bar_time": "2026-01-03", "close": 60.0, "adj_factor_cum": 2.0},
                ]
            }
        }
    )
    client._online = True

    result = await DojoDataGateway(client).stock_klines(
        ["AAA"],
        market="us",
        start_time="2026-01-02",
        end_time="2026-01-03",
        price_adj_type="pre",
        limit=0,
    )

    assert list(result.data["close"]) == [50.0, 60.0]
    assert result.source == "sdk_online"
    assert client.stocks.calls == [
        (
            "get_kline",
            {"symbol": "AAA", "start_time": "2026-01-02", "end_time": "2026-01-03", "price_adj_type": "pre", "limit": 0},
        )
    ]


@pytest.mark.asyncio
async def test_offline_stock_klines_keeps_sdk_adjusted_prices_without_second_adjustment() -> None:
    client = FakeDojo(
        stocks={
            "get_klines": {
                "rows": [
                    {"symbol": "AAA", "bar_time": "2026-01-02", "close": 50.0},
                    {"symbol": "AAA", "bar_time": "2026-01-03", "close": 60.0},
                ],
                "snapshot": SNAPSHOT,
            }
        }
    )
    client._online = False

    result = await DojoDataGateway(client).stock_klines(
        ["AAA"],
        start_time="2026-01-02",
        end_time="2026-01-03",
        price_adj_type="pre",
        limit=0,
    )

    assert list(result.data["bar_time"]) == ["2026-01-02", "2026-01-03"]
    assert list(result.data["close"]) == [50.0, 60.0]
    assert client.stocks.calls[0][0] == "get_klines"
    assert client.stocks.calls[0][1]["adjust"] == "pre"


@pytest.mark.asyncio
async def test_online_stock_klines_sends_full_window_to_single_stock_endpoint() -> None:
    def response(**kwargs):
        return {
            "data": [
                {"symbol": kwargs["symbol"], "bar_time": kwargs["start_time"], "close": 9.0},
                {"symbol": kwargs["symbol"], "bar_time": kwargs["end_time"], "close": 10.0},
            ]
        }

    client = FakeDojo(stocks={"get_kline": response})
    client._online = True

    result = await DojoDataGateway(client).stock_klines(
        ["AAA"],
        start_time="2026-01-01",
        end_time="2026-02-15",
        limit=0,
    )

    assert list(result.data["bar_time"]) == ["2026-01-01", "2026-02-15"]
    assert client.stocks.calls == [("get_kline", {"symbol": "AAA", "start_time": "2026-01-01", "end_time": "2026-02-15", "limit": 0})]


@pytest.mark.asyncio
async def test_online_stock_klines_limits_single_stock_concurrency() -> None:
    class Stocks:
        def __init__(self) -> None:
            self.active = 0
            self.peak = 0

        async def get_kline(self, **kwargs):
            self.active += 1
            self.peak = max(self.peak, self.active)
            await asyncio.sleep(0.01)
            self.active -= 1
            return {"data": [{"symbol": kwargs["symbol"], "bar_time": "2026-01-02", "close": 10.0}]}

    stocks = Stocks()
    client = type("Client", (), {"_online": True, "stocks": stocks})()

    result = await DojoDataGateway(client, kline_max_concurrent=3).stock_klines([f"S{i}" for i in range(8)], limit=0)

    assert set(result.data["symbol"]) == {f"S{i}" for i in range(8)}
    assert stocks.peak == 3


@pytest.mark.asyncio
async def test_online_stock_klines_keeps_successful_symbols_when_one_fails() -> None:
    def response(**kwargs):
        if kwargs["symbol"] == "BAD":
            raise RuntimeError("upstream failed")
        return {"data": [{"symbol": kwargs["symbol"], "bar_time": "2026-01-02", "close": 10.0}]}

    client = FakeDojo(stocks={"get_kline": response})
    client._online = True

    result = await DojoDataGateway(client, kline_max_concurrent=2).stock_klines(["GOOD", "BAD"], limit=0)

    assert list(result.data["symbol"]) == ["GOOD"]


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
