import pytest
from unittest.mock import AsyncMock, MagicMock
from dojoagents.dashboard.services.forex_store import ForexStore


@pytest.mark.asyncio
async def test_convert_fin_rows_to_market_usd_cny():
    mock_client = MagicMock()
    mock_client.forex = MagicMock()
    mock_client.forex.kline = AsyncMock(
        return_value={
            "data": [
                {"bar_time": "2025-01-15T00:00:00Z", "close": 7.2},
                {"bar_time": "2025-02-15T00:00:00Z", "close": 7.1},
            ]
        }
    )

    store = ForexStore(client=mock_client)

    rows = [
        {
            "currency": "USD",
            "report_date": "2025-03-31T00:00:00Z",
            "total_operating_revenue": 100,
        }
    ]

    converted = await store.convert_fin_rows_to_market(rows, market="sh")

    assert len(converted) == 1
    assert converted[0]["currency"] == "CNY"
    # Average of 7.2 and 7.1 is 7.15. 100 * 7.15 = 715
    assert converted[0]["total_operating_revenue"] == 715.0


@pytest.mark.asyncio
async def test_convert_caches_results():
    mock_client = MagicMock()
    mock_client.forex = MagicMock()
    mock_client.forex.kline = AsyncMock(
        return_value={
            "data": [
                {"bar_time": "2025-01-15T00:00:00Z", "close": 7.2},
                {"bar_time": "2025-02-15T00:00:00Z", "close": 7.1},
            ]
        }
    )

    store = ForexStore(client=mock_client)

    rows = [
        {
            "currency": "USD",
            "report_date": "2025-03-31T00:00:00Z",
            "total_operating_revenue": 100,
        }
    ]

    # First call
    await store.convert_fin_rows_to_market(rows, market="sh")
    calls_after_first = mock_client.forex.kline.call_count

    # Second call should not trigger another fetch
    await store.convert_fin_rows_to_market(rows, market="sh")
    assert mock_client.forex.kline.call_count == calls_after_first


@pytest.mark.asyncio
async def test_convert_fin_rows_uses_fallback_rate_when_historical_window_missing():
    class WindowForexGateway:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        async def forex(self, symbol: str, **kwargs):
            self.calls.append((symbol, kwargs))
            return {
                "data": [
                    {"bar_time": "2026-01-15", "close": 7.0},
                    {"bar_time": "2026-02-15", "close": 7.2},
                    {"bar_time": "2026-03-15", "close": 7.4},
                ]
            }

    gateway = WindowForexGateway()
    store = ForexStore(client=gateway)
    rows = [
        {
            "currency": "CNY",
            "report_date": "2024-03-31 00:00:00",
            "std_report_date": "2024-03-31 00:00:00",
            "total_operating_revenue": 24_765_200_000,
        },
        {
            "currency": "CNY",
            "report_date": "2025-03-31 00:00:00",
            "std_report_date": "2025-03-31 00:00:00",
            "total_operating_revenue": 24_765_200_000,
        },
    ]

    converted = await store.convert_fin_rows_to_market(rows, market="us")

    assert converted[0]["currency"] == "USD"
    assert converted[1]["currency"] == "USD"
    avg_rate = (7.0 + 7.2 + 7.4) / 3
    assert converted[0]["total_operating_revenue"] == pytest.approx(24_765_200_000 / avg_rate)
    assert converted[1]["total_operating_revenue"] == pytest.approx(24_765_200_000 / avg_rate)
