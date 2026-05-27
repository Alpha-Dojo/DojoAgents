# DojoAgents 终端与代码执行能力集成实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 移植并协程化重写 hermes-agent 的终端执行（Local, Docker, Modal, SSH）与代码程序化调用（PTC）能力，使 DojoAgents 拥有强健的本地和沙箱执行、后台监控通知及多步代码工具调用的威力。

**Architecture:** 构建以 `asyncio.subprocess` 为基石的 `BaseEnvironment` 环境体系；在父进程利用 `asyncio.start_unix_server` 运行原生异步 RPC 服务，接收子进程的 RPC 内置工具调用；在后台进程管理器中对 `asyncio.subprocess.Process` 进行集中监控和轮询完成事件。

**Tech Stack:** `asyncio`, `subprocess`, Unix Domain Sockets, Python 进程沙箱。

---

### Task 1: 异步环境基类与本地环境重构

**Files:**
- Create: `dojoagents/tools/environments/base.py`
- Modify: `dojoagents/tools/environments/local.py`
- Test: `tests/test_local_environment.py`

- [ ] **Step 1: 编写测试用例验证 LocalEnvironment 协程执行命令**
  新建 `tests/test_local_environment.py`：
  ```python
  import asyncio
  import pytest
  import tempfile
  import os
  from dojoagents.tools.environments.local import LocalEnvironment
  from dojoagents.tools.sandbox import SandboxPolicy

  @pytest.mark.asyncio
  async def test_local_env_execute_success():
      policy = SandboxPolicy(allow_network=True)
      env = LocalEnvironment(policy=policy, cwd=tempfile.gettempdir())
      
      res = await env.execute("echo 'hello dojo'")
      assert res["exit_code"] == 0
      assert "hello dojo" in res["output"]

  @pytest.mark.asyncio
  async def test_local_env_cwd_persistence():
      policy = SandboxPolicy()
      tmp_dir1 = tempfile.mkdtemp()
      tmp_dir2 = tempfile.mkdtemp()
      try:
          env = LocalEnvironment(policy=policy, cwd=tmp_dir1)
          # 执行 cd 切换路径
          res = await env.execute(f"cd {tmp_dir2}")
          assert res["exit_code"] == 0
          # 验证执行器的内部 cwd 已更新
          assert env.cwd == tmp_dir2
      finally:
          os.rmdir(tmp_dir1)
          os.rmdir(tmp_dir2)
  ```

- [ ] **Step 2: 运行测试以验证失败**
  运行：`pytest tests/test_local_environment.py`
  预期：失败，因为 `LocalEnvironment` 尚未实现 `execute` 方法。

- [ ] **Step 3: 编写 `BaseEnvironment` 异步基类实现**
  新建 `dojoagents/tools/environments/base.py`：
  ```python
  import asyncio
  import os
  import shlex
  from abc import ABC, abstractmethod

  class BaseEnvironment(ABC):
      def __init__(self, cwd: str, timeout: float = 120.0):
          self.cwd = os.path.abspath(os.path.expanduser(cwd))
          self.timeout = timeout
          self._session_id = os.urandom(6).hex()
          self.env_vars = os.environ.copy()

      @abstractmethod
      async def _run_bash(self, cmd_string: str, timeout: float, stdin_data: str = None) -> asyncio.subprocess.Process:
          pass

      async def execute(self, command: str, timeout: float = None) -> dict:
          eff_timeout = timeout or self.timeout
          cwd_marker = f"__DOJO_CWD_{self._session_id}__"
          cwd_file = f"/tmp/dojo-cwd-{self._session_id}.txt"
          
          wrapped_command = (
              f"cd {shlex.quote(self.cwd)} || exit 126\n"
              f"{command}\n"
              f"__exit_code=$?\n"
              f"pwd -P > {cwd_file} 2>/dev/null || true\n"
              f"printf '\\n{cwd_marker}%s{cwd_marker}\\n' \"$(pwd -P)\"\n"
              f"exit $__exit_code"
          )
          
          process = await self._run_bash(wrapped_command, eff_timeout)
          try:
              stdout_bytes, _ = await asyncio.wait_for(
                  process.communicate(),
                  timeout=eff_timeout
              )
              output = stdout_bytes.decode("utf-8", errors="replace")
              returncode = process.returncode
          except asyncio.TimeoutError:
              try:
                  process.kill()
              except OSError:
                  pass
              await process.wait()
              return {"output": "Command timed out", "exit_code": 124}

          if cwd_marker in output:
              parts = output.split(cwd_marker)
              if len(parts) >= 3:
                  new_cwd = parts[-2].strip()
                  if os.path.isdir(new_cwd):
                      self.cwd = new_cwd
                  output = parts[0] + parts[-1]

          return {
              "output": output.strip(),
              "exit_code": returncode if returncode is not None else 0,
          }
  ```

- [ ] **Step 4: 实现 `LocalEnvironment` 中的子进程执行**
  修改 `dojoagents/tools/environments/local.py`：
  ```python
  from __future__ import annotations
  import asyncio
  from dojoagents.tools.environments.base import BaseEnvironment
  from dojoagents.tools.sandbox import SandboxPolicy

  class LocalEnvironment(BaseEnvironment):
      def __init__(self, policy: SandboxPolicy, cwd: str = ".") -> None:
          super().__init__(cwd=cwd)
          self.policy = policy

      async def _run_bash(self, cmd_string: str, timeout: float, stdin_data: str = None) -> asyncio.subprocess.Process:
          self.policy.check_tool("terminal")
          return await asyncio.create_subprocess_shell(
              cmd_string,
              stdout=asyncio.subprocess.PIPE,
              stderr=asyncio.subprocess.STDOUT,
              stdin=asyncio.subprocess.PIPE if stdin_data else asyncio.subprocess.DEVNULL,
              env=self.env_vars
          )
  ```

- [ ] **Step 5: 验证测试通过并 Commit**
  运行：`pytest tests/test_local_environment.py`
  预期：PASS。
  运行：
  ```bash
  git add dojoagents/tools/environments/base.py dojoagents/tools/environments/local.py tests/test_local_environment.py
  git commit -m "feat: add BaseEnvironment and rewrite LocalEnvironment to be async"
  ```

---

### Task 2: Docker/SSH/Modal 异步环境封装移植

**Files:**
- Create: `dojoagents/tools/environments/docker.py`
- Create: `dojoagents/tools/environments/ssh.py`
- Create: `dojoagents/tools/environments/modal.py`
- Test: `tests/test_remote_environments.py`

- [ ] **Step 1: 编写测试用例验证 Docker/SSH 环境指令调度参数**
  创建 `tests/test_remote_environments.py`：
  ```python
  import pytest
  from unittest.mock import AsyncMock, patch
  from dojoagents.tools.environments.docker import DockerEnvironment
  from dojoagents.tools.environments.ssh import SSHEnvironment

  @pytest.mark.asyncio
  async def test_docker_env_run_bash_calls_subprocess():
      env = DockerEnvironment(image="python:3.11", cwd="/workspace")
      
      mock_process = AsyncMock()
      mock_process.communicate.return_value = (b"__DOJO_CWD_xyz__/workspace__DOJO_CWD_xyz__", b"")
      mock_process.returncode = 0
      
      with patch("asyncio.create_subprocess_exec", return_value=mock_process) as mock_exec:
          res = await env.execute("ls")
          assert res["exit_code"] == 0
          mock_exec.assert_called_once()
          args = mock_exec.call_args[0]
          assert "docker" in args[0]
  ```

- [ ] **Step 2: 运行测试以验证失败**
  运行：`pytest tests/test_remote_environments.py`
  预期：失败，因为 `DockerEnvironment` / `SSHEnvironment` 尚未创建。

- [ ] **Step 3: 编写 `DockerEnvironment` 原生异步包装**
  新建 `dojoagents/tools/environments/docker.py`：
  ```python
  import asyncio
  from dojoagents.tools.environments.base import BaseEnvironment

  class DockerEnvironment(BaseEnvironment):
      def __init__(self, image: str, cwd: str = "/workspace", container_name: str = None):
          super().__init__(cwd=cwd)
          self.image = image
          self.container_name = container_name or f"dojo-sandbox-{self._session_id}"
          self._started = False

      async def _ensure_container(self):
          if self._started:
              return
          # 异步创建并启动后台挂载的容器
          start_cmd = [
              "docker", "run", "-d", "--name", self.container_name,
              "--workdir", self.cwd, self.image, "tail", "-f", "/dev/null"
          ]
          proc = await asyncio.create_subprocess_exec(
              *start_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
          )
          await proc.communicate()
          self._started = True

      async def _run_bash(self, cmd_string: str, timeout: float, stdin_data: str = None) -> asyncio.subprocess.Process:
          await self._ensure_container()
          exec_cmd = ["docker", "exec", "-i", self.container_name, "bash", "-c", cmd_string]
          return await asyncio.create_subprocess_exec(
              *exec_cmd,
              stdout=asyncio.subprocess.PIPE,
              stderr=asyncio.subprocess.STDOUT,
              stdin=asyncio.subprocess.PIPE if stdin_data else asyncio.subprocess.DEVNULL
          )

      def cleanup(self):
          if self._started:
              import subprocess
              subprocess.run(["docker", "rm", "-f", self.container_name], capture_output=True)
  ```

- [ ] **Step 4: 编写 `SSHEnvironment` 异步交互包**
  新建 `dojoagents/tools/environments/ssh.py`：
  ```python
  import asyncio
  import shlex
  from dojoagents.tools.environments.base import BaseEnvironment

  class SSHEnvironment(BaseEnvironment):
      def __init__(self, host: str, user: str, port: int = 22, cwd: str = "~"):
          super().__init__(cwd=cwd)
          self.host = host
          self.user = user
          self.port = port

      async def _run_bash(self, cmd_string: str, timeout: float, stdin_data: str = None) -> asyncio.subprocess.Process:
          ssh_target = f"{self.user}@{self.host}"
          quoted_cmd = shlex.quote(cmd_string)
          exec_cmd = ["ssh", "-p", str(self.port), ssh_target, f"bash -c {quoted_cmd}"]
          return await asyncio.create_subprocess_exec(
              *exec_cmd,
              stdout=asyncio.subprocess.PIPE,
              stderr=asyncio.subprocess.STDOUT,
              stdin=asyncio.subprocess.PIPE if stdin_data else asyncio.subprocess.DEVNULL
          )

      def cleanup(self):
          pass
  ```

- [ ] **Step 5: 验证测试通过并 Commit**
  运行：`pytest tests/test_remote_environments.py`
  预期：PASS。
  运行：
  ```bash
  git add dojoagents/tools/environments/docker.py dojoagents/tools/environments/ssh.py tests/test_remote_environments.py
  git commit -m "feat: add Docker and SSH async execution environments"
  ```

---

### Task 3: 异步后台任务管理器设计实现

**Files:**
- Create: `dojoagents/tools/process_registry.py`
- Test: `tests/test_process_registry.py`

- [ ] **Step 1: 编写测试用例验证后台任务注册及等待通知**
  创建 `tests/test_process_registry.py`：
  ```python
  import pytest
  import asyncio
  from dojoagents.tools.process_registry import AsyncProcessRegistry

  @pytest.mark.asyncio
  async def test_process_registry_spawn_and_await():
      registry = AsyncProcessRegistry()
      # 异步启动一个后台命令，休眠 1 秒
      proc_session = await registry.spawn("sleep 1")
      assert proc_session.id is not None
      
      # 轮询验证后台进程处于活跃状态
      assert registry.has_active_processes()
      
      # 等待该进程执行结束
      await proc_session.wait()
      assert not registry.has_active_processes()
  ```

- [ ] **Step 2: 运行测试以验证失败**
  运行：`pytest tests/test_process_registry.py`
  预期：失败，因为 `AsyncProcessRegistry` 尚未定义。

- [ ] **Step 3: 实现 `AsyncProcessRegistry` 逻辑**
  创建 `dojoagents/tools/process_registry.py`：
  ```python
  import asyncio
  import uuid
  from typing import Dict

  class BackgroundProcessSession:
      def __init__(self, session_id: str, process: asyncio.subprocess.Process, command: str):
          self.id = session_id
          self.process = process
          self.command = command
          self.notify_on_complete = False

      async def wait(self):
          await self.process.wait()

  class AsyncProcessRegistry:
      def __init__(self):
          self.processes: Dict[str, BackgroundProcessSession] = {}

      async def spawn(self, command: str, env_vars: dict = None) -> BackgroundProcessSession:
          session_id = uuid.uuid4().hex[:12]
          process = await asyncio.create_subprocess_shell(
              command,
              stdout=asyncio.subprocess.PIPE,
              stderr=asyncio.subprocess.STDOUT,
              stdin=asyncio.subprocess.DEVNULL,
              env=env_vars
          )
          session = BackgroundProcessSession(session_id, process, command)
          self.processes[session_id] = session
          
          # 后台启动异步监测协程
          asyncio.create_thread(self._reap_process(session_id))
          return session

      async def _reap_process(self, session_id: str):
          session = self.processes.get(session_id)
          if session:
              await session.wait()
              # 此处后续可集成向 Agent 发送通知唤醒的逻辑
              self.processes.pop(session_id, None)

      def has_active_processes(self) -> bool:
          return len(self.processes) > 0
  ```
  *(注：使用 `asyncio.create_task` 代替 `asyncio.create_thread` 以维持纯协程模型。在实现中将 `asyncio.create_thread` 替换为 `asyncio.create_task`)*

- [ ] **Step 4: 验证测试通过并 Commit**
  运行：`pytest tests/test_process_registry.py`
  预期：PASS。
  运行：
  ```bash
  git add dojoagents/tools/process_registry.py tests/test_process_registry.py
  git commit -m "feat: add AsyncProcessRegistry to manage background subprocesses"
  ```

---

### Task 4: Terminal Tool 集成与 Runtime 注册

**Files:**
- Create: `dojoagents/tools/terminal_tool.py`
- Modify: `dojoagents/agent/runtime.py`
- Test: `tests/test_terminal_tool_integrated.py`

- [ ] **Step 1: 编写集成测试验证 terminal 工具正常调度**
  创建 `tests/test_terminal_tool_integrated.py`：
  ```python
  import pytest
  from dojoagents.tools.registry import ToolRegistry
  from dojoagents.tools.executor import ToolExecutor
  from dojoagents.tools.sandbox import SandboxPolicy
  from dojoagents.agent.models import ToolCall
  from dojoagents.tools.terminal_tool import get_terminal_spec

  @pytest.mark.asyncio
  async def test_integrated_terminal_tool_call():
      registry = ToolRegistry()
      spec = get_terminal_spec(SandboxPolicy(allowed_commands=["echo"]))
      registry.register(spec)
      
      executor = ToolExecutor(registry, SandboxPolicy())
      tool_call = ToolCall(id="tc-1", name="terminal", arguments={"command": "echo 'dojo terminal test'"})
      
      result = await executor.execute_one(tool_call)
      assert result.ok
      assert "dojo terminal test" in result.content
  ```

- [ ] **Step 2: 运行测试以验证失败**
  运行：`pytest tests/test_terminal_tool_integrated.py`
  预期：失败，因为 `terminal` 尚未被导出和注册。

- [ ] **Step 3: 编写 `terminal_tool.py` 封装与注册机制**
  新建 `dojoagents/tools/terminal_tool.py`：
  ```python
  import json
  from dojoagents.tools.registry import ToolSpec
  from dojoagents.tools.environments.local import LocalEnvironment
  from dojoagents.tools.sandbox import SandboxPolicy

  async def handle_terminal(args: dict, policy: SandboxPolicy) -> dict:
      command = args.get("command")
      env = LocalEnvironment(policy=policy)
      # 真实地执行命令
      raw_res = await env.execute(command)
      return {
          "content": raw_res.get("output", ""),
          "metadata": {"exit_code": raw_res.get("exit_code", 0)}
      }

  def get_terminal_spec(policy: SandboxPolicy) -> ToolSpec:
      return ToolSpec(
          name="terminal",
          description="Execute shell commands on a Linux environment.",
          parameters={
              "type": "object",
              "properties": {
                  "command": {"type": "string", "description": "The command to execute"}
              },
              "required": ["command"]
          },
          handler=lambda args: handle_terminal(args, policy)
      )
  ```

- [ ] **Step 4: 将 `terminal` 工具注册到 `runtime.py`**
  修改 `dojoagents/agent/runtime.py` 的 `from_config_store` 方法，导入并向 `tool_registry` 注册 `terminal`。
  定位修改点：在注册 `SkillsListTool` 的后面增加一行：
  ```python
  from dojoagents.tools.terminal_tool import get_terminal_spec
  tool_registry.register(get_terminal_spec(SandboxPolicy(
      allowed_roots=config.tools.sandbox.allowed_roots,
      allow_network=config.tools.sandbox.allow_network,
      allowed_commands=config.tools.sandbox.allowed_commands,
      timeout_seconds=config.tools.sandbox.timeout_seconds,
  )))
  ```

- [ ] **Step 5: 验证集成测试通过并 Commit**
  运行：`pytest tests/test_terminal_tool_integrated.py`
  预期：PASS。
  运行：
  ```bash
  git add dojoagents/tools/terminal_tool.py dojoagents/agent/runtime.py tests/test_terminal_tool_integrated.py
  git commit -m "feat: integrate terminal tool into DojoAgents runtime registry"
  ```

---

### Task 5: 协程化 PTC RPC 机制与代码执行集成

**Files:**
- Create: `dojoagents/tools/code_execution_tool.py`
- Modify: `dojoagents/agent/runtime.py`
- Test: `tests/test_code_execution_ptc.py`

- [ ] **Step 1: 编写测试用例验证 python 代码执行反向 rpc 调度**
  创建 `tests/test_code_execution_ptc.py`：
  ```python
  import pytest
  import tempfile
  import os
  from dojoagents.tools.registry import ToolRegistry
  from dojoagents.tools.executor import ToolExecutor
  from dojoagents.tools.sandbox import SandboxPolicy
  from dojoagents.agent.models import ToolCall
  from dojoagents.tools.code_execution_tool import get_code_execution_spec
  from dojoagents.tools.terminal_tool import get_terminal_spec

  @pytest.mark.asyncio
  async def test_code_execution_calls_terminal_via_rpc():
      registry = ToolRegistry()
      policy = SandboxPolicy(allowed_commands=["echo", "python3"])
      registry.register(get_terminal_spec(policy))
      
      # 注册 execute_code 核心工具
      spec = get_code_execution_spec(registry, policy)
      registry.register(spec)
      
      executor = ToolExecutor(registry, policy)
      
      # 编写一个 Python 脚本，通过 rpc 调用 terminal 执行 echo 
      code = (
          "import hermes_tools\n"
          "res = hermes_tools.terminal('echo rpc-ok')\n"
          "print('ScriptOut:', res.get('content', '').strip())\n"
      )
      
      tool_call = ToolCall(id="tc-code", name="execute_code", arguments={"code": code})
      result = await executor.execute_one(tool_call)
      assert result.ok
      assert "ScriptOut: rpc-ok" in result.content
  ```

- [ ] **Step 2: 运行测试以验证失败**
  运行：`pytest tests/test_code_execution_ptc.py`
  预期：失败，因为 `execute_code` 模块与 rpc 层尚未建立。

- [ ] **Step 3: 编写原生异步 RPC 服务与 `code_execution_tool.py` 实现**
  新建 `dojoagents/tools/code_execution_tool.py`：
  ```python
  import asyncio
  import json
  import os
  import tempfile
  from dojoagents.tools.registry import ToolSpec
  from dojoagents.agent.models import ToolCall

  class AsyncCodeExecutionRPC:
      def __init__(self, socket_path: str, tool_registry):
          self.socket_path = socket_path
          self.tool_registry = tool_registry
          self.server = None

      async def start(self):
          self.server = await asyncio.start_unix_server(self.handle_client, path=self.socket_path)

      async def handle_client(self, reader, writer):
          try:
              while True:
                  line = await reader.readline()
                  if not line:
                      break
                  request = json.loads(line.decode("utf-8"))
                  tool_name = request.get("tool")
                  args = request.get("args", {})
                  
                  spec = self.tool_registry.get(tool_name)
                  if spec:
                      # 异步调度工具
                      raw_res = await spec.handler(args)
                      response = {"ok": True, "content": raw_res.get("content", ""), "error": None}
                  else:
                      response = {"ok": False, "content": "", "error": f"Tool '{tool_name}' not registered"}
                      
                  writer.write((json.dumps(response) + "\n").encode("utf-8"))
                  await writer.drain()
          except Exception as exc:
              pass
          finally:
              writer.close()

      async def stop(self):
          if self.server:
              self.server.close()
              await self.server.wait_closed()
              if os.path.exists(self.socket_path):
                  try:
                      os.unlink(self.socket_path)
                  except OSError:
                      pass

  async def handle_code_execution(args: dict, tool_registry, policy) -> dict:
      code_content = args.get("code")
      session_id = os.urandom(6).hex()
      socket_path = f"/tmp/dojo-rpc-{session_id}.sock"
      
      # 1. 启动异步 RPC Server 监听
      rpc_server = AsyncCodeExecutionRPC(socket_path, tool_registry)
      await rpc_server.start()
      
      # 2. 动态生成 hermes_tools 桩模块文件
      temp_dir = tempfile.mkdtemp()
      stub_file = os.path.join(temp_dir, "hermes_tools.py")
      stub_code = f"""
  import socket, json, os
  def terminal(command):
      s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
      s.connect({repr(socket_path)})
      s.sendall(json.dumps({{"tool": "terminal", "args": {{"command": command}}}}).encode('utf-8') + b'\\n')
      res = json.loads(s.recv(65536).decode('utf-8'))
      s.close()
      return res
  """
      with open(stub_file, "w", encoding="utf-8") as f:
          f.write(stub_code)
          
      # 3. 将 LLM 脚本写到文件并异步执行
      script_file = os.path.join(temp_dir, "script.py")
      with open(script_file, "w", encoding="utf-8") as f:
          f.write(code_content)
          
      env = os.environ.copy()
      env["PYTHONPATH"] = temp_dir
      
      proc = await asyncio.create_subprocess_exec(
          "python3", script_file,
          stdout=asyncio.subprocess.PIPE,
          stderr=asyncio.subprocess.STDOUT,
          env=env
      )
      
      try:
          stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=30.0)
          output = stdout.decode("utf-8", errors="replace")
      finally:
          await rpc_server.stop()
          # 清除临时文件
          for filename in ["hermes_tools.py", "script.py"]:
              try:
                  os.unlink(os.path.join(temp_dir, filename))
              except OSError:
                  pass
          os.rmdir(temp_dir)
          
      return {
          "content": output,
          "metadata": {"exit_code": proc.returncode}
      }

  def get_code_execution_spec(tool_registry, policy: SandboxPolicy) -> ToolSpec:
      return ToolSpec(
          name="execute_code",
          description="Execute Python scripts and interact with quantitative tools.",
          parameters={
              "type": "object",
              "properties": {
                  "code": {"type": "string", "description": "Python code to execute"}
              },
              "required": ["code"]
          },
          handler=lambda args: handle_code_execution(args, tool_registry, policy)
      )
  ```

- [ ] **Step 4: 将 `execute_code` 注册到 runtime**
  修改 `dojoagents/agent/runtime.py`。在注册 `terminal` 后面增加一行：
  ```python
  from dojoagents.tools.code_execution_tool import get_code_execution_spec
  tool_registry.register(get_code_execution_spec(tool_registry, SandboxPolicy(
      allowed_roots=config.tools.sandbox.allowed_roots,
      allow_network=config.tools.sandbox.allow_network,
      allowed_commands=config.tools.sandbox.allowed_commands,
      timeout_seconds=config.tools.sandbox.timeout_seconds,
  )))
  ```

- [ ] **Step 5: 验证测试通过并 Commit**
  运行：`pytest tests/test_code_execution_ptc.py`
  预期：PASS。
  运行：
  ```bash
  git add dojoagents/tools/code_execution_tool.py dojoagents/agent/runtime.py tests/test_code_execution_ptc.py
  git commit -m "feat: implement AsyncCodeExecutionRPC and execute_code tool"
  ```
