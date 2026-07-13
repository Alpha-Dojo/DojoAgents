from __future__ import annotations

import json
from pathlib import Path

import pytest

from dojoagents.agent.models import ToolCall
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.process_registry import WriteSessionFileGuardContext, active_write_session_file_guard
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy
from dojoagents.tools.session_file_names import validate_output_filename
from dojoagents.tools.session_file_tool import (
    get_write_session_file_spec,
    write_session_file,
)


def test_validate_output_filename_rejects_directories() -> None:
    with pytest.raises(ValueError, match="basename"):
        validate_output_filename("../escape.json")


def test_write_session_file_writes_json(tmp_path: Path) -> None:
    payload = write_session_file(
        sessions_root=tmp_path,
        session_id="sess-1",
        filename="analysis.json",
        content={"items": [{"ticker": "NVDA"}]},
        fmt="json",
    )
    target = Path(payload["path"])
    assert target.exists()
    assert payload["bytes_written"] > 0
    assert json.loads(target.read_text(encoding="utf-8"))["items"][0]["ticker"] == "NVDA"


def test_write_session_file_writes_jsonl(tmp_path: Path) -> None:
    payload = write_session_file(
        sessions_root=tmp_path,
        session_id="sess-1",
        filename="rows.jsonl",
        content=[{"a": 1}, {"b": 2}],
        fmt="jsonl",
    )
    lines = Path(payload["path"]).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["a"] == 1


@pytest.mark.asyncio
async def test_write_session_file_tool_returns_path(tmp_path: Path) -> None:
    token = active_write_session_file_guard.set(
        WriteSessionFileGuardContext(
            llm_provider=None,
            model="test-model",
            enabled=False,
        )
    )
    try:
        registry = ToolRegistry()
        registry.register(get_write_session_file_spec(tmp_path))
        executor = ToolExecutor(registry, SandboxPolicy(timeout_seconds=5))

        result = await executor.execute_one(
            ToolCall(
                id="call-1",
                name="write_session_file",
                arguments={
                    "filename": "report.json",
                    "content": {"ok": True},
                    "format": "json",
                },
            ),
            session_id="sess-abc",
        )
    finally:
        active_write_session_file_guard.reset(token)

    assert result.ok is True
    assert result.data["path"].endswith("sess-abc/outputs/report.json")
    assert Path(result.data["path"]).exists()


@pytest.mark.asyncio
async def test_terminal_nonzero_exit_code_marks_tool_failed() -> None:
    from dojoagents.tools.terminal_tool import get_terminal_spec

    registry = ToolRegistry()
    registry.register(get_terminal_spec(SandboxPolicy()))
    executor = ToolExecutor(registry, SandboxPolicy())

    result = await executor.execute_one(
        ToolCall(id="call-1", name="terminal", arguments={"command": "exit 42"}),
    )

    assert result.ok is False
    assert result.metadata.get("exit_code") == 42
    assert "42" in result.error


@pytest.mark.asyncio
async def test_execute_code_can_call_write_session_file_via_rpc(tmp_path: Path) -> None:
    from dojoagents.tools.code_execution_tool import get_code_execution_spec

    token = active_write_session_file_guard.set(
        WriteSessionFileGuardContext(
            llm_provider=None,
            model="test-model",
            enabled=False,
        )
    )
    try:
        registry = ToolRegistry()
        policy = SandboxPolicy()
        registry.register(get_write_session_file_spec(tmp_path))
        registry.register(get_code_execution_spec(registry, policy, sessions_root=tmp_path))
        executor = ToolExecutor(registry, policy)

        code = """
import dojo_tools
res = dojo_tools.write_session_file(
    "chain.json",
    {"nodes": [{"id": "N001"}]},
    format="json",
)
print("PATH:", dojo_tools.tool_json(res)["path"])
"""
        result = await executor.execute_one(
            ToolCall(id="call-1", name="execute_code", arguments={"code": code}),
            session_id="sess-chain",
        )
    finally:
        active_write_session_file_guard.reset(token)

    assert result.ok is True
    assert "PATH:" in result.content
    assert isinstance(result.data, dict)
    assert result.data.get("path", "").endswith("chain.json")
    assert result.data.get("filename") == "chain.json"
    files = result.data.get("session_output_files")
    assert isinstance(files, list) and len(files) == 1
    written = tmp_path / "sess-chain" / "outputs" / "chain.json"
    assert written.exists()
    assert json.loads(written.read_text(encoding="utf-8"))["nodes"][0]["id"] == "N001"


@pytest.mark.asyncio
async def test_execute_code_nonzero_exit_code_marks_tool_failed(tmp_path: Path) -> None:
    from dojoagents.tools.code_execution_tool import get_code_execution_spec

    registry = ToolRegistry()
    policy = SandboxPolicy()
    registry.register(get_code_execution_spec(registry, policy, sessions_root=tmp_path))
    executor = ToolExecutor(registry, policy)

    result = await executor.execute_one(
        ToolCall(
            id="call-1",
            name="execute_code",
            arguments={"code": "import sys\nprint('boom')\nsys.exit(3)\n"},
        ),
        session_id="sess-exec",
    )

    assert result.ok is False
    assert result.metadata.get("exit_code") == 3
    assert "boom" in result.content


@pytest.mark.asyncio
async def test_execute_code_writes_large_json_without_rpc_limit(tmp_path: Path) -> None:
    from dojoagents.tools.code_execution_tool import get_code_execution_spec

    token = active_write_session_file_guard.set(
        WriteSessionFileGuardContext(
            llm_provider=None,
            model="test-model",
            enabled=False,
        )
    )
    try:
        registry = ToolRegistry()
        policy = SandboxPolicy()
        registry.register(get_write_session_file_spec(tmp_path))
        registry.register(get_code_execution_spec(registry, policy, sessions_root=tmp_path))
        executor = ToolExecutor(registry, policy)

        large_graph = {
            "nodes": [{"id": f"N{i:04d}", "label": "x" * 200} for i in range(400)],
            "edges": [{"source": f"N{i:04d}", "target": f"N{i + 1:04d}"} for i in range(399)],
        }
        code = f"""
import dojo_tools
graph = {json.dumps(large_graph, ensure_ascii=False)}
res = dojo_tools.write_session_file("large_graph.json", graph, format="json")
print("PATH:", dojo_tools.tool_json(res)["path"])
"""
        result = await executor.execute_one(
            ToolCall(id="call-large", name="execute_code", arguments={"code": code}),
            session_id="sess-large",
        )
    finally:
        active_write_session_file_guard.reset(token)

    assert result.ok is True
    written = tmp_path / "sess-large" / "outputs" / "large_graph.json"
    assert written.exists()
    assert written.stat().st_size > 100_000
