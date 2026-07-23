from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dojoagents.agent.models import AgentResponse
from dojoagents.cli.main import build_parser
from dojoagents.harnesses.built_in.financial.surfaces.cli_tasks import (
    _metadata_exit_code,
    _response_exit_code,
    _run_status_exit_code,
    run_tasks_command,
)


def test_tasks_run_cli_parser() -> None:
    parser = build_parser()
    args = parser.parse_args(["tasks", "run", "--pipeline", "daily-market-events", "--date", "2026-06-01"])
    assert args.command == "tasks"
    assert args.tasks_command == "run"
    assert args.pipeline == "daily-market-events"
    assert args.date == "2026-06-01"
    assert args.local is False
    assert args.force is False
    assert args.dashboard_url == ""


def test_tasks_run_local_flag() -> None:
    args = build_parser().parse_args(
        [
            "tasks",
            "run",
            "--pipeline",
            "daily-market-events",
            "--date",
            "2026-06-01",
            "--local",
        ]
    )
    assert args.local is True


def test_tasks_eval_cli_parser() -> None:
    args = build_parser().parse_args(["tasks", "eval", "--task", "event-trigger", "--date", "2026-07-13"])
    assert args.tasks_command == "eval"
    assert args.task == "event-trigger"
    assert args.date == "2026-07-13"
    assert args.artifact == ""
    assert args.output_root == ""


def test_tasks_run_force_flag() -> None:
    args = build_parser().parse_args(
        [
            "tasks",
            "run",
            "--pipeline",
            "daily-market-events",
            "--date",
            "2026-07-12",
            "--force",
        ]
    )
    assert args.force is True


@pytest.mark.parametrize(
    ("metadata", "expected"),
    [
        ({"pipeline_completed": True}, 0),
        ({"pipeline_validation_errors": ["Missing required output"]}, 1),
        ({"error": "task_activation", "task_activation_error": "Unknown pipeline"}, 1),
        ({"pipeline_error": "max_pipeline_steps_exceeded"}, 1),
        ({"stopped": "task_incomplete"}, 1),
        ({"cancelled": True}, 1),
        ({}, 1),
    ],
)
def test_metadata_exit_code(metadata: dict, expected: int) -> None:
    assert _metadata_exit_code(metadata) == expected
    response = AgentResponse(content="", session_id="s1", metadata=metadata)
    assert _response_exit_code(response) == expected


@pytest.mark.parametrize(
    ("status", "metadata", "expected"),
    [
        ("done", {"pipeline_completed": True}, 0),
        ("done", {"pipeline_validation_errors": ["x"]}, 1),
        ("done", {}, 1),
        ("error", {"error": "runtime_error"}, 1),
        ("cancelled", {"cancelled": True}, 1),
        ("running", {}, 1),
    ],
)
def test_run_status_exit_code(status: str, metadata: dict, expected: int) -> None:
    assert _run_status_exit_code(status, metadata) == expected


@pytest.mark.asyncio
async def test_tasks_run_remote_invokes_dashboard_client() -> None:
    args = build_parser().parse_args(["tasks", "run", "--pipeline", "daily-market-events", "--date", "2026-06-01"])
    fake_record = {
        "run_id": "run-1",
        "status": "done",
        "metadata": {"pipeline_completed": True},
        "content": "done",
    }

    with patch("dojoagents.harnesses.built_in.financial.surfaces.cli_tasks.run_pipeline_via_dashboard", new_callable=AsyncMock) as remote:
        remote.return_value = fake_record
        code = await run_tasks_command(args)

    assert code == 0
    remote.assert_awaited_once()
    kwargs = remote.await_args.kwargs
    assert kwargs["pipeline_id"] == "daily-market-events"
    assert kwargs["trading_date"] == "2026-06-01"
    assert kwargs["session_id"] == "cli-task-daily-market-events-2026-06-01"


@pytest.mark.asyncio
async def test_tasks_run_skips_non_trading_day_before_remote() -> None:
    args = build_parser().parse_args(["tasks", "run", "--pipeline", "daily-market-events", "--date", "2026-07-12"])
    with patch("dojoagents.harnesses.built_in.financial.surfaces.cli_tasks.run_pipeline_via_dashboard", new_callable=AsyncMock) as remote:
        code = await run_tasks_command(args)

    assert code == 0
    remote.assert_not_awaited()


@pytest.mark.asyncio
async def test_tasks_run_force_bypasses_trading_day_skip() -> None:
    args = build_parser().parse_args(
        [
            "tasks",
            "run",
            "--pipeline",
            "daily-market-events",
            "--date",
            "2026-07-12",
            "--force",
        ]
    )
    fake_record = {
        "run_id": "run-1",
        "status": "done",
        "metadata": {"pipeline_completed": True},
        "content": "done",
    }
    with patch("dojoagents.harnesses.built_in.financial.surfaces.cli_tasks.run_pipeline_via_dashboard", new_callable=AsyncMock) as remote:
        remote.return_value = fake_record
        code = await run_tasks_command(args)

    assert code == 0
    remote.assert_awaited_once()


@pytest.mark.asyncio
async def test_tasks_run_remote_returns_nonzero_on_validation_failure() -> None:
    args = build_parser().parse_args(["tasks", "run", "--pipeline", "daily-market-events", "--date", "2026-06-01"])
    fake_record = {
        "run_id": "run-1",
        "status": "done",
        "metadata": {"pipeline_validation_errors": ["Missing required output: foo.json"]},
        "content": "failed",
    }

    with patch("dojoagents.harnesses.built_in.financial.surfaces.cli_tasks.run_pipeline_via_dashboard", new_callable=AsyncMock) as remote:
        remote.return_value = fake_record
        code = await run_tasks_command(args)

    assert code == 1


@pytest.mark.asyncio
async def test_tasks_run_local_invokes_pipeline_runner() -> None:
    args = build_parser().parse_args(
        [
            "tasks",
            "run",
            "--pipeline",
            "daily-market-events",
            "--date",
            "2026-06-01",
            "--local",
        ]
    )
    fake_response = AgentResponse(
        content="done",
        session_id="cli-task-daily-market-events-2026-06-01",
        metadata={"pipeline_completed": True},
    )

    with patch("dojoagents.harnesses.built_in.financial.surfaces.cli_tasks._prepare_task_runtime", new_callable=AsyncMock) as prepare:
        runtime = AsyncMock()
        runtime.task_manager = MagicMock()
        runtime.task_manager.get_pipeline.return_value = object()
        runtime.agent.run = AsyncMock()
        prepare.return_value = (runtime, AsyncMock(), AsyncMock())
        with patch("dojoagents.harnesses.built_in.financial.surfaces.cli_tasks.run_agent_with_tasks", new_callable=AsyncMock) as run_tasks:
            run_tasks.return_value = fake_response
            code = await run_tasks_command(args)

    assert code == 0
    run_tasks.assert_awaited_once()
    request = run_tasks.await_args.args[1]
    assert request.message == "/pipeline daily-market-events 2026-06-01"
    assert request.session_id == "cli-task-daily-market-events-2026-06-01"
    assert request.channel == "cli"


@pytest.mark.asyncio
async def test_tasks_run_local_returns_nonzero_on_validation_failure() -> None:
    args = build_parser().parse_args(
        [
            "tasks",
            "run",
            "--pipeline",
            "daily-market-events",
            "--date",
            "2026-06-01",
            "--local",
        ]
    )
    fake_response = AgentResponse(
        content="failed",
        session_id="cli-task-daily-market-events-2026-06-01",
        metadata={"pipeline_validation_errors": ["Missing required output: foo.json"]},
    )

    with patch("dojoagents.harnesses.built_in.financial.surfaces.cli_tasks._prepare_task_runtime", new_callable=AsyncMock) as prepare:
        runtime = AsyncMock()
        runtime.task_manager = MagicMock()
        runtime.task_manager.get_pipeline.return_value = object()
        prepare.return_value = (runtime, AsyncMock(), AsyncMock())
        with patch("dojoagents.harnesses.built_in.financial.surfaces.cli_tasks.run_agent_with_tasks", new_callable=AsyncMock) as run_tasks:
            run_tasks.return_value = fake_response
            code = await run_tasks_command(args)

    assert code == 1


def test_tasks_eval_validates_jsonl_against_schema(tmp_path) -> None:
    from dojoagents.harnesses.built_in.financial.surfaces.cli_tasks import eval_task_output

    output_root = tmp_path / "outputs"
    task_dir = output_root / "event-trigger"
    task_dir.mkdir(parents=True)
    path = task_dir / "market_event_triggers_2026-07-13.jsonl"
    path.write_text(
        '{"event_time":"2026-07-13T12:00:00Z","event_summary":{"headline":{"zh":"测试标题","en":"Test headline"},'
        '"category":"macro_data","source":{"zh":"来源","en":"Source"},'
        '"content":{"zh":"内容","en":"Content"},"surprise":"expected"},'
        '"sector_impacts":[{"sector_id":"1/2/3","sector_name":{"zh":"板块","en":"Sector"},'
        '"affected_markets":["us"],"direction":"Positive","reason":"up 3%"}]}\n',
        encoding="utf-8",
    )
    args = build_parser().parse_args(
        [
            "tasks",
            "eval",
            "--task",
            "event-trigger",
            "--date",
            "2026-07-13",
            "--output-root",
            str(output_root),
        ]
    )
    assert eval_task_output(args) == 0


def test_tasks_eval_fails_on_invalid_jsonl(tmp_path) -> None:
    from dojoagents.harnesses.built_in.financial.surfaces.cli_tasks import eval_task_output

    output_root = tmp_path / "outputs"
    task_dir = output_root / "event-trigger"
    task_dir.mkdir(parents=True)
    path = task_dir / "market_event_triggers_2026-07-13.jsonl"
    path.write_text("not-json\n", encoding="utf-8")
    args = build_parser().parse_args(
        [
            "tasks",
            "eval",
            "--task",
            "event-trigger",
            "--date",
            "2026-07-13",
            "--output-root",
            str(output_root),
        ]
    )
    assert eval_task_output(args) == 1
