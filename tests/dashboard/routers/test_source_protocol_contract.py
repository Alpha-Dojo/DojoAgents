from __future__ import annotations


def test_source_protocol_openapi_metadata_excludes_agent_gap(financial_client) -> None:
    schema = financial_client.get("/openapi.json").json()

    market_screener = schema["paths"]["/api/v1/market/screener"]["get"]
    assert market_screener["operationId"] == "screen_market_stocks"
    assert market_screener["tags"] == ["macro-market"]

    assert schema["paths"]["/api/v1/portfolio/holdings/batch"]["post"]["operationId"] == "add_portfolio_holdings"
    assert schema["paths"]["/api/v1/portfolio/holdings/metadata"]["post"]["operationId"] == "update_portfolio_holdings_metadata"
    assert "/api/v1/agent/chat" not in schema["paths"]


def test_market_overview_uses_source_protocol_shape(financial_client) -> None:
    body = financial_client.get("/api/v1/market/overview").json()

    assert set(body) >= {"days", "window_start", "window_end", "as_of", "markets", "benchmarks"}
    assert "source" not in body
    assert "stale" not in body
    assert isinstance(body["benchmarks"], dict)
    assert body["markets"]["us"]["market"] == "us"


def test_ticker_endpoints_use_source_protocol_field_names(financial_client) -> None:
    quote = financial_client.get("/api/v1/ticker/quote?ticker=AAPL&market=us").json()
    assert "sector_paths" in quote
    assert "sector_options" not in quote

    financials = financial_client.get("/api/v1/ticker/financials?ticker=AAPL&market=us").json()
    assert "indicators" in financials
    assert "income_distributions" in financials
    assert "items" not in financials
    assert "distributions" not in financials

    news_events = financial_client.get("/api/v1/ticker/news-events?ticker=AAPL&market=us").json()
    assert "news" in news_events
    assert "events" in news_events
    assert "news_items" not in news_events
    assert "event_items" not in news_events

    price_trends = financial_client.get("/api/v1/ticker/price-trends?ticker=AAPL&market=us").json()
    assert "interval" in price_trends
    assert "klines" in price_trends
    assert "pe_band" in price_trends
    assert "bars" not in price_trends
    assert "pe_points" not in price_trends


def test_portfolio_endpoints_use_source_protocol_shape(financial_client) -> None:
    list_body = financial_client.get("/api/v1/portfolio").json()
    assert set(list_body) == {"query", "items"}

    analysis = financial_client.get("/api/v1/portfolio/p1/analysis").json()
    assert "detail" not in analysis
    assert set(analysis) >= {"id", "name", "holdings", "kpis", "nav_by_market"}

    batch = financial_client.post(
        "/api/v1/portfolio/holdings/batch",
        json={"portfolio_id": "p1", "holdings": [{"ticker": "AAPL", "market": "us"}]},
    )
    assert batch.status_code == 200, batch.text

    metadata = financial_client.post(
        "/api/v1/portfolio/holdings/metadata",
        json={"portfolio_id": "p1", "shares_by_ticker": {"AAPL": 10}},
    )
    assert metadata.status_code == 200, metadata.text


def test_market_screener_endpoint_exists(financial_client) -> None:
    response = financial_client.get("/api/v1/market/screener?market=us&limit=5")

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) >= {"days", "market", "window_start", "as_of", "universe_count", "match_count", "items"}
