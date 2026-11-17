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
async def test_web_search_tavily_adapter_parses_results(monkeypatch):
    from dojoagents.tools import web_searcher

    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.tavily.com/search"
        assert request.headers.get("authorization") == "Bearer tvly-test"
        body = request.read()
        import json

        payload = json.loads(body.decode("utf-8"))
        assert payload["query"] == "dojo"
        assert payload["max_results"] == 2
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Tavily Dojo",
                        "url": "https://example.com/tavily",
                        "content": "Tavily snippet",
                    }
                ]
            },
        )

    def fake_client_factory(cfg, **kwargs):
        return _mock_async_client(web_searcher, cfg, handler, **kwargs)

    monkeypatch.setattr(web_searcher, "_make_async_client", fake_client_factory)

    executor = _make_executor(
        {
            "tools": {
                "web": {
                    "search_backend": "tavily",
                    "api_key": "tvly-test",
                }
            }
        }
    )
    result = await executor.execute_one(
        ToolCall(id="call-1", name="web_search", arguments={"query": "dojo", "limit": 2})
    )

    assert result.ok is True
    assert result.metadata["backend"] == "tavily"
    assert result.data["web"][0]["title"] == "Tavily Dojo"
    assert result.data["web"][0]["description"] == "Tavily snippet"


@pytest.mark.asyncio
async def test_web_search_tavily_without_api_key_returns_error():
    executor = _make_executor({"tools": {"web": {"search_backend": "tavily"}}})
    result = await executor.execute_one(ToolCall(id="call-1", name="web_search", arguments={"query": "dojo"}))

    assert result.ok is False
    assert "api key" in result.error.lower()


@pytest.mark.asyncio
async def test_web_search_serply_adapter_parses_results(monkeypatch):
    from dojoagents.tools import web_searcher

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/v1/search"
        assert request.url.host == "api.serply.io"
        assert request.url.params["q"] == "dojo"
        assert request.url.params["num"] == "1"
        assert request.headers.get("x-api-key") == "serply-test"
        assert request.headers.get("user-agent", "").startswith("DojoAgents/")
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "Serply Dojo",
                        "link": "https://example.com/serply",
                        "description": "Serply snippet",
                    },
                    {
                        "title": "Second",
                        "link": "https://example.com/second",
                        "description": "Second snippet",
                    },
                ]
            },
        )

    def fake_client_factory(cfg, **kwargs):
        return _mock_async_client(web_searcher, cfg, handler, **kwargs)

    monkeypatch.setattr(web_searcher, "_make_async_client", fake_client_factory)

    executor = _make_executor({"tools": {"web": {"search_backend": "serply", "api_key": "serply-test"}}})
    result = await executor.execute_one(
        ToolCall(id="call-1", name="web_search", arguments={"query": "dojo", "limit": 1})
    )

    assert result.ok is True
    assert result.metadata["backend"] == "serply"
    assert len(result.data["web"]) == 1
    assert result.data["web"][0]["title"] == "Serply Dojo"
    assert result.data["web"][0]["url"] == "https://example.com/serply"
    assert result.data["web"][0]["description"] == "Serply snippet"


@pytest.mark.asyncio
async def test_web_search_serply_caps_num_at_ten(monkeypatch):
    from dojoagents.tools import web_searcher

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["num"] == "10"
        return httpx.Response(200, json={"results": []})

    def fake_client_factory(cfg, **kwargs):
        return _mock_async_client(web_searcher, cfg, handler, **kwargs)

    monkeypatch.setattr(web_searcher, "_make_async_client", fake_client_factory)

    executor = _make_executor({"tools": {"web": {"search_backend": "serply", "api_key": "serply-test"}}})
    result = await executor.execute_one(
        ToolCall(id="call-1", name="web_search", arguments={"query": "dojo", "limit": 25})
    )

    assert result.ok is True
    assert result.data["web"] == []


@pytest.mark.asyncio
async def test_web_search_serply_rejected_key_returns_error(monkeypatch):
    from dojoagents.tools import web_searcher

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"detail": "Invalid API key"})

    def fake_client_factory(cfg, **kwargs):
        return _mock_async_client(web_searcher, cfg, handler, **kwargs)

    monkeypatch.setattr(web_searcher, "_make_async_client", fake_client_factory)

    executor = _make_executor({"tools": {"web": {"search_backend": "serply", "api_key": "bad-key"}}})
    result = await executor.execute_one(
        ToolCall(id="call-1", name="web_search", arguments={"query": "dojo"})
    )

    assert result.ok is False
    assert "401" in result.error


@pytest.mark.asyncio
async def test_web_search_serply_without_api_key_returns_error():
    executor = _make_executor({"tools": {"web": {"search_backend": "serply"}}})
    result = await executor.execute_one(
        ToolCall(id="call-1", name="web_search", arguments={"query": "dojo"})
    )

    assert result.ok is False
    assert "api key" in result.error.lower()


@pytest.mark.asyncio
async def test_web_extract_tavily_adapter_parses_results(monkeypatch):
    from dojoagents.tools import web_searcher

    async def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.tavily.com/extract"
        assert request.headers.get("authorization") == "Bearer tvly-test"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://example.com/page",
                        "title": "Extracted",
                        "raw_content": "Full page content",
                    }
                ],
                "failed_results": [],
            },
        )

    def fake_client_factory(cfg, **kwargs):
        return _mock_async_client(web_searcher, cfg, handler, **kwargs)

    monkeypatch.setattr(web_searcher, "_make_async_client", fake_client_factory)

    executor = _make_executor(
        {
            "tools": {
                "web": {
                    "extract_backend": "tavily",
                    "api_key": "tvly-test",
                }
            }
        }
    )
    result = await executor.execute_one(
        ToolCall(id="call-1", name="web_extract", arguments={"url": "https://example.com/page"})
    )

    assert result.ok is True
    assert result.metadata["backend"] == "tavily"
    assert result.data["results"][0]["title"] == "Extracted"
    assert result.data["results"][0]["content"] == "Full page content"


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


@pytest.mark.anyio
@pytest.mark.parametrize("user_agent", [None, "DojoAgents-Custom/1.0"])
@pytest.mark.parametrize("text_only", [False, True])
async def test_parallel_mcp_transport_and_result(monkeypatch, user_agent, text_only):
    import json
    from dojoagents.tools import web_searcher

    seen = []
    payload = {"results": [
        {"title": "AnyIO", "url": "https://anyio.readthedocs.io/", "excerpts": ["First", "Second"]},
        {"url": "https://example.org/", "excerpts": ["Other"]},
    ]}

    async def handler(request):
        seen.append(request)
        assert request.headers["user-agent"] == (user_agent or web_searcher._default_user_agent())
        assert "authorization" not in request.headers
        if request.method == "GET":
            return httpx.Response(405)
        if request.method == "DELETE":
            return httpx.Response(200)
        body = json.loads(request.content)
        method = body["method"]
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "initialize":
            result = {"protocolVersion": body["params"]["protocolVersion"], "capabilities": {},
                      "serverInfo": {"name": "fixture", "version": "1"}}
        elif method == "tools/list":
            result = {"tools": [{"name": "web_search", "inputSchema": {"type": "object"}}]}
        else:
            assert method == "tools/call"
            assert body["params"]["name"] == "web_search"
            assert body["params"]["arguments"] == {"objective": "AnyIO tasks", "search_queries": ["AnyIO tasks"]}
            result = {"content": [{"type": "text", "text": json.dumps(payload)}]}
            if not text_only:
                result["structuredContent"] = payload
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result},
                              headers={"mcp-session-id": "fixture-session"})

    factory = web_searcher._make_async_client
    monkeypatch.setattr(web_searcher, "_make_async_client", lambda cfg, **kw: factory(
        cfg, transport=httpx.MockTransport(handler), **kw))
    executor = _make_executor({"tools": {"web": {"search_backend": "parallel", "user_agent": user_agent}}})
    result = await executor.execute_one(ToolCall(id="parallel", name="web_search", arguments={"query": "AnyIO tasks", "limit": 1}))
    assert result.ok, result.error
    assert result.metadata["backend"] == "parallel"
    assert result.data["web"] == [{"title": "AnyIO", "url": "https://anyio.readthedocs.io/",
                                   "description": "First\nSecond", "position": 1}]
    assert {r.method for r in seen} == {"POST", "GET", "DELETE"}
    assert {json.loads(r.content)["method"] for r in seen if r.method == "POST"} == {
        "initialize", "notifications/initialized", "tools/list", "tools/call"}


@pytest.mark.anyio
@pytest.mark.parametrize("error_kind", ["tool", "malformed", "http", "missing_tool"])
async def test_parallel_errors_do_not_fall_back(monkeypatch, error_kind):
    import json
    from dojoagents.tools import web_searcher

    async def handler(request):
        assert request.url.host == "mcp.parallel.ai"
        assert request.headers["authorization"] == "Bearer explicit-key"
        if error_kind == "http":
            return httpx.Response(401)
        body = json.loads(request.content)
        method = body["method"]
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "initialize":
            result = {"protocolVersion": body["params"]["protocolVersion"], "capabilities": {},
                      "serverInfo": {"name": "fixture", "version": "1"}}
        elif method == "tools/list":
            result = {"tools": [] if error_kind == "missing_tool" else [
                {"name": "web_search", "inputSchema": {"type": "object"}}]}
        else:
            result = {"isError": error_kind == "tool", "content": [{"type": "text", "text": "unavailable"}]}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    factory = web_searcher._make_async_client
    monkeypatch.setattr(web_searcher, "_make_async_client", lambda cfg, **kw: factory(
        cfg, transport=httpx.MockTransport(handler), **kw))
    executor = _make_executor({"tools": {"web": {"search_backend": "parallel", "api_key": "explicit-key"}}})
    result = await executor.execute_one(ToolCall(id="error", name="web_search", arguments={"query": "AnyIO"}))
    assert not result.ok
    assert result.error


@pytest.mark.anyio
async def test_parallel_explicit_missing_key_env_does_not_use_anonymous(monkeypatch):
    from dojoagents.tools import web_searcher

    monkeypatch.delenv("DOJO_TEST_MISSING_PARALLEL_KEY", raising=False)
    def unexpected_client(*args, **kwargs):
        pytest.fail("Missing explicit credential must fail before network I/O")
    monkeypatch.setattr(web_searcher, "_make_async_client", unexpected_client)
    executor = _make_executor({"tools": {"web": {"search_backend": "parallel", "api_key_env": "DOJO_TEST_MISSING_PARALLEL_KEY"}}})
    result = await executor.execute_one(ToolCall(id="key", name="web_search", arguments={"query": "AnyIO"}))
    assert not result.ok
    assert "API key" in result.error


def test_parallel_saved_config_preserves_defaults_and_extract(tmp_path):
    from dojoagents.config.loader import ConfigStore

    store = ConfigStore(tmp_path / "agents.yaml")
    assert store.snapshot().tools.web.search_backend == "ddgs"
    store.save_raw({"tools": {"web": {"search_backend": "parallel"}}})
    assert store.snapshot().tools.web.search_backend == "parallel"
    assert store.snapshot().tools.web.extract_backend == "fetch"
    store.save_raw({"tools": {"web": {"search_backend": None}}})
    assert store.snapshot().tools.web.search_backend is None


@pytest.mark.anyio
async def test_parallel_tool_permission_checked_before_network(monkeypatch):
    from dojoagents.tools import web_searcher

    def deny(self, tool_name):
        raise PermissionError("web search denied")
    def unexpected_client(*args, **kwargs):
        pytest.fail("Denied tool must not perform network I/O")
    monkeypatch.setattr(web_searcher, "_make_async_client", unexpected_client)
    executor = _make_executor({"tools": {"web": {"search_backend": "parallel"}}})
    monkeypatch.setattr(SandboxPolicy, "check_tool", deny)
    result = await executor.execute_one(ToolCall(id="denied", name="web_search", arguments={"query": "AnyIO"}))
    assert not result.ok
    assert "denied" in result.error


@pytest.mark.anyio
async def test_parallel_timeout_preserves_executor_boundary(monkeypatch):
    import anyio
    import json
    from dojoagents.tools import web_searcher

    async def handler(request):
        body = json.loads(request.content)
        method = body["method"]
        if method == "notifications/initialized":
            return httpx.Response(202)
        if method == "initialize":
            result = {"protocolVersion": body["params"]["protocolVersion"], "capabilities": {},
                      "serverInfo": {"name": "fixture", "version": "1"}}
        elif method == "tools/list":
            result = {"tools": [{"name": "web_search", "inputSchema": {"type": "object"}}]}
        else:
            await anyio.sleep_forever()
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    factory = web_searcher._make_async_client
    monkeypatch.setattr(web_searcher, "_make_async_client", lambda cfg, **kw: factory(
        cfg, transport=httpx.MockTransport(handler), **kw))
    executor = _make_executor({"tools": {"web": {"search_backend": "parallel"}}})
    executor.sandbox = SandboxPolicy(timeout_seconds=0.1)
    result = await executor.execute_one(ToolCall(id="timeout", name="web_search", arguments={"query": "AnyIO"}))
    assert not result.ok
    assert "timed out" in result.error
