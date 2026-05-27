import asyncio
import threading
from typing import Any
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

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

class MCPServerTask:
    def __init__(self, name: str, config: dict):
        self.name = name
        self.config = config
        self.session = None
        self.client_ctx = None
        self.tools = []

    async def connect(self):
        command = self.config.get("command")
        args = self.config.get("args", [])
        params = StdioServerParameters(command=command, args=args, env=self.config.get("env"))
        
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

async def _run_on_mcp_loop(coro):
    _ensure_mcp_loop()
    future = asyncio.run_coroutine_threadsafe(coro, _mcp_loop)
    return await asyncio.wrap_future(future)

def make_mcp_tool_handler(server_task: MCPServerTask, tool_name: str):
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
