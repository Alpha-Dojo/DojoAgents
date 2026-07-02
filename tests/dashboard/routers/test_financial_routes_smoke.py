from __future__ import annotations

import pytest


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/dojo-core/tickers/search?q=AAPL",
        "/api/v1/dojo-core/ticker/sector?ticker=AAPL&market=us",
        "/api/v1/dojo-core/ticker/quote?ticker=AAPL&market=us",
        "/api/v1/dojo-core/ticker/fin-indicators?ticker=AAPL&market=us",
        "/api/v1/dojo-core/ticker/events?ticker=AAPL&market=us",
        "/api/v1/dojo-core/ticker/news?ticker=AAPL&market=us",
        "/api/v1/dojo-core/ticker/kline?ticker=AAPL&market=us",
        "/api/v1/dojo-core/ticker/income?ticker=AAPL&market=us",
        "/api/v1/dojo-core/ticker/pe-band?ticker=AAPL&market=us",
        "/api/v1/dojo-folio/portfolios",
        "/api/v1/dojo-folio/portfolios/search?q=Primary",
        "/api/v1/dojo-folio/portfolios/p1",
        "/api/v1/dojo-mesh/benchmarks",
        "/api/v1/dojo-mesh/sectors",
        "/api/v1/dojo-mesh/sectors/cross-market?link_key=software",
        "/api/v1/dojo-sphere/sectors/metrics?level1_id=1&level2_id=2&level3_id=3",
        "/api/v1/dojo-sphere/sectors/constituents?level1_id=1&level2_id=2&level3_id=3",
        "/api/v1/dojo-sphere/sectors/performance?level1_id=1&level2_id=2&level3_id=3",
        "/api/v1/dojo-sphere/constituents/kline/stats",
        "/api/v1/dojo-sphere/sectors/kline?level1_id=1&level2_id=2&level3_id=3",
        "/api/v1/dojo-sphere/constituents/kline?symbols=AAPL,MSFT",
        "/api/v1/dojo-sphere/constituents/AAPL/kline",
        "/api/v1/markets/stats",
        "/api/v1/markets/us/stats",
        "/api/v1/sectors/taxonomy",
        "/api/v1/utility/search/company-ticker?q=AAPL",
        "/api/v1/utility/taxonomy/tree",
        "/api/v1/market/overview",
        "/api/v1/market/sector-movers",
        "/api/v1/sector/analysis?level1_id=1&level2_id=2&level3_id=3",
        "/api/v1/sector/constituents?level1_id=1&level2_id=2&level3_id=3&market=cn",
        "/api/v1/portfolio",
        "/api/v1/portfolio/p1/analysis",
        "/api/v1/portfolio/p1/analysis/summary",
        "/api/v1/portfolio/p1/analysis/performance",
    ],
)
def test_financial_get_routes_return_schema_valid_responses(financial_client, path) -> None:
    response = financial_client.get(path)

    assert response.status_code == 200, response.text


@pytest.mark.parametrize(
    ("method", "path", "body", "expected"),
    [
        ("post", "/api/v1/dojo-folio/portfolios", {"name": "Growth"}, 201),
        ("patch", "/api/v1/dojo-folio/portfolios/p1", {"name": "Growth"}, 200),
        ("delete", "/api/v1/dojo-folio/portfolios/p1", None, 204),
        (
            "post",
            "/api/v1/dojo-folio/portfolios/p1/holdings",
            {"ticker": "AAPL", "market": "us"},
            200,
        ),
        ("post", "/api/v1/dojo-folio/portfolios/p1/allocate", {"market": "us"}, 200),
        ("post", "/api/v1/portfolio/manage", {"action": "create", "name": "Growth"}, 200),
        (
            "post",
            "/api/v1/portfolio/holdings",
            {"portfolio_id": "p1", "ticker": "AAPL", "market": "us"},
            200,
        ),
        ("post", "/api/v1/portfolio/allocate", {"portfolio_id": "p1", "market": "us"}, 200),
    ],
)
def test_financial_write_routes_return_contract_status(financial_client, method, path, body, expected) -> None:
    request = getattr(financial_client, method)
    response = request(path) if body is None else request(path, json=body)

    assert response.status_code == expected, response.text
