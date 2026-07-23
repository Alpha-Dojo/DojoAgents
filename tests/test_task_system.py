from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from dojoagents.harnesses.built_in.financial.policies.legacy.artifact_synthesis import ArtifactSynthesisHarness
from dojoagents.harnesses.built_in.financial.policies.legacy.tool_orchestrated import ToolOrchestratedHarness
from dojoagents.agent.models import ChatRequest, ToolCall, ToolResult
from dojoagents.harnesses.built_in.financial.policies.legacy_harness import HarnessLoopState
from dojoagents.tasks.activator import TaskActivator, TaskActivationError
from dojoagents.tasks.artifacts import resolve_dated_filename
from dojoagents.tasks.command_router import CommandRouter
from dojoagents.tasks.manager import TaskPromptManager
from dojoagents.tasks.output_paths import resolve_task_output_file
from dojoagents.tasks.pipeline import PipelineRunner
from dojoagents.tasks.schema_validator import TaskOutputValidator
from dojoagents.tools.session_file_tool import read_session_output, write_session_file


@pytest.fixture
def task_roots(tmp_path: Path) -> tuple[Path, Path]:
    repo_root = Path(__file__).resolve().parents[1]
    financial = repo_root / "dojoagents" / "harnesses" / "built_in" / "financial"
    built_in = financial / "tasks" / "definitions"
    pipelines = financial / "pipelines" / "definitions"
    return built_in, pipelines


@pytest.fixture
def task_manager(task_roots: tuple[Path, Path]) -> TaskPromptManager:
    built_in, pipelines = task_roots
    return TaskPromptManager(task_dirs=[built_in], pipeline_dirs=[pipelines])


@pytest.fixture
def task_output_root(tmp_path: Path) -> Path:
    return tmp_path / "task-outputs"


def _task_metadata(task_id: str, *, trading_date: str = "2026-07-02") -> dict[str, Any]:
    return {
        "active_task": {
            "task_id": task_id,
            "params": {"trading_date": trading_date},
        }
    }


def _write_task_file(
    task_output_root: Path,
    task_id: str,
    filename: str,
    content: dict[str, Any],
) -> Path:
    path = resolve_task_output_file(task_output_root, task_id, filename)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


def test_resolve_dated_filename() -> None:
    assert resolve_dated_filename("market_news_raw_pack.json", {"trading_date": "2026-07-03"}) == "market_news_raw_pack_2026-07-03.json"
    assert resolve_dated_filename("market_event_triggers.jsonl", {"trading_date": "2026-07-03"}) == "market_event_triggers_2026-07-03.jsonl"
    assert resolve_dated_filename("market_news_raw_pack.json", {}) == "market_news_raw_pack.json"


def test_task_manager_loads_builtin_tasks(task_manager: TaskPromptManager) -> None:
    assert "sector-attribution" in task_manager.list_tasks()
    assert "event-trigger" in task_manager.list_tasks()
    assert "daily-market-events" in task_manager.list_pipelines()
    spec = task_manager.get_task("sector-attribution")
    assert spec is not None
    assert spec.contract.harness_profile == "tool_orchestrated"
    assert "market_news_raw_pack_2026-07-02.json" in task_manager.build_injection_block(
        ChatRequest(
            message="run",
            user_id="u1",
            session_id="s1",
            metadata={
                "active_task": {
                    "task_id": "sector-attribution",
                    "params": {"trading_date": "2026-07-02"},
                    "harness_profile": "tool_orchestrated",
                    "outputs": [{"filename": "market_news_raw_pack_2026-07-02.json", "format": "json"}],
                }
            },
        )
    )


def test_command_router_activates_task(task_manager: TaskPromptManager, task_output_root: Path) -> None:
    activator = TaskActivator(
        manager=task_manager,
        sessions_root="/tmp",
        task_output_root=str(task_output_root),
        auto_detect=False,
    )
    router = CommandRouter(manager=task_manager, activator=activator, skill_manager=None)
    request = ChatRequest(
        message="/task sector-attribution 2026-07-02",
        user_id="u1",
        session_id="sess-task",
        channel="dashboard",
    )
    processed = router.preprocess(request)
    active = processed.metadata.get("active_task")
    assert isinstance(active, dict)
    assert active["task_id"] == "sector-attribution"
    assert active["params"]["trading_date"] == "2026-07-02"
    assert active["outputs"][0]["filename"] == "market_news_raw_pack_2026-07-02.json"


def test_command_router_activates_pipeline(task_manager: TaskPromptManager, task_output_root: Path) -> None:
    activator = TaskActivator(
        manager=task_manager,
        sessions_root="/tmp",
        task_output_root=str(task_output_root),
        auto_detect=False,
    )
    router = CommandRouter(manager=task_manager, activator=activator, skill_manager=None)
    request = ChatRequest(
        message="/pipeline daily-market-events 2026-07-02",
        user_id="u1",
        session_id="sess-pipe",
        channel="dashboard",
    )
    processed = router.preprocess(request)
    pipeline = processed.metadata.get("pipeline")
    active = processed.metadata.get("active_task")
    assert isinstance(pipeline, dict)
    assert pipeline["id"] == "daily-market-events"
    assert pipeline["step"] == 1
    assert active["task_id"] == "sector-attribution"


def test_event_trigger_requires_raw_pack(
    task_output_root: Path,
    task_manager: TaskPromptManager,
) -> None:
    activator = TaskActivator(
        manager=task_manager,
        sessions_root="/tmp",
        task_output_root=str(task_output_root),
        auto_detect=False,
    )
    request = ChatRequest(
        message="/task event-trigger 2026-07-02",
        user_id="u1",
        session_id="sess-missing",
        channel="dashboard",
    )
    with pytest.raises(TaskActivationError, match="market_news_raw_pack_2026-07-02.json"):
        activator.activate_task(request, task_id="event-trigger", params={"trading_date": "2026-07-02"})


def test_read_and_write_session_output_roundtrip(tmp_path: Path) -> None:
    payload = write_session_file(
        sessions_root=tmp_path,
        session_id="sess-io",
        filename="analysis.json",
        content={"ok": True},
        fmt="json",
    )
    assert payload["ok"] is True
    assert payload["storage_kind"] == "session"
    read_back = read_session_output(
        sessions_root=tmp_path,
        session_id="sess-io",
        filename="analysis.json",
    )
    assert read_back["data"]["ok"] is True


def test_task_mode_writes_to_task_output_root(tmp_path: Path, task_output_root: Path) -> None:
    metadata = _task_metadata("sector-attribution")
    payload = write_session_file(
        sessions_root=tmp_path,
        session_id="sess-io",
        filename="market_news_raw_pack_2026-07-02.json",
        content={
            "trading_date": "2026-07-02",
            "window_start_date": "2026-07-02",
            "window_end_date": "2026-07-02",
            "sector_moves": [],
            "news_items": [],
            "sectors_without_news": [],
        },
        fmt="json",
        task_output_root=task_output_root,
        request_metadata=metadata,
    )
    assert payload["storage_kind"] == "task"
    assert "sector-attribution" in payload["path"]
    assert not (tmp_path / "sess-io" / "outputs" / "market_news_raw_pack_2026-07-02.json").exists()

    read_back = read_session_output(
        sessions_root=tmp_path,
        session_id="sess-io",
        filename="market_news_raw_pack_2026-07-02.json",
        task_output_root=task_output_root,
        request_metadata={
            "active_task": {
                "task_id": "event-trigger",
                "inputs": [
                    {
                        "filename": "market_news_raw_pack_2026-07-02.json",
                        "source_task_id": "sector-attribution",
                    }
                ],
            }
        },
    )
    assert read_back["storage_kind"] == "task"
    assert read_back["data"]["trading_date"] == "2026-07-02"


def test_schema_validator_accepts_raw_pack(tmp_path: Path, task_manager: TaskPromptManager) -> None:
    spec = task_manager.get_task("sector-attribution")
    assert spec is not None
    artifact = spec.contract.outputs[0]
    path = tmp_path / "market_news_raw_pack_2026-07-02.json"
    path.write_text(
        json.dumps(
            {
                "trading_date": "2026-07-02",
                "window_start_date": "2026-07-02",
                "window_end_date": "2026-07-02",
                "sector_moves": [],
                "news_items": [],
                "sectors_without_news": [],
            }
        ),
        encoding="utf-8",
    )
    issues = TaskOutputValidator(task_manager).validate_artifact(task=spec, artifact=artifact, path=path)
    assert issues == []


def test_pipeline_runner_advances_to_event_trigger(
    task_output_root: Path,
    task_manager: TaskPromptManager,
) -> None:
    session_id = "sess-advance"
    _write_task_file(
        task_output_root,
        "sector-attribution",
        "market_news_raw_pack_2026-07-02.json",
        {
            "trading_date": "2026-07-02",
            "window_start_date": "2026-07-02",
            "window_end_date": "2026-07-02",
            "sector_moves": [
                {
                    "sector_path_id": "1/2/8",
                    "sector_name": {"zh": "半导体封测", "en": "Packaging"},
                    "market": "us",
                    "change_percent": -8.2,
                }
            ],
            "news_items": [],
            "sectors_without_news": ["1/2/8"],
        },
    )
    activator = TaskActivator(
        manager=task_manager,
        sessions_root="/tmp",
        task_output_root=str(task_output_root),
        auto_detect=False,
    )
    runner = PipelineRunner(
        manager=task_manager,
        activator=activator,
        validator=TaskOutputValidator(task_manager),
        task_output_root=str(task_output_root),
    )
    request = ChatRequest(
        message="/pipeline daily-market-events 2026-07-02",
        user_id="u1",
        session_id=session_id,
        channel="dashboard",
        metadata={
            "pipeline": {"id": "daily-market-events", "step": 1, "params": {"trading_date": "2026-07-02"}},
            "active_task": {
                "task_id": "sector-attribution",
                "params": {"trading_date": "2026-07-02"},
                "harness_profile": "tool_orchestrated",
                "outputs": [
                    {
                        "filename": "market_news_raw_pack_2026-07-02.json",
                        "format": "json",
                        "schema": "schema/market_news_raw_pack.schema.json",
                    }
                ],
            },
        },
    )
    from dojoagents.agent.models import AgentResponse

    response = AgentResponse(content="done", session_id=session_id)
    advance = runner.maybe_advance(request, response)
    assert advance.next_request is not None
    assert advance.next_request.metadata["active_task"]["task_id"] == "event-trigger"
    assert advance.next_request.metadata["active_task"]["inputs"][0]["filename"] == "market_news_raw_pack_2026-07-02.json"
    assert advance.next_request.metadata["active_task"]["inputs"][0]["source_task_id"] == "sector-attribution"
    assert advance.next_request.metadata["pipeline"]["step"] == 2


def test_tool_orchestrated_harness_blocks_days_usage() -> None:
    harness = ToolOrchestratedHarness()
    request = ChatRequest(
        message="run",
        user_id="u1",
        session_id="s1",
        metadata={
            "active_task": {
                "task_id": "sector-attribution",
                "harness_profile": "tool_orchestrated",
                "constraints": {"max_tool_calls_per_turn": 1},
            }
        },
    )
    state = HarnessLoopState(request=request)
    assert harness.matches(request, state)
    blocked = harness.block_tool_call(
        ToolCall(id="1", name="get_sector_movers", arguments={"days": 5}),
        state,
    )
    assert blocked is not None
    assert "start_date" in blocked


def test_artifact_synthesis_harness_blocks_write_before_read() -> None:
    harness = ArtifactSynthesisHarness()
    request = ChatRequest(
        message="run",
        user_id="u1",
        session_id="s1",
        metadata={
            "active_task": {
                "task_id": "event-trigger",
                "harness_profile": "artifact_synthesis",
                "constraints": {"must_read_input_before_write": True},
                "inputs": [{"filename": "market_news_raw_pack_2026-07-02.json", "required": True}],
                "outputs": [{"filename": "market_event_triggers_2026-07-02.jsonl", "format": "jsonl"}],
            }
        },
    )
    state = HarnessLoopState(request=request)
    blocked = harness.block_tool_call(
        ToolCall(id="1", name="write_session_file", arguments={"filename": "market_event_triggers_2026-07-02.jsonl"}),
        state,
    )
    assert blocked is not None
    assert "read_session_output" in blocked


def test_artifact_synthesis_harness_allows_write_after_read_in_same_turn() -> None:
    harness = ArtifactSynthesisHarness()
    request = ChatRequest(
        message="run",
        user_id="u1",
        session_id="s1",
        metadata={
            "active_task": {
                "task_id": "event-trigger",
                "harness_profile": "artifact_synthesis",
                "constraints": {"must_read_input_before_write": True},
                "inputs": [
                    {
                        "filename": "market_news_raw_pack_2026-07-02.json",
                        "base_filename": "market_news_raw_pack.json",
                        "required": True,
                    }
                ],
                "outputs": [{"filename": "market_event_triggers_2026-07-02.jsonl", "format": "jsonl"}],
            }
        },
    )
    state = HarnessLoopState(request=request)
    state.tool_results.append(
        ToolResult(
            call_id="read-1",
            name="read_session_output",
            ok=True,
            data={"filename": "market_news_raw_pack_2026-07-02.json"},
        )
    )
    blocked = harness.block_tool_call(
        ToolCall(id="2", name="write_session_file", arguments={"filename": "market_event_triggers_2026-07-02.jsonl"}),
        state,
    )
    assert blocked is None


def test_artifact_synthesis_harness_repairs_undated_read_filename() -> None:
    harness = ArtifactSynthesisHarness()
    request = ChatRequest(
        message="run",
        user_id="u1",
        session_id="s1",
        metadata={
            "active_task": {
                "task_id": "event-trigger",
                "harness_profile": "artifact_synthesis",
                "inputs": [
                    {
                        "filename": "market_news_raw_pack_2026-07-02.json",
                        "base_filename": "market_news_raw_pack.json",
                        "required": True,
                    }
                ],
            }
        },
    )
    state = HarnessLoopState(request=request)
    repaired = harness.repair_tool_calls(
        [
            ToolCall(
                id="1",
                name="read_session_output",
                arguments={"filename": "market_news_raw_pack.json"},
            )
        ],
        state,
    )
    assert repaired[0].arguments["filename"] == "market_news_raw_pack_2026-07-02.json"
