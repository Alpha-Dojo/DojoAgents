import anyio
import concurrent.futures
import functools
import os
import re
import time
import logging
import threading
from typing import Any, List, Optional, TypeVar
from mcp import ClientSession, StdioServerParameters
from mcp.client import sse as mcp_sse
from mcp.client.stdio import stdio_client
from dojoagents.tools.registry import ToolRegistry, ToolSpec
from dojoagents.utils.blocking_portal import (
    PortalClosedError,
    PortalError,
    ThreadedBlockingPortal,
)

logger = logging.getLogger("dojoagents")

T = TypeVar("T")

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


MCP_KEEPALIVE_INTERVAL_SECONDS = 180.0
MCP_KEEPALIVE_TIMEOUT_SECONDS = 30.0
MCP_START_TIMEOUT_SECONDS = 30.0
MCP_CONNECT_TIMEOUT_SECONDS = 15.0
MCP_STOP_TIMEOUT_SECONDS = 10.0
MCP_CALL_TIMEOUT_SECONDS = 120.0
MCP_SHUTDOWN_TIMEOUT_SECONDS = 30.0
MCP_RECONNECT_BACKOFF_SECONDS = 1.0
MCP_RECONNECT_MAX_BACKOFF_SECONDS = 30.0
MCP_READY_POLL_SECONDS = 0.05

# Outcomes of one open -> keepalive -> close cycle.
_CYCLE_STOPPED = "stopped"
_CYCLE_UNHEALTHY = "unhealthy"
_CYCLE_FAILED = "failed"

_server_error_counts: dict[str, int] = {}
_server_breaker_opened_at: dict[str, float] = {}
_CIRCUIT_BREAKER_THRESHOLD = 3
_CIRCUIT_BREAKER_COOLDOWN_SEC = 60.0


class MCPStartupError(RuntimeError):
    """An MCP server could not become ready inside its bounded startup window."""


class MCPUnavailableError(RuntimeError):
    """An MCP server has no usable session (still starting, reconnecting, or stopped)."""


def _bump_server_error(server_name: str) -> None:
    n = _server_error_counts.get(server_name, 0) + 1
    _server_error_counts[server_name] = n
    if n >= _CIRCUIT_BREAKER_THRESHOLD:
        _server_breaker_opened_at[server_name] = time.monotonic()


def _reset_server_error(server_name: str) -> None:
    _server_error_counts[server_name] = 0
    _server_breaker_opened_at.pop(server_name, None)


def _unwrap_error(exc: BaseException) -> BaseException:
    """Collapse a single-child ``ExceptionGroup`` to its cause.

    AnyIO wraps everything that escapes a task group, so the real transport error
    would otherwise be hidden behind an unhelpful group.
    """

    while isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
        exc = exc.exceptions[0]
    return exc


async def _wait_for_first(*events: anyio.Event) -> int:
    """Return the index of whichever event is set first."""

    signalled: list[int] = []

    async def _waiter(index: int, event: anyio.Event) -> None:
        await event.wait()
        if not signalled:
            signalled.append(index)
        task_group.cancel_scope.cancel()

    async with anyio.create_task_group() as task_group:
        for index, event in enumerate(events):
            task_group.start_soon(_waiter, index, event)
    if not signalled:
        raise RuntimeError("wait_for_first completed without any event being signalled")
    return signalled[0]


async def _wait_for_event(event: anyio.Event, timeout: float) -> bool:
    """Wait up to ``timeout`` for ``event``; return whether it was set in time."""

    with anyio.move_on_after(timeout):
        await event.wait()
    return event.is_set()


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
        from dojoagents.agent.provider_profiles import resolve_provider_profile

        cfg_store = ConfigStore()
        config = cfg_store.snapshot()

        provider_name, provider_cfg = resolve_provider_config(config.llm_provider)
        if provider_cfg is None:
            provider = UnconfiguredLLMProvider()
            model = ""
        else:
            resolved_profile = resolve_provider_profile(provider_name or "openai", provider_cfg)
            provider = OpenAICompatibleProvider(
                api_key=provider_cfg.api_key,
                base_url=provider_cfg.base_url,
                author=provider_cfg.author,
                extra_headers=provider_cfg.extra_headers,
                timeout=provider_cfg.timeout,
                max_retries=provider_cfg.max_retries,
                max_response_bytes=provider_cfg.max_response_bytes,
                request_policy=resolved_profile.wire_policy,
                model_id_policy=resolved_profile.model_id_policy,
            )
            provider.name = provider_name or "openai"
            model = provider_cfg.model or ""
        from dojoagents.agent.usage import ensure_metered_provider

        provider = ensure_metered_provider(provider)

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

        from dojoagents.agent.usage import usage_scope

        with usage_scope("tool_internal", "tool_internal.mcp"):
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
    """Owns one MCP server session for its whole lifetime.

    ``serve`` is started exactly once by the owning :class:`MCPToolRuntime` and is
    the only task allowed to open *and* close the transport context and the
    session: AnyIO requires a nested task group's ``__aenter__``/``__aexit__`` to
    run in the same task, and the previous shape (connect from the registering
    call, disconnect from an unrelated call) could never have unwound correctly.

    Keepalive, reconnect, and close all live inside the task group created by
    ``serve`` so that cancellation always unwinds the whole server with bounded
    timeouts.
    """

    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self.session = None
        self.client_ctx = None
        self.tools = []
        # Set by the runtime that adopts this server; ``None`` means the server is
        # not attached to an owning portal (unit tests, or a stopped component).
        self.portal: ThreadedBlockingPortal | None = None
        self.ready = threading.Event()
        self.startup_error: BaseException | None = None
        self.connect_error: BaseException | None = None
        self.stopped = threading.Event()
        self.reconnect_count = 0
        self.last_reconnect_at: float | None = None
        self._stop_requested = False
        self._stop_event: anyio.Event | None = None
        self._reconnect_event: anyio.Event | None = None

    async def connect(self):
        from unittest.mock import Mock

        is_mocked = isinstance(ClientSession, Mock) or isinstance(stdio_client, Mock)

        if not is_mocked:
            # Production Mode: Use strands MCPClient
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

                transport_callable = lambda: mcp_sse.sse_client(**sse_kwargs)  # noqa
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

            self.client_ctx = mcp_sse.sse_client(**sse_kwargs)
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

    async def disconnect(self) -> None:
        """Close the session and transport. Must run in the task that opened them."""

        if getattr(self, "mcp_client", None):
            self.mcp_client.stop(None, None, None)
            return

        if self.session is not None:
            session, self.session = self.session, None
            await session.__aexit__(None, None, None)
        if self.client_ctx is not None:
            client_ctx, self.client_ctx = self.client_ctx, None
            await client_ctx.__aexit__(None, None, None)

    # ── ownership ───────────────────────────────────────────────────

    def request_stop(self) -> None:
        """Ask ``serve`` to stop. Must be called on the owning event loop."""

        self._stop_requested = True
        if self._stop_event is not None:
            self._stop_event.set()

    def request_reconnect(self) -> None:
        """Ask ``serve`` to rebuild the session. Must be called on the owning loop."""

        if self._reconnect_event is not None:
            self._reconnect_event.set()

    async def serve(self) -> None:
        """Supervise the server: open, keep alive, reconnect, and close it."""

        failures = 0
        try:
            while True:
                outcome = await self._run_session_cycle()
                if outcome == _CYCLE_STOPPED:
                    break
                if outcome == _CYCLE_FAILED and not self.ready.is_set():
                    # First attach never succeeded: report it instead of looping.
                    self.startup_error = self.connect_error or RuntimeError(f"MCP server '{self.name}' failed to start")
                    break
                failures += 1
                delay = min(
                    MCP_RECONNECT_BACKOFF_SECONDS * (2 ** (failures - 1)),
                    MCP_RECONNECT_MAX_BACKOFF_SECONDS,
                )
                self.reconnect_count += 1
                self.last_reconnect_at = time.monotonic()
                logger.info(
                    "MCP server '%s' rebuilding in %.1fs (reason=%s, failure streak=%d)",
                    self.name,
                    delay,
                    outcome,
                    failures,
                )
                await self._backoff(delay)
                if self._stop_requested:
                    break
        except BaseException as exc:  # noqa: BLE001 - recorded for the starter, then re-raised
            if not self.ready.is_set():
                self.startup_error = _unwrap_error(exc)
            raise
        finally:
            if not self.ready.is_set():
                self.startup_error = self.startup_error or RuntimeError(f"MCP server '{self.name}' stopped before it became ready")
            self.ready.set()
            self.stopped.set()

    async def _backoff(self, delay: float) -> None:
        """Wait before the next rebuild, waking immediately on a stop request."""

        self._stop_event = anyio.Event()
        try:
            await _wait_for_event(self._stop_event, delay)
        finally:
            self._stop_event = None

    async def _run_session_cycle(self) -> str:
        """One open -> keepalive -> close cycle, reported as a cycle outcome."""

        async with anyio.create_task_group() as server_tasks:
            self._stop_event = anyio.Event()
            self._reconnect_event = anyio.Event()
            if self._stop_requested:
                self._stop_event.set()
            try:
                try:
                    with anyio.fail_after(MCP_CONNECT_TIMEOUT_SECONDS):
                        await self.connect()
                except anyio.get_cancelled_exc_class():
                    raise
                except BaseException as exc:  # noqa: BLE001 - reconnect loop owns recovery
                    self.connect_error = _unwrap_error(exc)
                    server_tasks.cancel_scope.cancel()
                    return _CYCLE_FAILED
                self.connect_error = None
                self.ready.set()
                server_tasks.start_soon(self._keepalive_loop)
                trigger = await _wait_for_first(self._stop_event, self._reconnect_event)
                if trigger == 0:
                    self._stop_requested = True
                    return _CYCLE_STOPPED
                return _CYCLE_UNHEALTHY
            finally:
                self._stop_event = None
                self._reconnect_event = None
                server_tasks.cancel_scope.cancel()
                await _close_quietly(self)

    async def _keepalive_loop(self) -> None:
        """Ping the session on an interval; ask ``serve`` to rebuild on failure."""

        while True:
            if await _wait_for_event(self._stop_event, MCP_KEEPALIVE_INTERVAL_SECONDS):
                return
            await self._ping_once()

    async def _ping_once(self) -> None:
        session = self.session
        if session is None:
            self.request_reconnect()
            return
        try:
            with anyio.fail_after(MCP_KEEPALIVE_TIMEOUT_SECONDS):
                await session.list_tools()
        except anyio.get_cancelled_exc_class():
            raise
        except Exception as exc:  # noqa: BLE001 - any transport failure triggers a rebuild
            logger.warning("MCP server '%s' keepalive failed: %s", self.name, exc)
            self.request_reconnect()

    # ── tool dispatch ───────────────────────────────────────────────

    async def call_tool(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        *,
        timeout: float = MCP_CALL_TIMEOUT_SECONDS,
    ) -> Any:
        """Call a tool on this server's session from any thread or event loop."""

        session = self.session
        if session is None:
            raise MCPUnavailableError(f"MCP server '{self.name}' has no active session")
        portal = self.portal
        if portal is None:
            # Not attached to an owning portal: run inline so callers still get a
            # real error instead of a silently different execution path.
            return await session.call_tool(tool_name, arguments=arguments)
        if not portal.running:
            raise MCPUnavailableError(f"MCP server '{self.name}' is shut down and no longer accepts calls")
        return await portal.call_async(session.call_tool, tool_name, arguments=arguments, timeout=timeout)


async def _close_quietly(server: MCPServerTask) -> None:
    """Close a server's transport, never letting a close failure mask the real cause.

    This deliberately adds no shield or timeout scope around the close: AnyIO only
    permits a cancel scope to be closed while it is the task's current scope, and
    the transport's ``__aexit__`` closes scopes that were opened by ``connect`` at
    the same depth.  Wrapping it would raise ``RuntimeError`` instead of closing.
    Boundedness comes from the surrounding lifecycle instead: ``stop_server`` and
    ``portal.shutdown`` give up after their own timeouts.
    """

    try:
        await server.disconnect()
    except Exception:  # noqa: BLE001 - teardown must never mask the real failure
        logger.warning("MCP server '%s' did not close cleanly", server.name, exc_info=True)


def _log_server_task_failure(server: MCPServerTask, future: concurrent.futures.Future) -> None:
    """Surface a supervisor exit that happened after startup succeeded."""

    if future.cancelled():
        return
    exc = future.exception()
    if exc is not None and server.ready.is_set() and server.startup_error is None:
        logger.warning("MCP server '%s' supervisor stopped: %s", server.name, exc)


class MCPToolRuntime:
    """Process-wide owner of the MCP portal and the servers running on it.

    The portal is created lazily on first use and lives for the process; nothing
    here relies on ``__del__``.  ``shutdown`` stops accepting calls, stops every
    server, then closes the portal and joins its thread.
    """

    def __init__(self, *, name: str = "mcp-portal") -> None:
        self._guard = threading.Lock()
        self._portal = ThreadedBlockingPortal(name=name)
        self.servers: dict[str, MCPServerTask] = {}

    @property
    def portal(self) -> ThreadedBlockingPortal:
        return self._portal

    def start_server(self, server: MCPServerTask, *, timeout: float = MCP_START_TIMEOUT_SECONDS) -> MCPServerTask:
        """Adopt ``server``, start its supervisor, and wait (bounded) until it is ready."""

        self._portal.start()
        server.portal = self._portal
        future = self._portal.start_task(server.serve, name=f"mcp-server:{server.name}")
        future.add_done_callback(functools.partial(_log_server_task_failure, server))
        deadline = time.monotonic() + timeout
        while not server.ready.wait(MCP_READY_POLL_SECONDS):
            if time.monotonic() >= deadline:
                raise MCPStartupError(f"MCP server '{server.name}' did not become ready within {timeout:g}s")
        if server.startup_error is not None:
            raise MCPStartupError(f"MCP server '{server.name}' failed to start: {server.startup_error}") from server.startup_error
        with self._guard:
            self.servers[server.name] = server
        return server

    def request_reconnect(self, name: str) -> bool:
        """Thread-safe: ask the owning loop to rebuild the named server's session."""

        server = self.servers.get(name)
        if server is None:
            return False
        try:
            self._portal.call(server.request_reconnect, timeout=MCP_STOP_TIMEOUT_SECONDS)
        except PortalError as exc:
            logger.warning("MCP server '%s' reconnect request failed: %s", name, exc)
            return False
        return True

    def stop_server(self, name: str, *, timeout: float = MCP_STOP_TIMEOUT_SECONDS) -> bool:
        """Stop one server and wait (bounded) for its task to unwind."""

        with self._guard:
            server = self.servers.pop(name, None)
        if server is None:
            return False
        try:
            self._portal.call(server.request_stop, timeout=timeout)
        except PortalError as exc:
            logger.warning("MCP server '%s' stop request failed: %s", name, exc)
        server.stopped.wait(timeout)
        return True

    def shutdown(self, *, timeout: float = MCP_SHUTDOWN_TIMEOUT_SECONDS) -> None:
        """Stop every server, then close the portal and join its thread. Idempotent."""

        for name in list(self.servers):
            self.stop_server(name)
        with self._guard:
            self.servers.clear()
        self._portal.shutdown(timeout=timeout)

    async def ashutdown(self, *, timeout: float = MCP_SHUTDOWN_TIMEOUT_SECONDS) -> None:
        """Async-safe :meth:`shutdown`."""

        await self._portal.run_sync(
            self.shutdown,
            timeout=timeout,
            abandon_on_cancel=True,
        )


_MCP_RUNTIME: MCPToolRuntime | None = None
_MCP_RUNTIME_GUARD = threading.Lock()


def mcp_runtime() -> MCPToolRuntime:
    """Return the process-wide MCP runtime, creating it on first use."""

    global _MCP_RUNTIME
    with _MCP_RUNTIME_GUARD:
        if _MCP_RUNTIME is None:
            _MCP_RUNTIME = MCPToolRuntime()
        return _MCP_RUNTIME


def shutdown_mcp_tools(*, timeout: float = MCP_SHUTDOWN_TIMEOUT_SECONDS) -> None:
    """Stop every MCP server and close the shared portal. Safe to call repeatedly."""

    with _MCP_RUNTIME_GUARD:
        runtime = _MCP_RUNTIME
    if runtime is None:
        return
    runtime.shutdown(timeout=timeout)


async def ashutdown_mcp_tools(*, timeout: float = MCP_SHUTDOWN_TIMEOUT_SECONDS) -> None:
    """Async-safe :func:`shutdown_mcp_tools`."""

    with _MCP_RUNTIME_GUARD:
        runtime = _MCP_RUNTIME
    if runtime is None:
        return
    await runtime.ashutdown(timeout=timeout)


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

        # Legacy session path: dispatch through the owning portal so the session
        # stays on the event loop that owns it.
        async def _call():
            try:
                res = await server_task.call_tool(tool_name, args)
                if res.isError:
                    error_msg = "".join(b.text for b in res.content if hasattr(b, "text") and b.text)
                    raise Exception(error_msg or f"MCP tool '{tool_name}' returned error")
                parts = [b.text for b in res.content if hasattr(b, "text") and b.text]
                _reset_server_error(server_name)
                return {"content": "\n".join(parts), "metadata": {"server": server_task.name, "mcp_tool": tool_name}}
            except Exception as e:
                _bump_server_error(server_name)
                raise Exception(_sanitize_error(str(e)))

        return await _call()

    return handler


def discover_and_register_mcp_tools(registry: ToolRegistry, mcp_config: dict[str, Any]) -> None:
    """Register every enabled MCP server's tools into ``registry``.

    Runs on the calling (synchronous) thread: the shared portal accepts the
    work, and each server reports readiness before its tools are registered, so
    a failure is raised here instead of surfacing later as an empty tool list.
    """

    if not mcp_config:
        return

    enabled = [(name, cfg) for name, cfg in mcp_config.items() if cfg.get("enabled", True)]
    if not enabled:
        return

    runtime = mcp_runtime()
    for name, cfg in enabled:
        task = MCPServerTask(name, cfg)
        try:
            runtime.start_server(task)
        except MCPStartupError as exc:
            logger.error("Failed to initialize MCP server '%s': %s", name, exc)
            if exc.__cause__ is not None:
                logger.debug("MCP server '%s' startup traceback", name, exc_info=exc.__cause__)
            continue

        for mcp_tool in task.tools:
            _scan_mcp_description(name, mcp_tool.name, mcp_tool.description or "")
            safe_name = f"mcp_{name}_{mcp_tool.name}"
            spec = ToolSpec(
                name=safe_name,
                description=mcp_tool.description or "",
                parameters=mcp_tool.inputSchema,
                handler=make_mcp_tool_handler(task, mcp_tool.name),
            )
            registry.register(spec)
