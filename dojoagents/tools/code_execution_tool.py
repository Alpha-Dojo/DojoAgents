import asyncio
import json
import os
import sys
import tempfile
from typing import Any

from dojoagents.agent.tool_result_artifacts import ToolResultArtifactStore
from dojoagents.logging import get_logger
from dojoagents.tools.dojo_tools_stub import (
    HERMES_INTERNAL_LIST_TOOLS,
    HERMES_INTERNAL_LOAD_TOOL,
    build_dojo_tools_stub_code,
)
from dojoagents.tools.process_registry import active_session_id
from dojoagents.tools.registry import ToolSpec
from dojoagents.tools.sandbox import SandboxPolicy

LOGGER = get_logger(__name__)

if sys.platform == "win32":
    import dojoagents.tools.af_unix_asyncio_compat as af_unix_asyncio_compat

    start_unix_server = af_unix_asyncio_compat.start_unix_server
else:
    start_unix_server = asyncio.start_unix_server


class AsyncCodeExecutionRPC:
    def __init__(
        self,
        socket_path: str,
        tool_registry,
        *,
        max_tool_calls: int = 20,
        artifact_store: ToolResultArtifactStore | None = None,
        agent_session_id: str = "",
    ):
        self.socket_path = socket_path
        self.tool_registry = tool_registry
        self.max_tool_calls = max_tool_calls
        self.artifact_store = artifact_store
        self.agent_session_id = agent_session_id
        self.server = None
        self.tool_call_counter = 0

    async def start(self):
        self.server = await start_unix_server(self.handle_client, path=self.socket_path)

    async def _dispatch_tool(self, tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        if tool_name == HERMES_INTERNAL_LOAD_TOOL:
            return self._load_tool_result(args)
        if tool_name == HERMES_INTERNAL_LIST_TOOLS:
            return self._list_tool_results()

        spec = self.tool_registry.get(tool_name)
        if spec is None:
            return {"ok": False, "content": "", "data": None, "error": f"Tool '{tool_name}' not registered"}
        raw_res = await spec.handler(dict(args or {}))
        if isinstance(raw_res, str):
            raw_res = {"content": raw_res}
        return {
            "ok": True,
            "content": raw_res.get("content", ""),
            "data": raw_res.get("data"),
            "error": None,
        }

    def _load_tool_result(self, args: dict[str, Any]) -> dict[str, Any]:
        if self.artifact_store is None or not self.agent_session_id:
            return {
                "ok": False,
                "content": "",
                "data": None,
                "error": "Tool result artifacts are unavailable for this execute_code run.",
            }
        call_id = str(args.get("call_id") or "").strip()
        if not call_id:
            return {"ok": False, "content": "", "data": None, "error": "call_id is required"}
        payload = self.artifact_store.load(self.agent_session_id, call_id)
        if payload is None:
            return {
                "ok": False,
                "content": "",
                "data": None,
                "error": f"Tool result artifact not found for call_id={call_id}",
            }
        return {
            "ok": True,
            "content": payload.get("content", ""),
            "data": payload.get("data"),
            "error": None,
        }

    def _list_tool_results(self) -> dict[str, Any]:
        if self.artifact_store is None or not self.agent_session_id:
            return {
                "ok": False,
                "content": "",
                "data": None,
                "error": "Tool result artifacts are unavailable for this execute_code run.",
            }
        rows = self.artifact_store.list_summaries(self.agent_session_id)
        content = json.dumps({"items": rows}, ensure_ascii=False, indent=2)
        return {"ok": True, "content": content, "data": {"items": rows}, "error": None}

    async def handle_client(self, reader, writer):
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                request = json.loads(line.decode("utf-8"))
                tool_name = request.get("tool")
                args = request.get("args", {})

                if self.tool_call_counter >= self.max_tool_calls:
                    response = {
                        "ok": False,
                        "content": "",
                        "data": None,
                        "error": f"Tool call limit reached ({self.max_tool_calls}). No more tool calls allowed.",
                    }
                else:
                    self.tool_call_counter += 1
                    try:
                        response = await self._dispatch_tool(str(tool_name or ""), dict(args or {}))
                    except Exception as exc:
                        LOGGER.exception("execute_code RPC tool failed: %s", tool_name)
                        response = {"ok": False, "content": "", "data": None, "error": str(exc)}

                writer.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
                await writer.drain()
        except Exception:
            LOGGER.exception("execute_code RPC client handler failed")
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


async def handle_code_execution(
    args: dict,
    tool_registry,
    policy,
    *,
    max_tool_calls: int = 20,
    artifact_store: ToolResultArtifactStore | None = None,
    agent_session_id: str = "",
) -> dict:
    code_content = args.get("code")
    rpc_session_id = os.urandom(6).hex()
    socket_path = os.path.join(tempfile.gettempdir(), f"dojo-rpc-{rpc_session_id}.sock")

    rpc_server = AsyncCodeExecutionRPC(
        socket_path,
        tool_registry,
        max_tool_calls=max_tool_calls,
        artifact_store=artifact_store,
        agent_session_id=agent_session_id,
    )
    await rpc_server.start()

    temp_dir = tempfile.mkdtemp()
    stub_file = os.path.join(temp_dir, "dojo_tools.py")
    tool_names = [spec.name for spec in tool_registry.all()]
    stub_code = build_dojo_tools_stub_code(socket_path=socket_path, tool_names=tool_names)
    with open(stub_file, "w", encoding="utf-8") as handle:
        handle.write(stub_code)

    script_file = os.path.join(temp_dir, "script.py")
    with open(script_file, "w", encoding="utf-8") as handle:
        handle.write(code_content)

    env = os.environ.copy()
    env["PYTHONPATH"] = temp_dir

    proc = await asyncio.create_subprocess_exec(
        "python3",
        script_file,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        env=env,
    )

    try:
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=300.0)
        output = stdout.decode("utf-8", errors="replace")
    finally:
        await rpc_server.stop()
        for filename in ["dojo_tools.py", "script.py"]:
            try:
                os.unlink(os.path.join(temp_dir, filename))
            except OSError:
                pass
        try:
            os.rmdir(temp_dir)
        except OSError:
            pass

    return {"content": output, "metadata": {"exit_code": proc.returncode}}


def get_code_execution_spec(
    tool_registry,
    policy: SandboxPolicy,
    *,
    artifact_store: ToolResultArtifactStore | None = None,
    max_tool_calls: int = 20,
) -> ToolSpec:
    async def _handler(args: dict[str, Any]) -> dict[str, Any]:
        session_id = active_session_id.get() or str(args.get("session_id") or "")
        return await handle_code_execution(
            args,
            tool_registry,
            policy,
            max_tool_calls=max_tool_calls,
            artifact_store=artifact_store,
            agent_session_id=session_id,
        )

    exposed = [spec.name for spec in tool_registry.all() if spec.name not in {"execute_code", "code_execution"}]
    sample_tools = ", ".join(exposed[:8])
    if len(exposed) > 8:
        sample_tools += ", ..."

    return ToolSpec(
        name="execute_code",
        description=(
            "Execute Python scripts with access to registered DojoAgents tools via `import dojo_tools`. "
            "NEVER hardcode market prices or financial rows — fetch data with dojo_tools RPC helpers "
            f"(e.g. {sample_tools}) or `dojo_tools.load_tool_result(call_id)` for persisted large tool outputs. "
            "Use `dojo_tools.tool_json(res)` to parse JSON tool payloads."
        ),
        parameters={
            "type": "object",
            "properties": {"code": {"type": "string", "description": "Python code to execute"}},
            "required": ["code"],
        },
        handler=_handler,
    )
