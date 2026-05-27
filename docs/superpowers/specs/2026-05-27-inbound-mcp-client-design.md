# Design Specification: DojoAgents Inbound MCP Client Integration

- **Date**: 2026-05-27
- **Author**: Antigravity
- **Status**: Approved

---

## 1. Background & Goal

The Model Context Protocol (MCP) allows AI agents to dynamically connect to external developer tools, APIs, and data sources. Currently, **DojoAgents** has a static, local tool execution flow. This design adds **Inbound MCP Client** support to DojoAgents, allowing the agent to connect to external MCP servers (via stdio and HTTP/SSE) and dynamically expose their tools directly into the agent's tool execution registry.

---

## 2. Architecture & Thread Model

To guarantee resilience, avoid circular event loop errors, and prevent blocking of main agent threads, we implement a **Dedicated Background Thread Event Loop** architecture:

```
[Main Process Thread]
       │
       ▼ (Initializes Runtime)
┌────────────────────────────────┐
│   Runtime.from_config_store()  │
└────────────────┬───────────────┘
                 │ (Run-Once Blocking Bootstrap)
                 ▼
┌────────────────────────────────┐
│    discover_mcp_tools()        ├───────┐ (Spawns)
└────────────────────────────────┘       ▼
                                   ┌───────────┐
                                   │  _lock    │
                                   └─────┬─────┘
                                         ▼
                                  ┌───────────────┐
                                  │  _mcp_thread  │ (Daemon Thread)
                                  │ ┌───────────┐ │
                                  │ │ _mcp_loop │ │ (Persistent asyncio loop)
                                  │ └─────┬─────┘ │
                                  └───────┼───────┘
                                          │ (Creates Tasks for each server)
                                          ▼
                                ┌──────────────────┐
                                │  MCPServerTask   │
                                │  - stdio / http  │
                                └──────────────────┘
```

1. **Persistent Daemon Thread**: A dedicated thread `mcp-event-loop` runs a persistent `asyncio` event loop `_mcp_loop` in the background.
2. **Task Isolation**: Each configured MCP server runs as a separate, long-lived `MCPServerTask` in the background loop.
3. **Bootstrapping (Runtime Startup)**: During `Runtime.from_config_store`, the main thread blocks using a thread-safe Future (`future.result(timeout=30)`) to let all configured MCP servers connect and fetch their tool schemas.
4. **Execution Bridging**: During active agent turns, tools are invoked asynchronously. The handler uses `asyncio.wrap_future` to await the background loop's execution result in a completely non-blocking manner on the main thread's loop.

---

## 3. Detailed Components

### 3.1 Configuration Additions

#### `dojoagents/config/models.py`
Add `mcp_servers` to the root `AgentsConfig` dataclass:
```python
@dataclass(frozen=True)
class AgentsConfig:
    # ... existing fields ...
    mcp_servers: dict[str, Any] = field(default_factory=dict)
```

#### `dojoagents/config/loader.py`
Pass the raw parsed YAML `mcp_servers` mapping to the `AgentsConfig` constructor:
```python
def _to_config(raw: dict[str, Any]) -> AgentsConfig:
    # ...
    return AgentsConfig(
        # ...
        mcp_servers=dict(raw.get("mcp_servers", {})),
    )
```

#### `pyproject.toml`
Add `mcp` SDK dependency under `dependencies`:
```toml
dependencies = [
    # ... existing dependencies ...
    "mcp>=1.26.0,<2",
]
```

### 3.2 Client Implementation (`dojoagents/tools/mcp_tool.py`)

A new module to manage the thread loop, client connections, and tool conversions.

```python
import asyncio
import threading
from typing import Any, Callable
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from dojoagents.tools.registry import ToolRegistry, ToolSpec

_mcp_loop: asyncio.AbstractEventLoop | None = None
_mcp_thread: threading.Thread | None = None
_lock = threading.Lock()
_servers: dict[str, "MCPServerTask"] = {}

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

async def _run_on_mcp_loop(coro):
    _ensure_mcp_loop()
    future = asyncio.run_coroutine_threadsafe(coro, _mcp_loop)
    return await asyncio.wrap_future(future)

class MCPServerTask:
    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self.session = None
        self.tools = []

    async def connect(self):
        # We start with stdio transport support, matching configuration commands
        command = self.config.get("command")
        args = self.config.get("args", [])
        params = StdioServerParameters(command=command, args=args, env=self.config.get("env"))
        
        # We store the stdio client generator context safely
        self.client_ctx = stdio_client(params)
        read_stream, write_stream = await self.client_ctx.__aenter__()
        
        self.session = ClientSession(read_stream, write_stream)
        await self.session.__aenter__()
        await self.session.initialize()
        
        tools_result = await self.session.list_tools()
        self.tools = tools_result.tools

    async def disconnect(self):
        if self.session:
            await self.session.__aexit__(None, None, None)
        if self.client_ctx:
            await self.client_ctx.__aexit__(None, None, None)

def make_mcp_tool_handler(server_task: MCPServerTask, tool_name: str) -> Callable[[dict[str, Any]], Any]:
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        async def _call():
            res = await server_task.session.call_tool(tool_name, arguments=args)
            if res.isError:
                error_msg = "".join(b.text for b in res.content if hasattr(b, "text") and b.text)
                raise Exception(error_msg or f"MCP tool '{tool_name}' returned error")
            parts = [b.text for b in res.content if hasattr(b, "text") and b.text]
            return {
                "content": "\n".join(parts),
                "metadata": {"server": server_task.name, "mcp_tool": tool_name}
            }
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
                safe_name = f"mcp_{name}_{mcp_tool.name}"
                spec = ToolSpec(
                    name=safe_name,
                    description=mcp_tool.description or "",
                    parameters=mcp_tool.inputSchema,
                    handler=make_mcp_tool_handler(task, mcp_tool.name)
                )
                registry.register(spec)

    future = asyncio.run_coroutine_threadsafe(_setup_all(), _mcp_loop)
    future.result(timeout=30)
