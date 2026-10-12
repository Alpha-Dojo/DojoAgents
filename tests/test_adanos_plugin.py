from pathlib import Path

import httpx
import pytest

from dojoagents.plugins.registry import DojoPluginRegistry


def load_plugin():
    registry = DojoPluginRegistry()
    registry._scan_directory(Path(__file__).parents[1] / "dojoagents/plugins/built_in", source="built_in")
    return registry.contribution_snapshot().tools


def test_disabled_without_credentials(monkeypatch):
    monkeypatch.delenv("ADANOS_API_KEY", raising=False)
    assert not any(tool.name == "adanos_sentiment" for tool in load_plugin())


@pytest.fixture
def tool(monkeypatch):
    monkeypatch.setenv("ADANOS_API_KEY", "test-placeholder")
    return next(tool for tool in load_plugin() if tool.name == "adanos_sentiment")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,path",
    [
        ("reddit_stocks", "/reddit/stocks/v1/stock/AAPL"),
        ("reddit_crypto", "/reddit/crypto/v1/token/BTC"),
        ("x_stocks", "/x/stocks/v1/stock/AAPL"),
        ("news_stocks", "/news/stocks/v1/stock/AAPL"),
        ("polymarket_stocks", "/polymarket/stocks/v1/stock/AAPL"),
    ],
)
async def test_asset_request(tool, monkeypatch, source, path):
    client = httpx.AsyncClient

    def respond(request):
        assert request.url.host == "api.adanos.org"
        assert request.url.path == path
        assert dict(request.url.params) == {"from": "2026-10-01", "to": "2026-10-02"}
        assert request.headers["X-API-Key"] == "test-placeholder"
        return httpx.Response(200, json={"sentiment_score": 0.25})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client(transport=httpx.MockTransport(respond), **kw))
    result = await tool.handler({"source": source, "operation": "asset", "asset": "BTC" if source == "reddit_crypto" else "AAPL", "from": "2026-10-01", "to": "2026-10-02"})
    assert result["data"] == {"sentiment_score": 0.25}
    assert result["source"] == source


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source,operation,args,path,params",
    [
        ("reddit_stocks", "trending", {"limit": 5}, "/reddit/stocks/v1/trending", {"limit": "5"}),
        ("reddit_crypto", "compare", {"assets": ["BTC", "ETH"]}, "/reddit/crypto/v1/compare", {"symbols": "BTC,ETH"}),
        ("news_stocks", "compare", {"assets": ["BRK", "ABX.DE"]}, "/news/stocks/v1/compare", {"tickers": "BRK,ABX.DE"}),
        ("x_stocks", "market", {}, "/x/stocks/v1/market-sentiment", {}),
    ],
)
async def test_other_operations(tool, monkeypatch, source, operation, args, path, params):
    client = httpx.AsyncClient

    def respond(request):
        assert request.url.path == path
        assert dict(request.url.params) == params
        return httpx.Response(200, json={"items": []})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client(transport=httpx.MockTransport(respond), **kw))
    assert (await tool.handler({"source": source, "operation": operation, **args}))["data"] == {"items": []}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "args",
    [
        {"source": "news_crypto", "operation": "asset", "asset": "BTC"},
        {"source": "reddit_stocks", "operation": "asset", "asset": "../stats"},
        {"source": "reddit_stocks", "operation": "asset"},
        {"source": "reddit_stocks", "operation": "compare", "assets": []},
        {"source": "reddit_stocks", "operation": "trending", "limit": 101},
        {"source": "reddit_stocks", "operation": "market", "from": "2026-10-03", "to": "2026-10-01"},
        {"source": "reddit_stocks", "operation": "market", "days": 7},
    ],
)
async def test_invalid_inputs_do_not_connect(tool, monkeypatch, args):
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: pytest.fail("invalid request reached transport"))
    assert "error" in await tool.handler(args)


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [401, 403, 429, 500])
async def test_error_has_status_without_response_body(tool, monkeypatch, status):
    client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client(transport=httpx.MockTransport(lambda request: httpx.Response(status, text="private-provider-detail")), **kw))
    result = await tool.handler({"source": "reddit_stocks", "operation": "market"})
    assert result == {"error": f"Adanos request failed (HTTP {status}); check API access and quota.", "status": status}


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "json"])
async def test_transport_and_non_json_errors(tool, monkeypatch, failure):
    client = httpx.AsyncClient

    def respond(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("private-provider-detail", request=request)
        return httpx.Response(200, text="not-json")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: client(transport=httpx.MockTransport(respond), **kw))
    result = await tool.handler({"source": "reddit_stocks", "operation": "market"})
    assert "error" in result
    assert "private-provider-detail" not in str(result)
