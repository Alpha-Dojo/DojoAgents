from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dojoagents.agent.models import AgentResponse
from dojoagents.cli.main import build_parser
from dojoagents.cli.tasks import (
    _metadata_exit_code,
    _response_exit_code,
    _run_status_exit_code,
    run_tasks_command,
)


def test_tasks_run_cli_parser() -> None:
    parser = build_parser()
    args = parser.parse_args(
        ["tasks", "run", "--pipeline", "daily-market-events", "--date", "2026-06-01"]
    )
    assert args.command == "tasks"
    assert args.tasks_command == "run"
    assert args.pipeline == "daily-market-events"
    assert args.date == "2026-06-01"
    assert args.local is False
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
    args = build_parser().parse_args(
        ["tasks", "run", "--pipeline", "daily-market-events", "--date", "2026-06-01"]
    )
    fake_record = {
        "run_id": "run-1",
        "status": "done",
        "metadata": {"pipeline_completed": True},
        "content": "done",
    }

    with patch("dojoagents.cli.tasks.run_pipeline_via_dashboard", new_callable=AsyncMock) as remote:
        remote.return_value = fake_record
        code = await run_tasks_command(args)

    assert code == 0
    remote.assert_awaited_once()
    kwargs = remote.await_args.kwargs
    assert kwargs["pipeline_id"] == "daily-market-events"
    assert kwargs["trading_date"] == "2026-06-01"
    assert kwargs["session_id"] == "cli-task-daily-market-events-2026-06-01"


@pytest.mark.asyncio
async def test_tasks_run_remote_returns_nonzero_on_validation_failure() -> None:
    args = build_parser().parse_args(
        ["tasks", "run", "--pipeline", "daily-market-events", "--date", "2026-06-01"]
    )
    fake_record = {
        "run_id": "run-1",
        "status": "done",
        "metadata": {"pipeline_validation_errors": ["Missing required output: foo.json"]},
        "content": "failed",
    }

    with patch("dojoagents.cli.tasks.run_pipeline_via_dashboard", new_callable=AsyncMock) as remote:
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

    with patch("dojoagents.cli.tasks._prepare_task_runtime", new_callable=AsyncMock) as prepare:
        runtime = AsyncMock()
        runtime.task_manager = MagicMock()
        runtime.task_manager.get_pipeline.return_value = object()
        runtime.agent.run = AsyncMock()
        prepare.return_value = (runtime, AsyncMock(), AsyncMock())
        with patch("dojoagents.cli.tasks.run_agent_with_tasks", new_callable=AsyncMock) as run_tasks:
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

    with patch("dojoagents.cli.tasks._prepare_task_runtime", new_callable=AsyncMock) as prepare:
        runtime = AsyncMock()
        runtime.task_manager = MagicMock()
        runtime.task_manager.get_pipeline.return_value = object()
        prepare.return_value = (runtime, AsyncMock(), AsyncMock())
        with patch("dojoagents.cli.tasks.run_agent_with_tasks", new_callable=AsyncMock) as run_tasks:
            run_tasks.return_value = fake_response
            code = await run_tasks_command(args)

    assert code == 1
