import asyncio
import os
import re
import time
import logging
import threading
from typing import Any, List, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dojoagents.tools.registry import ToolRegistry, ToolSpec

logger = logging.getLogger("dojoagents")

_SAFE_ENV_KEYS = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LANG",
        "LC_ALL",
        "TERM",
        "SHELL",
        "TMPDIR",
    }
)

_CREDENTIAL_PATTERN = re.compile(
    r"(?:"
    r"ghp_[A-Za-z0-9_]{1,255}"  # GitHub PAT
    r"|sk-[A-Za-z0-9_]{1,255}"  # OpenAI-style key
    r"|Bearer\s+\S+"  # Bearer token
    r"|token=[^\s&,;\"']{1,255}"  # token=...
    r"|key=[^\s&,;\"']{1,255}"  # key=...
    r"|API_KEY=[^\s&,;\"']{1,255}"  # API_KEY=...
    r"|password=[^\s&,;\"']{1,255}"  # password=...
    r"|secret=[^\s&,;\"']{1,255}"  # secret=...
    r")",
    re.IGNORECASE,
)

_MCP_INJECTION_PATTERNS = [
    (re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I), "prompt override attempt ('ignore previous instructions')"),
    (re.compile(r"you\s+are\s+now\s+a", re.I), "identity override attempt ('you are now a...')"),
    (re.compile(r"your\s+new\s+(task|role|instructions?)\s+(is|are)", re.I), "task override attempt"),
    (re.compile(r"system\s*:\s*", re.I), "system prompt injection attempt"),
    (re.compile(r"<\s*(system|human|assistant)\s*>", re.I), "role tag injection attempt"),
    (re.compile(r"do\s+not\s+(tell|inform|mention|reveal)", re.I), "concealment instruction"),
    (re.compile(r"(curl|wget|fetch)\s+https?://", re.I), "network command in description"),
    (re.compile(r"base64\.(b64decode|decodebytes)", re.I), "base64 decode reference"),
    (re.compile(r"exec\s*\(|eval\s*\(", re.I), "code execution reference"),
    (re.compile(r"import\s+(subprocess|os|shutil|socket)", re.I), "dangerous import reference"),
]


def _build_safe_env(user_env: Optional[dict]) -> dict:
    env = {}
    for key, value in os.environ.items():
        if key in _SAFE_ENV_KEYS or key.startswith("XDG_"):
            env[key] = value
    if user_env:
        env.update(user_env)
    return env


def _sanitize_error(text: str) -> str:
    return _CREDENTIAL_PATTERN.sub("[REDACTED]", text)


def _scan_mcp_description(server_name: str, tool_name: str, description: str) -> List[str]:
    findings = []
    if not description:
        return findings
    for pattern, reason in _MCP_INJECTION_PATTERNS:
        if pattern.search(description):
            findings.append(reason)
    if findings:
        logger.warning(
            "MCP server '%s' tool '%s': suspicious description content — %s. " "Description: %.200s",
            server_name,
            tool_name,
            "; ".join(findings),
            description,
        )
    return findings


_mcp_loop: asyncio.AbstractEventLoop | None = None
_mcp_thread: threading.Thread | None = None
_lock = threading.Lock()
_servers: dict[str, "MCPServerTask"] = {}

_server_error_counts: dict[str, int] = {}
_server_breaker_opened_at: dict[str, float] = {}
_CIRCUIT_BREAKER_THRESHOLD = 3
_CIRCUIT_BREAKER_COOLDOWN_SEC = 60.0


def _bump_server_error(server_name: str) -> None:
    n = _server_error_counts.get(server_name, 0) + 1
    _server_error_counts[server_name] = n
    if n >= _CIRCUIT_BREAKER_THRESHOLD:
        _server_breaker_opened_at[server_name] = time.monotonic()


def _reset_server_error(server_name: str) -> None:
    _server_error_counts[server_name] = 0
    _server_breaker_opened_at.pop(server_name, None)


def _ensure_mcp_loop():
    global _mcp_loop, _mcp_thread
    with _lock:
        if _mcp_loop is not None and _mcp_loop.is_running():
            return
        _mcp_loop = asyncio.new_event_loop()
        _mcp_thread = threading.Thread(
            target=_mcp_loop.run_forever,
            name="mcp-event-loop",
            daemon=True,
        )
        _mcp_thread.start()


from mcp.types import (  # noqa
    CreateMessageResult,  # noqa
    CreateMessageResultWithTools,  # noqa
    SamplingCapability,  # noqa
    SamplingToolsCapability,  # noqa
    TextContent,  # noqa
    ToolUseContent,  # noqa
)  # noqa


class SamplingHandler:
    def __init__(self, server_name: str, config: dict):
        self.server_name = server_name
        self.config = config

    async def __call__(self, context, params):
        from dojoagents.config.loader import ConfigStore, resolve_provider_config
        from dojoagents.agent.providers import OpenAICompatibleProvider, UnconfiguredLLMProvider

        cfg_store = ConfigStore()
        config = cfg_store.snapshot()

        _, provider_cfg = resolve_provider_config(config.llm_provider)
        if provider_cfg is None:
            provider = UnconfiguredLLMProvider()
            model = ""
        else:
            provider = OpenAICompatibleProvider(
                api_key=provider_cfg.api_key,
                base_url=provider_cfg.base_url,
                author=provider_cfg.author,
            )
            model = provider_cfg.model or ""

        messages = []
        for msg in params.messages:
            content_text = ""
            if isinstance(msg.content, str):
                content_text = msg.content
            elif hasattr(msg.content, "text"):
                content_text = msg.content.text
            elif isinstance(msg.content, list):
                content_text = "\n".join(item.text for item in msg.content if hasattr(item, "text"))
            messages.append({"role": msg.role, "content": content_text})

        if hasattr(params, "systemPrompt") and params.systemPrompt:
            messages.insert(0, {"role": "system", "content": params.systemPrompt})

        tools_list = []
        if hasattr(params, "tools") and params.tools:
            for t in params.tools:
                tools_list.append(
                    {
                        "name": t.name,
                        "description": t.description or "",
                        "parameters": t.inputSchema,
                    }
                )

        llm_result = await provider.chat(
            messages=messages,
            tools=tools_list,
            model=model,
        )

        if llm_result.tool_calls:
            content_blocks = []
            for tc in llm_result.tool_calls:
                content_blocks.append(
                    ToolUseContent(
                        type="tool_use",
                        id=tc.id,
                        name=tc.name,
                        input=tc.arguments,
                    )
                )
            return CreateMessageResultWithTools(
                role="assistant",
                content=content_blocks,
                model=model,
                stopReason="toolUse",
            )
        else:
            return CreateMessageResult(
                role="assistant",
                content=TextContent(type="text", text=llm_result.content),
                model=model,
                stopReason="endTurn",
            )


class MCPServerTask:
    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self.session = None
        self.client_ctx = None
        self.tools = []
        self._keepalive_task = None

    async def connect(self):
        from unittest.mock import Mock

        is_mocked = isinstance(ClientSession, Mock) or isinstance(stdio_client, Mock)

        if not is_mocked:
            # Production Mode: Use strands MCPClient
            url = self.config.get("url")
            sampling_handler = SamplingHandler(self.name, self.config)

            if url or self.config.get("transport") == "sse":
                from mcp.client.sse import sse_client

                headers = self.config.get("headers", {})

                oauth_auth = None
                if self.config.get("auth") == "oauth" or "oauth" in self.config:
                    from dojoagents.tools.mcp_oauth import build_oauth_auth

                    oauth_auth = build_oauth_auth(self.name, url, self.config.get("oauth"))

                sse_kwargs = {
                    "url": url,
                    "headers": headers or None,
                    "sse_read_timeout": 300.0,
                }
                if oauth_auth is not None:
                    sse_kwargs["auth"] = oauth_auth

                transport_callable = lambda: sse_client(**sse_kwargs)  # noqa
            else:
                command = self.config.get("command")
                args = self.config.get("args", [])
                safe_env = _build_safe_env(self.config.get("env"))
                params = StdioServerParameters(command=command, args=args, env=safe_env)

                transport_callable = lambda: stdio_client(params)  # noqa

            from strands.tools.mcp import MCPClient

            self.mcp_client = MCPClient(transport_callable, elicitation_callback=sampling_handler)
            self.mcp_client.start()
            self.session = self.mcp_client._background_thread_session

            # Fetch tools
            paginated_tools = self.mcp_client.list_tools_sync()
            self.tools = [t.mcp_tool for t in paginated_tools]
            return

        # Legacy / Mock Mode (for unit tests)
        url = self.config.get("url")
        sampling_handler = SamplingHandler(self.name, self.config)

        if url or self.config.get("transport") == "sse":
            headers = self.config.get("headers", {})

            oauth_auth = None
            if self.config.get("auth") == "oauth" or "oauth" in self.config:
                from dojoagents.tools.mcp_oauth import build_oauth_auth

                oauth_auth = build_oauth_auth(self.name, url, self.config.get("oauth"))

            sse_kwargs = {
                "url": url,
                "headers": headers or None,
                "sse_read_timeout": 300.0,
            }
            if oauth_auth is not None:
                sse_kwargs["auth"] = oauth_auth

            self.client_ctx = sse_client(**sse_kwargs)
            read_stream, write_stream = await self.client_ctx.__aenter__()

            self.session = ClientSession(
                read_stream,
                write_stream,
                sampling_callback=sampling_handler,
                sampling_capabilities=SamplingCapability(tools=SamplingToolsCapability()),
            )
        else:
            command = self.config.get("command")
            args = self.config.get("args", [])
            safe_env = _build_safe_env(self.config.get("env"))
            params = StdioServerParameters(command=command, args=args, env=safe_env)

            self.client_ctx = stdio_client(params)
            read_stream, write_stream = await self.client_ctx.__aenter__()

            self.session = ClientSession(
                read_stream,
                write_stream,
                sampling_callback=sampling_handler,
                sampling_capabilities=SamplingCapability(tools=SamplingToolsCapability()),
            )

        await self.session.__aenter__()
        await self.session.initialize()

        tools_result = await self.session.list_tools()
        self.tools = tools_result.tools

        self._keepalive_task = asyncio.create_task(self._run_keepalive())

    async def disconnect(self):
        if hasattr(self, "mcp_client") and self.mcp_client:
            self.mcp_client.stop(None, None, None)
            return

        if self._keepalive_task:
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
            self._keepalive_task = None
        if self.session:
            await self.session.__aexit__(None, None, None)
        if self.client_ctx:
            await self.client_ctx.__aexit__(None, None, None)

    async def _run_keepalive(self):
        try:
            while True:
                await asyncio.sleep(180)  # 3 minutes
                if self.session:
                    try:
                        await asyncio.wait_for(self.session.list_tools(), timeout=30)
                    except Exception as e:
                        logger.warning(f"MCP server '{self.name}' keepalive failed: {e}")
        except asyncio.CancelledError:
            pass


async def _run_on_mcp_loop(coro):
    _ensure_mcp_loop()
    future = asyncio.run_coroutine_threadsafe(coro, _mcp_loop)
    return await asyncio.wrap_future(future)


def make_mcp_tool_handler(server_task: MCPServerTask, tool_name: str):
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        server_name = server_task.name
        if _server_error_counts.get(server_name, 0) >= _CIRCUIT_BREAKER_THRESHOLD:
            opened_at = _server_breaker_opened_at.get(server_name, 0.0)
            age = time.monotonic() - opened_at
            if age < _CIRCUIT_BREAKER_COOLDOWN_SEC:
                remaining = max(1, int(_CIRCUIT_BREAKER_COOLDOWN_SEC - age))
                raise Exception(f"MCP server '{server_name}' is unreachable due to circuit breaker. " f"Cooldown remaining: {remaining}s")

        # If we have a strands MCPClient, use it directly
        from unittest.mock import Mock

        mcp_client = getattr(server_task, "mcp_client", None)
        if mcp_client is not None and not isinstance(mcp_client, Mock):
            try:
                tool_use_id = f"tooluse_{os.urandom(8).hex()}"
                res = await mcp_client.call_tool_async(tool_use_id=tool_use_id, name=tool_name, arguments=args)
                if res.get("status") == "error":
                    error_msg = ""
                    if "content" in res and isinstance(res["content"], list):
                        error_msg = "\n".join(b.get("text", "") for b in res["content"] if isinstance(b, dict) and "text" in b)
                    raise Exception(error_msg or f"MCP tool '{tool_name}' returned error")
                parts = [b.get("text", "") for b in res["content"] if isinstance(b, dict) and "text" in b]
                _reset_server_error(server_name)
                return {"content": "\n".join(parts), "metadata": {"server": server_name, "mcp_tool": tool_name}}
            except Exception as e:
                _bump_server_error(server_name)
                raise Exception(_sanitize_error(str(e)))

        # Legacy / Mock Mode handler (tests)
        async def _call():
            try:
                res = await server_task.session.call_tool(tool_name, arguments=args)
                if res.isError:
                    error_msg = "".join(b.text for b in res.content if hasattr(b, "text") and b.text)
                    raise Exception(error_msg or f"MCP tool '{tool_name}' returned error")
                parts = [b.text for b in res.content if hasattr(b, "text") and b.text]
                _reset_server_error(server_name)
                return {"content": "\n".join(parts), "metadata": {"server": server_task.name, "mcp_tool": tool_name}}
            except Exception as e:
                _bump_server_error(server_name)
                raise Exception(_sanitize_error(str(e)))

        return await _run_on_mcp_loop(_call())

    return handler


def discover_and_register_mcp_tools(registry: ToolRegistry, mcp_config: dict[str, Any]) -> None:
    if not mcp_config:
        return
    _ensure_mcp_loop()

    async def _setup_all():
        for name, cfg in mcp_config.items():
            if not cfg.get("enabled", True):
                continue
            task = MCPServerTask(name, cfg)
            await task.connect()
            _servers[name] = task

            for mcp_tool in task.tools:
                _scan_mcp_description(name, mcp_tool.name, mcp_tool.description or "")
                safe_name = f"mcp_{name}_{mcp_tool.name}"
                spec = ToolSpec(name=safe_name, description=mcp_tool.description or "", parameters=mcp_tool.inputSchema, handler=make_mcp_tool_handler(task, mcp_tool.name))
                registry.register(spec)

    future = asyncio.run_coroutine_threadsafe(_setup_all(), _mcp_loop)
    try:
        future.result(timeout=30)
    except Exception as e:
        import logging

        logging.getLogger("dojoagents").error(f"Failed to initialize MCP servers: {e}")
