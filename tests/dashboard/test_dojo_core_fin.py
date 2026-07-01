from __future__ import annotations

import pytest

from dojoagents.dashboard.schemas.stock_fin_indicators import CoreTickerFinIndicatorsResponse
from dojoagents.dashboard.schemas.stock_income import (
    CoreIncomeDistributionItem,
    CoreIncomeDistributionSlice,
    CoreTickerIncomeResponse,
)
from dojoagents.dashboard.services.dojo_data_gateway import GatewayResult
from dojoagents.dashboard.services.dojo_core_fin import (
    resolve_fin_indicators_for_market,
    resolve_income_for_market,
)
from dojoagents.dashboard.services.forex_store import ForexStore


class StubForexGateway:
    def __init__(self, bars: list[dict] | dict[str, list[dict]]) -> None:
        self.bars_by_symbol = bars if isinstance(bars, dict) else {"USDCNY": bars}

    async def forex(self, symbol: str, **kwargs):
        return GatewayResult(self.bars_by_symbol.get(symbol, []), None, "sdk_online", False)


@pytest.mark.asyncio
async def test_convert_fin_rows_fetches_usdcny_for_cny_reports():
    from dojoagents.dashboard.services.dojo_data_gateway import GatewayResult
    from dojoagents.dashboard.services.forex_store import ForexStore

    class RecordingForexGateway:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        async def forex(self, symbol: str, **kwargs):
            self.calls.append((symbol, kwargs))
            return GatewayResult(
                [
                    {"bar_time": "2026-01-15", "close": 7.0},
                    {"bar_time": "2026-02-15", "close": 7.2},
                    {"bar_time": "2026-03-15", "close": 7.4},
                ],
                None,
                "sdk_online",
                False,
            )

    gateway = RecordingForexGateway()
    store = ForexStore(client=gateway)
    rows = [
        {
            "currency": "CNY",
            "report_date": "2026-03-31 00:00:00",
            "std_report_date": "2026-03-31 00:00:00",
            "total_operating_revenue": 32_080_000_000,
            "net_profit_attr_parent": 3_445_000_000,
        }
    ]

    converted = await store.convert_fin_rows_to_market(rows, market="us")

    assert gateway.calls
    assert {call[0] for call in gateway.calls} == {"HKDCNY", "HKDUSD", "USDCNY"}
    assert converted[0]["currency"] == "USD"
    avg_rate = (7.0 + 7.2 + 7.4) / 3
    assert converted[0]["total_operating_revenue"] == pytest.approx(32_080_000_000 / avg_rate)


@pytest.mark.asyncio
async def test_resolve_fin_indicators_converts_cny_to_usd_for_us_listing():
    bars = [
        {"bar_time": "2026-01-15", "close": 7.0},
        {"bar_time": "2026-02-15", "close": 7.2},
        {"bar_time": "2026-03-15", "close": 7.4},
    ]
    forex_store = ForexStore(client=StubForexGateway(bars))
    response = CoreTickerFinIndicatorsResponse(
        ticker="BIDU",
        market="us",
        report_type="quarter",
        source="sdk_online",
        items=[
            {
                "currency": "CNY",
                "report_date": "2026-03-31",
                "std_report_date": "2026-03-31",
                "total_operating_revenue": 34_450_000_000,
                "net_profit_attr_parent": 3_445_000_000,
            }
        ],
    )

    converted = await resolve_fin_indicators_for_market(response, forex_store=forex_store)

    assert converted.items[0]["currency"] == "USD"
    avg_rate = (7.0 + 7.2 + 7.4) / 3
    assert converted.items[0]["total_operating_revenue"] == pytest.approx(34_450_000_000 / avg_rate)


@pytest.mark.asyncio
async def test_resolve_fin_indicators_converts_cny_to_hkd_for_hk_listing():
    forex_store = ForexStore(
        client=StubForexGateway(
            {
                "HKDCNY": [
                    {"bar_time": "2026-01-15", "close": 0.90},
                    {"bar_time": "2026-02-15", "close": 0.91},
                    {"bar_time": "2026-03-15", "close": 0.92},
                ],
                "USDCNY": [
                    {"bar_time": "2026-01-15", "close": 7.0},
                    {"bar_time": "2026-03-15", "close": 7.4},
                ],
                "HKDUSD": [
                    {"bar_time": "2026-01-15", "close": 0.128},
                    {"bar_time": "2026-03-15", "close": 0.129},
                ],
            }
        )
    )
    response = CoreTickerFinIndicatorsResponse(
        ticker="9888",
        market="hk",
        report_type="accumulate",
        source="sdk_online",
        items=[
            {
                "currency": "CNY",
                "report_date": "2026-03-31",
                "std_report_date": "2026-03-31",
                "total_operating_revenue": 32_880_000_000,
                "net_profit_attr_parent": 3_445_000_000,
            }
        ],
    )

    converted = await resolve_fin_indicators_for_market(response, forex_store=forex_store)

    assert converted.items[0]["currency"] == "HKD"
    avg_hkdcny = (0.90 + 0.91 + 0.92) / 3
    assert converted.items[0]["total_operating_revenue"] == pytest.approx(32_880_000_000 / avg_hkdcny)
    assert converted.items[0]["net_profit_attr_parent"] == pytest.approx(3_445_000_000 / avg_hkdcny)


@pytest.mark.asyncio
async def test_convert_fin_rows_triangulates_cny_to_hkd_when_hkdcny_unavailable():
    class SymbolForexGateway:
        async def forex(self, symbol: str, **kwargs):
            if symbol == "HKDCNY":
                return GatewayResult([], None, "sdk_online", False)
            if symbol == "USDCNY":
                return GatewayResult(
                    [
                        {"bar_time": "2026-01-15", "close": 7.0},
                        {"bar_time": "2026-03-15", "close": 7.4},
                    ],
                    None,
                    "sdk_online",
                    False,
                )
            if symbol == "HKDUSD":
                return GatewayResult(
                    [
                        {"bar_time": "2026-01-15", "close": 0.128},
                        {"bar_time": "2026-03-15", "close": 0.129},
                    ],
                    None,
                    "sdk_online",
                    False,
                )
            return GatewayResult([], None, "sdk_online", False)

    store = ForexStore(client=SymbolForexGateway())
    rows = [
        {
            "currency": "CNY",
            "report_date": "2026-03-31 00:00:00",
            "std_report_date": "2026-03-31 00:00:00",
            "total_operating_revenue": 32_880_000_000,
        }
    ]

    converted = await store.convert_fin_rows_to_market(rows, market="hk")

    avg_usdcny = (7.0 + 7.4) / 2
    avg_hkdusd = (0.128 + 0.129) / 2
    expected_factor = (1.0 / avg_usdcny) / avg_hkdusd
    assert converted[0]["currency"] == "HKD"
    assert converted[0]["total_operating_revenue"] == pytest.approx(32_880_000_000 * expected_factor)


@pytest.mark.asyncio
async def test_resolve_income_converts_using_fin_row_currency():
    bars = [
        {"bar_time": "2026-01-15", "close": 7.0},
        {"bar_time": "2026-03-15", "close": 7.4},
    ]
    forex_store = ForexStore(client=StubForexGateway(bars))
    income = CoreTickerIncomeResponse(
        ticker="BIDU",
        market="us",
        report_date="2026-03-31",
        source="sdk_online",
        distributions=[
            CoreIncomeDistributionSlice(
                mainop_type="2",
                report_date="2026-03-31",
                items=[
                    CoreIncomeDistributionItem(
                        item_name="Online Marketing",
                        main_business_income=20_000_000_000,
                        mbi_ratio=0.62,
                    )
                ],
            )
        ],
    )
    fin_rows = [{"currency": "CNY", "report_date": "2026-03-31", "std_report_date": "2026-03-31"}]

    converted = await resolve_income_for_market(
        income,
        forex_store=forex_store,
        fin_rows=fin_rows,
        market="us",
    )

    avg_rate = (7.0 + 7.4) / 2
    assert converted.distributions[0].items[0].main_business_income == pytest.approx(20_000_000_000 / avg_rate)
