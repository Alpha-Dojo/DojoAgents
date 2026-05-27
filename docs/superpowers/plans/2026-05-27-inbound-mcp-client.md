# DojoAgents Inbound MCP Client Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Inbound MCP Client capabilities in DojoAgents, allowing the agent to load and execute external stdio MCP server tools.

**Architecture:** Initialize a persistent daemon thread running an asyncio event loop for handling long-lived MCP connections. Integrate this with the DojoAgents synchronous `Runtime` setup and asynchronous `ToolExecutor` via a non-blocking `asyncio.Future` bridge.

**Tech Stack:** python-mcp, asyncio, pytest, pyyaml

---

### Task 1: Config and Dependency Additions

**Files:**
- Modify: `pyproject.toml`
- Modify: `dojoagents/config/models.py`
- Modify: `dojoagents/config/loader.py`
- Create: `tests/test_mcp_config.py`

- [ ] **Step 1: Write the config loading test**
  
  Create `tests/test_mcp_config.py`:
  ```python
  import tempfile
  from pathlib import Path
  import pytest
  from dojoagents.config.loader import ConfigStore
  
  def test_load_mcp_servers_config():
      content = """
  version: 1
  mcp_servers:
    filesystem:
      command: "npx"
      args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
      enabled: true
  """
      with tempfile.TemporaryDirectory() as tmpdir:
          cfg_file = Path(tmpdir) / "agents.yaml"
          cfg_file.write_text(content, encoding="utf-8")
          store = ConfigStore(path=cfg_file)
          config = store.snapshot()
          assert "filesystem" in config.mcp_servers
          assert config.mcp_servers["filesystem"]["command"] == "npx"
          assert config.mcp_servers["filesystem"]["enabled"] is True
  ```

- [ ] **Step 2: Run the test to verify it fails**
  
  Run: `pytest tests/test_mcp_config.py -v`
  Expected: FAIL (or AttributeError because `mcp_servers` is not defined on `AgentsConfig`)

- [ ] **Step 3: Modify pyproject.toml to add `mcp` dependency**
  
  Add `"mcp>=1.26.0,<2"` to the `dependencies` list in `pyproject.toml`.

- [ ] **Step 4: Modify dojoagents/config/models.py to add `mcp_servers`**
  
  Add `mcp_servers` to `AgentsConfig`:
  ```python
      mcp_servers: dict[str, Any] = field(default_factory=dict)
  ```

- [ ] **Step 5: Modify dojoagents/config/loader.py to load `mcp_servers`**
  
  Update `_to_config` inside `loader.py`:
  ```python
      return AgentsConfig(
          # ... existing arguments ...
          mcp_servers=dict(raw.get("mcp_servers", {})),
      )
  ```

- [ ] **Step 6: Run the test to verify it passes**
  
  Run: `pytest tests/test_mcp_config.py -v`
  Expected: PASS

- [ ] **Step 7: Commit**
  
  ```bash
  git add pyproject.toml dojoagents/config/models.py dojoagents/config/loader.py tests/test_mcp_config.py
  git commit -m "feat: add mcp dependency and config models"
  ```

---

### Task 2: Implement MCPServerTask and Thread Event Loop in `mcp_tool.py`

**Files:**
- Create: `dojoagents/tools/mcp_tool.py`
- Create: `tests/test_mcp_loop.py`

- [ ] **Step 1: Write test for loop initialization and connection task**
  
  Create `tests/test_mcp_loop.py`:
  ```python
  import pytest
  import asyncio
  from unittest.mock import AsyncMock, patch, MagicMock
  from dojoagents.tools.mcp_tool import _ensure_mcp_loop, _mcp_loop, MCPServerTask
  
  def test_mcp_loop_starts():
      _ensure_mcp_loop()
      assert _mcp_loop is not None
      assert _mcp_loop.is_running()
  
  @pytest.mark.asyncio
  async def test_mcp_server_task_connect():
      config = {"command": "echo", "args": []}
      task = MCPServerTask("test_server", config)
      
      mock_session = AsyncMock()
      mock_session.initialize = AsyncMock()
      mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
      mock_session.__aenter__ = AsyncMock(return_value=mock_session)
      mock_session.__aexit__ = AsyncMock()
  
      mock_client = MagicMock()
      mock_client.__aenter__ = AsyncMock(return_value=("read_stream", "write_stream"))
      mock_client.__aexit__ = AsyncMock()
  
      with patch("dojoagents.tools.mcp_tool.stdio_client", return_value=mock_client), \
           patch("dojoagents.tools.mcp_tool.ClientSession", return_value=mock_session):
          await task.connect()
          assert task.session == mock_session
  ```

- [ ] **Step 2: Run the test to verify it fails**
  
  Run: `pytest tests/test_mcp_loop.py -v`
  Expected: FAIL with ModuleNotFoundError or import failure for `dojoagents.tools.mcp_tool`

- [ ] **Step 3: Implement event loop and MCPServerTask in `dojoagents/tools/mcp_tool.py`**
  
  Create `dojoagents/tools/mcp_tool.py` with:
  ```python
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
  ```

- [ ] **Step 4: Run the test to verify it passes**
  
  Run: `pytest tests/test_mcp_loop.py -v`
  Expected: PASS

- [ ] **Step 5: Commit**
  
  ```bash
  git add dojoagents/tools/mcp_tool.py tests/test_mcp_loop.py
  git commit -m "feat: implement background loop and MCPServerTask"
  ```

---

### Task 3: Implement Async Thread Bridging and make_mcp_tool_handler

**Files:**
- Modify: `dojoagents/tools/mcp_tool.py`
- Create: `tests/test_mcp_bridge.py`

- [ ] **Step 1: Write test for bridging and execution handler**
  
  Create `tests/test_mcp_bridge.py`:
  ```python
  import pytest
  from unittest.mock import AsyncMock, MagicMock
  from dojoagents.tools.mcp_tool import _run_on_mcp_loop, make_mcp_tool_handler, MCPServerTask
  
  @pytest.mark.asyncio
  async def test_run_on_mcp_loop():
      async def sample_coro():
          await asyncio.sleep(0.01)
          return "success"
      res = await _run_on_mcp_loop(sample_coro())
      assert res == "success"
  
  @pytest.mark.asyncio
  async def test_make_mcp_tool_handler_success():
      task = MCPServerTask("my_server", {})
      mock_session = AsyncMock()
      
      # Mock the CallToolResult from MCP session
      mock_content = MagicMock()
      mock_content.text = "output content"
      mock_result = MagicMock()
      mock_result.isError = False
      mock_result.content = [mock_content]
      
      mock_session.call_tool = AsyncMock(return_value=mock_result)
      task.session = mock_session
      
      handler = make_mcp_tool_handler(task, "hello")
      res = await handler({"message": "test"})
      assert res["content"] == "output content"
      assert res["metadata"]["server"] == "my_server"
  ```

- [ ] **Step 2: Run the test to verify it fails**
  
  Run: `pytest tests/test_mcp_bridge.py -v`
  Expected: FAIL with AttributeError (bridge functions and handler factories not defined)

- [ ] **Step 3: Implement `_run_on_mcp_loop` and `make_mcp_tool_handler`**
  
  Append to `dojoagents/tools/mcp_tool.py`:
  ```python
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
  ```

- [ ] **Step 4: Run the test to verify it passes**
  
  Run: `pytest tests/test_mcp_bridge.py -v`
  Expected: PASS

- [ ] **Step 5: Commit**
  
  ```bash
  git add dojoagents/tools/mcp_tool.py tests/test_mcp_bridge.py
  git commit -m "feat: implement async thread bridging and handler factory"
  ```

---

### Task 4: Implement discover_and_register_mcp_tools and Runtime Integration

**Files:**
- Modify: `dojoagents/tools/mcp_tool.py`
- Modify: `dojoagents/agent/runtime.py`
- Create: `tests/test_mcp_runtime_integration.py`

- [ ] **Step 1: Write integration test for runtime registration**
  
  Create `tests/test_mcp_runtime_integration.py`:
  ```python
  import pytest
  import tempfile
  from pathlib import Path
  from unittest.mock import AsyncMock, patch, MagicMock
  from dojoagents.config.loader import ConfigStore
  from dojoagents.agent.runtime import Runtime
  
  def test_runtime_registers_mcp_tools():
      content = """
  version: 1
  mcp_servers:
    test_filesystem:
      command: "mock_cmd"
      args: []
      enabled: true
  """
      # Mock the connection and listing of tools
      mock_tool = MagicMock()
      mock_tool.name = "read_file"
      mock_tool.description = "Read a file"
      mock_tool.inputSchema = {"type": "object", "properties": {}}
      
      mock_task = MagicMock()
      mock_task.tools = [mock_tool]
      mock_task.connect = AsyncMock()
      
      with tempfile.TemporaryDirectory() as tmpdir:
          cfg_file = Path(tmpdir) / "agents.yaml"
          cfg_file.write_text(content, encoding="utf-8")
          store = ConfigStore(path=cfg_file)
          
          with patch("dojoagents.tools.mcp_tool.MCPServerTask", return_value=mock_task):
              runtime = Runtime.from_config_store(store)
              spec = runtime.agent.tool_executor.registry.get("mcp_test_filesystem_read_file")
              assert spec is not None
              assert spec.description == "Read a file"
  ```

- [ ] **Step 2: Run the test to verify it fails**
  
  Run: `pytest tests/test_mcp_runtime_integration.py -v`
  Expected: FAIL with spec is None (discovery function not called in runtime)

- [ ] **Step 3: Implement discovery function in `dojoagents/tools/mcp_tool.py`**
  
  Append to `dojoagents/tools/mcp_tool.py`:
  ```python
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
  ```

- [ ] **Step 4: Update `dojoagents/agent/runtime.py` to call discovery**
  
  In `Runtime.from_config_store` inside `dojoagents/agent/runtime.py`:
  ```python
          # In from_config_store method:
          from dojoagents.tools.code_execution_tool import get_code_execution_spec
          tool_registry.register(get_code_execution_spec(tool_registry, policy))
  
          # ADD THIS BLOCK
          from dojoagents.tools.mcp_tool import discover_and_register_mcp_tools
          discover_and_register_mcp_tools(tool_registry, config.mcp_servers)
  
          tool_names = [spec.name for spec in tool_registry.all()]
  ```

- [ ] **Step 5: Run the test to verify it passes**
  
  Run: `pytest tests/test_mcp_runtime_integration.py -v`
  Expected: PASS

- [ ] **Step 6: Commit**
  
  ```bash
  git add dojoagents/tools/mcp_tool.py dojoagents/agent/runtime.py tests/test_mcp_runtime_integration.py
  git commit -m "feat: integrate mcp tool discovery into runtime initialization"
  ```
