from __future__ import annotations

import pytest
import httpx

from dojoagents.agent.models import ToolCall
from dojoagents.config.loader import _to_config
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy


def _make_executor(raw_config: dict):
    from dojoagents.tools.web_searcher import get_web_searcher_specs

    config = _to_config(raw_config)
    registry = ToolRegistry()
    for spec in get_web_searcher_specs(config.tools.web):
        registry.register(spec)
    return ToolExecutor(registry, SandboxPolicy(timeout_seconds=2))


@pytest.mark.asyncio
async def test_web_search_returns_metadata_only(monkeypatch):
    from dojoagents import tools as tools_pkg
    from dojoagents.tools import web_searcher

    async def fake_search_backend(backend, query, limit, cfg):
        assert backend == "mock-search"
        assert query == "dojo agents"
        assert limit == 3
        return [
            {
                "title": "Dojo",
                "url": "https://example.com/dojo",
                "description": "Search result",
                "position": 1,
                "content": "raw page content should not leak through search",
            }
        ]

    monkeypatch.setattr(web_searcher, "_search_backend_request", fake_search_backend)

    executor = _make_executor({"tools": {"web": {"search_backend": "mock-search"}}})
    result = await executor.execute_one(ToolCall(id="call-1", name="web_search", arguments={"query": "dojo agents", "limit": 3}))

    assert result.ok is True
    assert result.metadata["backend"] == "mock-search"
    assert result.data["web"][0]["title"] == "Dojo"
    assert "content" not in result.data["web"][0]
    assert tools_pkg is not None


@pytest.mark.asyncio
async def test_web_search_without_backend_returns_typed_error():
    executor = _make_executor({})
    result = await executor.execute_one(ToolCall(id="call-1", name="web_search", arguments={"query": "dojo agents"}))

    assert result.ok is False
    assert "not configured" in result.error.lower()


@pytest.mark.asyncio
async def test_web_search_unknown_backend_returns_clear_error():
    executor = _make_executor({"tools": {"web": {"search_backend": "unknown-backend"}}})
    result = await executor.execute_one(ToolCall(id="call-1", name="web_search", arguments={"query": "dojo agents"}))

    assert result.ok is False
    assert "unknown-backend" in result.error


@pytest.mark.asyncio
async def test_web_extract_blocks_private_urls():
    executor = _make_executor({"tools": {"web": {"extract_backend": "mock-extract"}}})
    result = await executor.execute_one(ToolCall(id="call-1", name="web_extract", arguments={"urls": ["http://127.0.0.1/secrets"]}))

    assert result.ok is False
    assert "blocked" in result.error.lower()


@pytest.mark.asyncio
async def test_web_extract_truncates_long_content(monkeypatch):
    from dojoagents.tools import web_searcher

    async def fake_extract_backend(backend, urls, cfg):
        assert backend == "mock-extract"
        return [
            {
                "url": urls[0],
                "title": "Long page",
                "content": "A" * 400,
            }
        ]

    monkeypatch.setattr(web_searcher, "_extract_backend_request", fake_extract_backend)

    executor = _make_executor(
        {
            "tools": {
                "web": {
                    "extract_backend": "mock-extract",
                    "summary_threshold_chars": 120,
                    "max_summary_chars": 80,
                }
            }
        }
    )
    result = await executor.execute_one(
        ToolCall(
            id="call-1",
            name="web_extract",
            arguments={"urls": ["https://example.com/long"]},
        )
    )

    assert result.ok is True
    assert result.truncated is True
    assert result.metadata["processing_applied"] == "truncate"
    assert len(result.data["results"][0]["content"]) <= 100


@pytest.mark.asyncio
async def test_web_search_uses_registered_backend_adapter():
    from dojoagents.tools import web_searcher

    async def search_adapter(query, limit, cfg):
        return [
            {
                "title": f"Result for {query}",
                "url": "https://example.com/result",
                "description": f"limit={limit}",
            }
        ]

    web_searcher.register_search_backend("unit-search", search_adapter)
    executor = _make_executor({"tools": {"web": {"search_backend": "unit-search"}}})
    result = await executor.execute_one(ToolCall(id="call-1", name="web_search", arguments={"query": "alpha dojo", "limit": 2}))

    assert result.ok is True
    assert result.data["web"][0]["title"] == "Result for alpha dojo"


@pytest.mark.asyncio
async def test_web_extract_uses_registered_backend_adapter():
    from dojoagents.tools import web_searcher

    async def extract_adapter(urls, cfg):
        return [{"url": urls[0], "title": "Extracted", "content": "short content"}]

    web_searcher.register_extract_backend("unit-extract", extract_adapter)
    executor = _make_executor({"tools": {"web": {"extract_backend": "unit-extract"}}})
    result = await executor.execute_one(ToolCall(id="call-1", name="web_extract", arguments={"url": "https://example.com/page"}))

    assert result.ok is True
    assert result.data["results"][0]["title"] == "Extracted"


@pytest.mark.asyncio
async def test_web_search_ddgs_adapter_parses_results(monkeypatch):
    from dojoagents.tools import web_searcher

    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith("https://html.duckduckgo.com/html/")
        assert request.url.params["q"] == "dojo"
        return httpx.Response(
            200,
            text="""
            <html><body>
              <div class="result">
                <a class="result__a" href="https://example.com/dojo">Dojo Result</a>
                <a class="result__snippet">Description here</a>
              </div>
            </body></html>
            """,
            headers={"content-type": "text/html; charset=utf-8"},
        )

    def fake_client_factory(**kwargs):
        transport = httpx.MockTransport(handler)
        return httpx.AsyncClient(transport=transport, **kwargs)

    monkeypatch.setattr(web_searcher, "_make_async_client", fake_client_factory)

    executor = _make_executor({"tools": {"web": {"search_backend": "ddgs"}}})
    result = await executor.execute_one(ToolCall(id="call-1", name="web_search", arguments={"query": "dojo", "limit": 2}))

    assert result.ok is True
    assert result.data["web"][0]["title"] == "Dojo Result"
