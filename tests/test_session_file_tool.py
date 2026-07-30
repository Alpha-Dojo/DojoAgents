from __future__ import annotations

import json
from pathlib import Path

import pytest

from dojoagents.agent.models import ToolCall
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.process_registry import WriteSessionFileGuardContext, active_write_session_file_guard
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy
from dojoagents.sessions.identifiers import validate_output_filename
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
    assert not target.with_name(target.name + ".lock").exists()
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
async def test_read_prefers_task_disk_for_active_task_even_with_session_service(tmp_path: Path) -> None:
    """Pipeline handoff: upstream pack lives on task disk; session object may be absent."""
    from dojoagents.config.models import SessionsConfig
    from dojoagents.sessions.blobs.file import FileBlobStore
    from dojoagents.sessions.models import SessionCreateSpec, SessionPrincipal
    from dojoagents.sessions.service import SessionService
    from dojoagents.sessions.stores.file import FileSessionStore
    from dojoagents.tools.process_registry import active_session_id, active_session_principal
    from dojoagents.tools.session_file_tool import get_read_session_output_spec, write_session_file

    task_root = tmp_path / "task-outputs"
    write_session_file(
        sessions_root=tmp_path / "unused-sessions",
        session_id="sess-pipe",
        filename="market_news_raw_pack_2026-07-27.json",
        content={
            "trading_date": "2026-07-27",
            "window_start_date": "2026-07-27",
            "window_end_date": "2026-07-27",
            "sector_moves": [],
            "news_items": [],
            "sectors_without_news": [],
        },
        fmt="json",
        task_output_root=task_root,
        request_metadata={
            "active_task": {
                "task_id": "sector-attribution",
                "outputs": [{"filename": "market_news_raw_pack_2026-07-27.json", "format": "json"}],
            }
        },
    )

    store = FileSessionStore(tmp_path / "sessions", cursor_secret=b"secret")
    blobs = FileBlobStore(tmp_path / "blobs")
    await store.startup()
    await blobs.startup()
    service = SessionService(store=store, blob_store=blobs, config=SessionsConfig())
    principal = SessionPrincipal("alice")
    await service.create_session(principal, SessionCreateSpec("sess-pipe", "financial", "1.0.0", 1))

    read = get_read_session_output_spec(
        tmp_path / "sessions",
        task_output_root=task_root,
        session_service=service,
    )
    session_token = active_session_id.set("sess-pipe")
    principal_token = active_session_principal.set(principal)
    guard_token = active_write_session_file_guard.set(
        WriteSessionFileGuardContext(
            llm_provider=None,
            model="test-model",
            enabled=False,
            request_metadata={
                "active_task": {
                    "task_id": "event-trigger",
                    "inputs": [
                        {
                            "filename": "market_news_raw_pack_2026-07-27.json",
                            "source_task_id": "sector-attribution",
                            "required": True,
                        }
                    ],
                }
            },
        )
    )
    try:
        loaded = await read.handler({"filename": "market_news_raw_pack_2026-07-27.json"})
    finally:
        active_write_session_file_guard.reset(guard_token)
        active_session_principal.reset(principal_token)
        active_session_id.reset(session_token)
        await blobs.shutdown()
        await store.shutdown()

    assert loaded["data"]["storage_kind"] == "task"
    assert loaded["data"]["data"]["trading_date"] == "2026-07-27"
    assert "sector-attribution" in str(loaded["data"]["path"])


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


def test_write_rejects_json_append(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="append is not supported for format=json"):
        write_session_file(
            sessions_root=tmp_path,
            session_id="sess-1",
            filename="a.json",
            content={"a": 1},
            fmt="json",
            append=True,
        )


def test_write_jsonl_append_preserves_rows(tmp_path: Path) -> None:
    write_session_file(
        sessions_root=tmp_path,
        session_id="sess-1",
        filename="rows.jsonl",
        content=[{"a": 1}],
        fmt="jsonl",
    )
    write_session_file(
        sessions_root=tmp_path,
        session_id="sess-1",
        filename="rows.jsonl",
        content=[{"b": 2}],
        fmt="jsonl",
        append=True,
    )
    lines = (tmp_path / "sess-1" / "outputs" / "rows.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line) for line in lines] == [{"a": 1}, {"b": 2}]


def test_read_truncates_large_content(tmp_path: Path) -> None:
    from dojoagents.tools.session_file_tool import read_session_output

    big = "x" * 5_000
    write_session_file(
        sessions_root=tmp_path,
        session_id="sess-1",
        filename="big.txt",
        content=big,
        fmt="text",
    )
    payload = read_session_output(
        sessions_root=tmp_path,
        session_id="sess-1",
        filename="big.txt",
        max_chars=100,
    )
    assert payload["truncated"] is True
    assert payload["data"] is None
    assert len(payload["content"]) == 100
    assert payload["content_chars"] == 5_000


def test_read_accepts_absolute_path_as_basename(tmp_path: Path) -> None:
    from dojoagents.tools.session_file_tool import read_session_output

    write_session_file(
        sessions_root=tmp_path,
        session_id="sess-1",
        filename="pack.json",
        content={"ok": True},
        fmt="json",
    )
    payload = read_session_output(
        sessions_root=tmp_path,
        session_id="sess-1",
        filename=str(tmp_path / "sess-1" / "outputs" / "pack.json"),
    )
    assert payload["filename"] == "pack.json"
    assert payload["data"]["ok"] is True


def test_overwrite_uses_same_companion_lock_as_append(tmp_path: Path) -> None:
    from concurrent.futures import ThreadPoolExecutor

    write_session_file(
        sessions_root=tmp_path,
        session_id="sess-1",
        filename="rows.jsonl",
        content=[{"a": 1}],
        fmt="jsonl",
    )
    target = tmp_path / "sess-1" / "outputs" / "rows.jsonl"
    lock = target.with_name(target.name + ".lock")
    assert not lock.exists()

    def _append(i: int) -> None:
        write_session_file(
            sessions_root=tmp_path,
            session_id="sess-1",
            filename="rows.jsonl",
            content=[{"i": i}],
            fmt="jsonl",
            append=True,
        )

    def _overwrite() -> None:
        write_session_file(
            sessions_root=tmp_path,
            session_id="sess-1",
            filename="rows.jsonl",
            content=[{"final": True}],
            fmt="jsonl",
            append=False,
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        futs = [pool.submit(_append, i) for i in range(20)]
        futs.append(pool.submit(_overwrite))
        for fut in futs:
            fut.result(timeout=10)

    lines = [json.loads(line) for line in target.read_text(encoding="utf-8").splitlines() if line.strip()]
    # Final state is either overwrite-only, or overwrite followed by some appends —
    # never truncated/corrupt JSONL rows.
    assert lines
    assert all(isinstance(row, dict) for row in lines)
    assert not lock.exists()
