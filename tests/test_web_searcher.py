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


def _mock_async_client(web_searcher, cfg, handler, **kwargs):
    transport = httpx.MockTransport(handler)
    headers = dict(kwargs.pop("headers", {}) or {})
    headers.setdefault("User-Agent", web_searcher._resolve_user_agent(cfg))
    return httpx.AsyncClient(
        transport=transport,
        timeout=20.0,
        follow_redirects=True,
        headers=headers,
        **kwargs,
    )


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
    executor = _make_executor({"tools": {"web": {"search_backend": None}}})
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

    def fake_client_factory(cfg, **kwargs):
        transport = httpx.MockTransport(handler)
        return httpx.AsyncClient(transport=transport, **kwargs)

    monkeypatch.setattr(web_searcher, "_make_async_client", fake_client_factory)

    executor = _make_executor({"tools": {"web": {"search_backend": "ddgs"}}})
    result = await executor.execute_one(ToolCall(id="call-1", name="web_search", arguments={"query": "dojo", "limit": 2}))

    assert result.ok is True
    assert result.data["web"][0]["title"] == "Dojo Result"


@pytest.mark.asyncio
async def test_web_extract_fetch_adapter_parses_results(monkeypatch):
    from dojoagents.tools import web_searcher

    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://example.com/page"
        user_agent = request.headers.get("user-agent", "")
        assert user_agent
        assert not user_agent.startswith("python-httpx")
        return httpx.Response(
            200,
            text="""
            <html>
            <head><title>Test Title</title></head>
            <body>
              <p>Hello Dojo Agents</p>
            </body>
            </html>
            """,
            headers={"content-type": "text/html; charset=utf-8"},
        )

    def fake_client_factory(cfg, **kwargs):
        return _mock_async_client(web_searcher, cfg, handler, **kwargs)

    monkeypatch.setattr(web_searcher, "_make_async_client", fake_client_factory)

    executor = _make_executor({"tools": {"web": {"extract_backend": "fetch"}}})
    result = await executor.execute_one(ToolCall(id="call-1", name="web_extract", arguments={"url": "https://example.com/page"}))

    assert result.ok is True
    assert result.data["results"][0]["title"] == "Test Title"
    assert "Hello Dojo Agents" in result.data["results"][0]["content"]


@pytest.mark.asyncio
async def test_web_extract_without_backend_returns_typed_error():
    executor = _make_executor({"tools": {"web": {"extract_backend": None}}})
    result = await executor.execute_one(ToolCall(id="call-1", name="web_extract", arguments={"urls": ["https://example.com/page"]}))

    assert result.ok is False
    assert "not configured" in result.error.lower()


def test_resolve_user_agent_defaults_to_package_identity():
    from dojoagents.config.models import WebToolsConfig
    from dojoagents.tools.web_searcher import _resolve_user_agent

    resolved = _resolve_user_agent(WebToolsConfig())
    assert resolved.startswith("DojoAgents/")
    assert "github.com/Alpha-Dojo/DojoAgents" in resolved


def test_resolve_user_agent_honors_config_override():
    from dojoagents.config.models import WebToolsConfig
    from dojoagents.tools.web_searcher import _resolve_user_agent

    resolved = _resolve_user_agent(WebToolsConfig(user_agent="CustomBot/2.0 (contact@example.com)"))
    assert resolved == "CustomBot/2.0 (contact@example.com)"


@pytest.mark.asyncio
async def test_make_async_client_sets_user_agent_header():
    from dojoagents.config.models import WebToolsConfig
    from dojoagents.tools.web_searcher import _make_async_client

    client = _make_async_client(WebToolsConfig())
    try:
        assert client.headers.get("User-Agent")
        assert "DojoAgents" in client.headers["User-Agent"]
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_web_extract_fetch_adapter_handles_wikipedia_style_ua_policy(monkeypatch):
    from dojoagents.tools import web_searcher

    async def handler(request: httpx.Request) -> httpx.Response:
        user_agent = request.headers.get("user-agent", "")
        if not user_agent or user_agent.startswith("python-httpx"):
            return httpx.Response(
                403,
                text="Please set a user-agent and respect our robot policy",
            )
        return httpx.Response(
            200,
            text="""
            <html>
            <head><title>Nidec - Wikipedia</title></head>
            <body><p>Listed on the Tokyo Stock Exchange in 1977.</p></body>
            </html>
            """,
            headers={"content-type": "text/html; charset=utf-8"},
        )

    def fake_client_factory(cfg, **kwargs):
        return _mock_async_client(web_searcher, cfg, handler, **kwargs)

    monkeypatch.setattr(web_searcher, "_make_async_client", fake_client_factory)

    executor = _make_executor({"tools": {"web": {"extract_backend": "fetch"}}})
    result = await executor.execute_one(
        ToolCall(
            id="call-1",
            name="web_extract",
            arguments={"url": "https://en.wikipedia.org/wiki/Nidec"},
        )
    )

    assert result.ok is True
    assert result.data["results"][0]["error"] is None
    assert result.data["results"][0]["title"] == "Nidec - Wikipedia"
    assert "1977" in result.data["results"][0]["content"]


@pytest.mark.asyncio
async def test_web_extract_fetch_adapter_uses_configured_user_agent(monkeypatch):
    from dojoagents.tools import web_searcher

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers.get("user-agent") == "CustomBot/2.0 (contact@example.com)"
        return httpx.Response(
            200,
            text="<html><head><title>Configured</title></head><body>ok</body></html>",
            headers={"content-type": "text/html; charset=utf-8"},
        )

    def fake_client_factory(cfg, **kwargs):
        return _mock_async_client(web_searcher, cfg, handler, **kwargs)

    monkeypatch.setattr(web_searcher, "_make_async_client", fake_client_factory)

    executor = _make_executor(
        {
            "tools": {
                "web": {
                    "extract_backend": "fetch",
                    "user_agent": "CustomBot/2.0 (contact@example.com)",
                }
            }
        }
    )
    result = await executor.execute_one(
        ToolCall(id="call-1", name="web_extract", arguments={"url": "https://example.com/page"})
    )

    assert result.ok is True
    assert result.data["results"][0]["title"] == "Configured"
