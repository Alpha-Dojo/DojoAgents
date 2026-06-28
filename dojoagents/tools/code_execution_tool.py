import asyncio
import json
import os
import tempfile
from dojoagents.tools.registry import ToolSpec
from dojoagents.tools.sandbox import SandboxPolicy


class AsyncCodeExecutionRPC:
    def __init__(self, socket_path: str, tool_registry, max_tool_calls: int = 20):
        self.socket_path = socket_path
        self.tool_registry = tool_registry
        self.max_tool_calls = max_tool_calls
        self.server = None
        self.tool_call_counter = 0

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

                # 超限拦截
                if self.tool_call_counter >= self.max_tool_calls:
                    response = {"ok": False, "content": "", "error": f"Tool call limit reached ({self.max_tool_calls}). No more tool calls allowed."}
                else:
                    spec = self.tool_registry.get(tool_name)
                    if spec:
                        self.tool_call_counter += 1
                        raw_res = await spec.handler(args)
                        response = {"ok": True, "content": raw_res.get("content", ""), "error": None}
                    else:
                        response = {"ok": False, "content": "", "error": f"Tool '{tool_name}' not registered"}

                writer.write((json.dumps(response) + "\n").encode("utf-8"))
                await writer.drain()
        except Exception:
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    async def stop(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            if os.path.exists(self.socket_path):
                try:
                    os.unlink(self.socket_path)
                except OSError:
                    pass


async def handle_code_execution(args: dict, tool_registry, policy, max_tool_calls: int = 20) -> dict:
    code_content = args.get("code")
    session_id = os.urandom(6).hex()
    socket_path = f"/tmp/dojo-rpc-{session_id}.sock"

    # 1. 启动 RPC Server 监听，传入配额限制
    rpc_server = AsyncCodeExecutionRPC(socket_path, tool_registry, max_tool_calls=max_tool_calls)
    await rpc_server.start()

    # 2. 动态生成 hermes_tools 桩模块文件
    temp_dir = tempfile.mkdtemp()
    stub_file = os.path.join(temp_dir, "hermes_tools.py")
    stub_code = f"""
import socket, json, os
def _rpc_call(tool_name, args):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect({repr(socket_path)})
    s.sendall(json.dumps({{"tool": tool_name, "args": args}}).encode('utf-8') + b'\\n')
    res = json.loads(s.recv(65536).decode('utf-8'))
    s.close()
    return res

def terminal(command):
    return _rpc_call("terminal", {{"command": command}})

def read_file(path, offset=1, limit=500):
    return _rpc_call("read_file", {{"path": path, "offset": offset, "limit": limit}})
"""
    with open(stub_file, "w", encoding="utf-8") as f:
        f.write(stub_code)

    # 3. 将 LLM 脚本写到文件并异步执行
    script_file = os.path.join(temp_dir, "script.py")
    with open(script_file, "w", encoding="utf-8") as f:
        f.write(code_content)

    env = os.environ.copy()
    env["PYTHONPATH"] = temp_dir

    proc = await asyncio.create_subprocess_exec("python3", script_file, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT, env=env)

    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300.0)
        output = stdout.decode("utf-8", errors="replace")
    finally:
        await rpc_server.stop()
        for filename in ["hermes_tools.py", "script.py"]:
            try:
                os.unlink(os.path.join(temp_dir, filename))
            except OSError:
                pass
        try:
            os.rmdir(temp_dir)
        except OSError:
            pass

    return {"content": output, "metadata": {"exit_code": proc.returncode}}


def get_code_execution_spec(tool_registry, policy: SandboxPolicy) -> ToolSpec:
    return ToolSpec(
        name="execute_code",
        description="Execute Python scripts and interact with quantitative tools.",
        parameters={"type": "object", "properties": {"code": {"type": "string", "description": "Python code to execute"}}, "required": ["code"]},
        handler=lambda args: handle_code_execution(args, tool_registry, policy, max_tool_calls=policy.timeout_seconds or 20),
    )
