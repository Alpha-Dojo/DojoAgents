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
    assert mock_client.forex.kline.call_count == 1

    # Second call should not trigger another fetch
    await store.convert_fin_rows_to_market(rows, market="sh")
    assert mock_client.forex.kline.call_count == 1
