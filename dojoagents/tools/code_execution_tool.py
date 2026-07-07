import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

from dojoagents.agent.tool_result_artifacts import (
    ToolResultArtifactStore,
    extract_viz_payload_from_content,
    get_tool_artifact_schema_hint,
    get_viz_hint_for_payload,
)
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

# asyncio StreamReader.readline() defaults to 64 KiB per line; execute_code RPC carries
# full tool args/responses as one JSON line and must support large write_session_file payloads.
RPC_MAX_MESSAGE_BYTES = 32 * 1024 * 1024


class RpcJsonLineProtocol:
    """Buffered newline-delimited JSON framing for execute_code RPC."""

    def __init__(self, reader: asyncio.StreamReader, *, max_size: int = RPC_MAX_MESSAGE_BYTES) -> None:
        self._reader = reader
        self._buffer = bytearray()
        self._max_size = max_size

    async def read_message(self) -> dict[str, Any] | None:
        while True:
            newline_at = self._buffer.find(b"\n")
            if newline_at >= 0:
                line = bytes(self._buffer[:newline_at])
                del self._buffer[: newline_at + 1]
                if not line.strip():
                    continue
                return json.loads(line.decode("utf-8"))

            chunk = await self._reader.read(65536)
            if not chunk:
                if not self._buffer:
                    return None
                line = bytes(self._buffer)
                self._buffer.clear()
                if not line.strip():
                    return None
                return json.loads(line.decode("utf-8"))

            self._buffer.extend(chunk)
            if len(self._buffer) > self._max_size:
                raise ValueError(f"execute_code RPC message exceeds {self._max_size} bytes")

    @staticmethod
    def encode_message(payload: dict[str, Any]) -> bytes:
        return (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")


def _slim_rpc_tool_response(tool_name: str, raw_res: dict[str, Any]) -> dict[str, Any]:
    if tool_name != "write_session_file":
        return {
            "ok": True,
            "content": raw_res.get("content", ""),
            "data": raw_res.get("data"),
            "error": None,
        }

    data = raw_res.get("data")
    if not isinstance(data, dict):
        return {
            "ok": True,
            "content": raw_res.get("content", ""),
            "data": data,
            "error": None,
        }

    slim = {
        "ok": data.get("ok", True),
        "path": data.get("path"),
        "output_dir": data.get("output_dir"),
        "bytes_written": data.get("bytes_written"),
        "filename": data.get("filename"),
        "format": data.get("format"),
        "message": data.get("message"),
    }
    return {
        "ok": True,
        "content": json.dumps(slim, ensure_ascii=False),
        "data": slim,
        "error": None,
    }


def _session_output_entry_from_payload(payload: Any) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    filename = str(payload.get("filename") or "").strip()
    path = str(payload.get("path") or "").strip()
    if not filename or not path:
        return None
    entry: dict[str, Any] = {"filename": filename, "path": path}
    bytes_written = payload.get("bytes_written")
    if isinstance(bytes_written, int):
        entry["bytes_written"] = bytes_written
    output_dir = payload.get("output_dir")
    if isinstance(output_dir, str) and output_dir.strip():
        entry["output_dir"] = output_dir.strip()
    return entry


def _merge_session_output_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for entry in entries:
        filename = str(entry.get("filename") or "").strip()
        if filename:
            merged[filename] = entry
    return list(merged.values())


def _load_session_output_manifest(path: str | Path) -> list[dict[str, Any]]:
    manifest_path = Path(path)
    if not manifest_path.is_file():
        return []
    entries: list[dict[str, Any]] = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        entry = _session_output_entry_from_payload(payload)
        if entry is not None:
            entries.append(entry)
    return _merge_session_output_entries(entries)


def _build_execute_code_data(session_output_files: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not session_output_files:
        return None
    data: dict[str, Any] = {"session_output_files": session_output_files}
    data.update(session_output_files[-1])
    return data

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
        self.session_output_files: list[dict[str, Any]] = []

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
        response = _slim_rpc_tool_response(tool_name, raw_res)
        if tool_name == "write_session_file" and response.get("ok"):
            entry = _session_output_entry_from_payload(response.get("data"))
            if entry is not None:
                self.session_output_files = _merge_session_output_entries(
                    [*self.session_output_files, entry],
                )
        return response

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
        data = payload.get("data")
        if not isinstance(data, dict):
            extracted = extract_viz_payload_from_content(str(payload.get("content") or ""))
            if extracted is not None:
                data = extracted
        viz_hint = get_viz_hint_for_payload(data if isinstance(data, dict) else None)
        return {
            "ok": True,
            "content": payload.get("content", ""),
            "data": data,
            "tool_name": str(payload.get("tool_name") or ""),
            "schema_hint": get_tool_artifact_schema_hint(str(payload.get("tool_name") or "")),
            "viz_hint": viz_hint,
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
        protocol = RpcJsonLineProtocol(reader)
        try:
            while True:
                request = await protocol.read_message()
                if request is None:
                    break
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

                writer.write(RpcJsonLineProtocol.encode_message(response))
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
    sessions_root: str | Path = "",
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
    session_output_manifest = os.path.join(temp_dir, ".session_outputs.jsonl")
    stub_file = os.path.join(temp_dir, "dojo_tools.py")
    tool_names = [spec.name for spec in tool_registry.all()]
    stub_code = build_dojo_tools_stub_code(socket_path=socket_path, tool_names=tool_names)
    with open(stub_file, "w", encoding="utf-8") as handle:
        handle.write(stub_code)

    script_file = os.path.join(temp_dir, "script.py")
    with open(script_file, "w", encoding="utf-8") as handle:
        handle.write(code_content)

    env = os.environ.copy()
    env["DOJO_SESSION_OUTPUT_MANIFEST"] = session_output_manifest
    try:
        import dojoagents

        pkg_root = str(Path(dojoagents.__file__).resolve().parent.parent)
        env["PYTHONPATH"] = os.pathsep.join([temp_dir, pkg_root, env.get("PYTHONPATH", "")])
    except ImportError:
        env["PYTHONPATH"] = temp_dir
    env["PYTHONIOENCODING"] = "utf-8"
    if agent_session_id:
        env["DOJO_SESSION_ID"] = agent_session_id
        if sessions_root:
            from dojoagents.dashboard.services.session_inputs import resolve_session_input_dir
            from dojoagents.tools.session_file_tool import resolve_session_output_dir

            sessions_root_path = Path(sessions_root).expanduser().resolve()
            output_dir = resolve_session_output_dir(sessions_root_path, agent_session_id)
            output_dir.mkdir(parents=True, exist_ok=True)
            input_dir = resolve_session_input_dir(sessions_root_path, agent_session_id)
            input_dir.mkdir(parents=True, exist_ok=True)
            env["DOJO_SESSIONS_ROOT"] = str(sessions_root_path)
            env["DOJO_SESSION_OUTPUT_DIR"] = str(output_dir)
            env["DOJO_SESSION_INPUT_DIR"] = str(input_dir.resolve())
    proc = await asyncio.create_subprocess_exec(
        "python",
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

    session_output_files = _merge_session_output_entries(
        [
            *_load_session_output_manifest(session_output_manifest),
            *rpc_server.session_output_files,
        ],
    )
    for filename in ["dojo_tools.py", "script.py", ".session_outputs.jsonl"]:
        try:
            os.unlink(os.path.join(temp_dir, filename))
        except OSError:
            pass
    try:
        os.rmdir(temp_dir)
    except OSError:
        pass

    result: dict[str, Any] = {"content": output, "metadata": {"exit_code": proc.returncode}}
    execute_data = _build_execute_code_data(session_output_files)
    if execute_data is not None:
        result["data"] = execute_data
    return result


def get_code_execution_spec(
    tool_registry,
    policy: SandboxPolicy,
    *,
    artifact_store: ToolResultArtifactStore | None = None,
    max_tool_calls: int = 20,
    sessions_root: str | Path = "",
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
            sessions_root=sessions_root,
        )

    exposed = [spec.name for spec in tool_registry.all() if spec.name not in {"execute_code", "code_execution"}]
    sample_tools = ", ".join(exposed[:8])
    if len(exposed) > 8:
        sample_tools += ", ..."

    return ToolSpec(
        name="execute_code",
        description=(
            "Execute Python for dojo_tools batch orchestration or pandas/numpy computation on fetched data. "
            "NEVER hardcode market prices or financial rows — fetch data with dojo_tools RPC helpers "
            f"(e.g. {sample_tools}) or `dojo_tools.load_tool_result(call_id)` for persisted large tool outputs. "
            "Use `dojo_tools.tool_json(res)` to parse JSON tool payloads. "
            "After `load_tool_result`, read `res['schema_hint']` — use "
            "`df = pd.DataFrame(dojo_tools.tool_table(res))` (columns come from "
            "`schema_hint['row_fields']`; do NOT invent column names). "
            "Multi-table payloads: `dojo_tools.tool_table(res, '<table>')` using keys in "
            "`schema_hint['tables']`. "
            "e.g. `df = pd.DataFrame(dojo_tools.tool_rows(res))` after load_tool_result; "
            "get_ticker_price_trends rows are in `klines` with field `datetime` (not `data` or `bar_time`). "
            "After computation, print structured VIZ_DATA JSON when a chart is needed; the tool result "
            "includes a viz_hint footer for agent_viz_build. "
            "To save JSON/JSONL/text deliverables, call dojo_tools.write_session_file(...) and print the "
            "returned path — do NOT use terminal heredoc. "
            "DOJO_SESSION_OUTPUT_DIR is set to the current session outputs directory. "
            "FORBIDDEN: using this tool to print ASCII diagrams, schema docs, design proposals, or formatted "
            "text reports — write those directly in the assistant reply instead."
        ),
        parameters={
            "type": "object",
            "properties": {"code": {"type": "string", "description": "Python code to execute"}},
            "required": ["code"],
        },
        handler=_handler,
    )
