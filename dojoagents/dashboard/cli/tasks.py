from __future__ import annotations

import argparse
import datetime
import json
import re
from pathlib import Path
from typing import Any

from dojo.client.async_client import AsyncDojo

from dojoagents.agent.models import AgentResponse, ChatRequest
from dojoagents.agent.runtime import Runtime
from dojoagents.dashboard.client.tasks import (
    DashboardTaskClientError,
    dashboard_base_url_from_config,
    run_pipeline_via_dashboard,
)
from dojoagents.config.loader import ConfigStore
from dojoagents.logging import LOGGER, configure_logging
from dojoagents.tasks.activator import TaskActivationError
from dojoagents.tasks.artifacts import resolve_dated_filename
from dojoagents.tasks.manager import TaskPromptManager
from dojoagents.tasks.models import TaskArtifactSpec, TaskSpec
from dojoagents.tasks.output_paths import resolve_task_output_file
from dojoagents.tasks.runtime_helpers import run_agent_with_tasks
from dojoagents.tasks.schema_validator import TaskOutputValidator
from dojoagents.sessions.models import SessionPrincipal

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def add_tasks_parser(sub: argparse._SubParsersAction) -> None:
    tasks = sub.add_parser("tasks", help="Run task pipelines from the CLI")
    tasks_sub = tasks.add_subparsers(dest="tasks_command", required=True)

    run = tasks_sub.add_parser("run", help="Run a task pipeline for one trading date")
    run.add_argument("--pipeline", required=True, help="Pipeline id, e.g. daily-market-events")
    run.add_argument("--date", help="Trading date (YYYY-MM-DD), defaults to today")
    run.add_argument("--config", default="~/.dojo/agents.yaml", help="Path to agents.yaml")
    run.add_argument(
        "--force",
        action="store_true",
        help="Bypass pipeline preflight gates (e.g. trading-day check)",
    )
    run.add_argument(
        "--local",
        action="store_true",
        help="Run embedded in this process (loads market data locally)",
    )
    run.add_argument(
        "--dashboard-url",
        default="",
        help="Dashboard base URL (default: http://{dashboard.host}:{dashboard.port} from config)",
    )
    run.add_argument(
        "--no-preload",
        action="store_true",
        help="Skip DojoSDK offline preload in --local mode",
    )
    run.add_argument(
        "--force-rerun",
        action="store_true",
        help="Run pipeline even if output file already exists",
    )
    run.add_argument(
        "--skip-upload",
        action="store_true",
        help="Skip uploading the output file",
    )
    run.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Maximum number of retries if pipeline execution fails (default: 3)",
    )

    evaluate = tasks_sub.add_parser(
        "eval",
        help="Validate a task output artifact against its contract schema",
    )
    evaluate.add_argument("--task", required=True, help="Task id, e.g. event-trigger")
    evaluate.add_argument("--date", required=True, help="Trading date (YYYY-MM-DD)")
    evaluate.add_argument("--config", default="~/.dojo/agents.yaml", help="Path to agents.yaml")
    evaluate.add_argument(
        "--artifact",
        default="",
        help="Optional base artifact filename (default: validate all required outputs)",
    )
    evaluate.add_argument(
        "--output-root",
        default="",
        help="Override tasks.output_root from config",
    )


def _validate_trading_date(raw: str) -> str:
    text = str(raw or "").strip()
    if not _DATE_RE.fullmatch(text):
        raise TaskActivationError(f"Invalid date (expected YYYY-MM-DD): {raw!r}")
    return text


def _sanitize_session_token(raw: str) -> str:
    token = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(raw or "").strip()).strip("-")
    return token or "pipeline"


def load_task_manager(config_path: str) -> TaskPromptManager:
    store = ConfigStore(config_path)
    configure_logging(store.snapshot().logging)
    runtime = Runtime.from_config_store(store)
    if runtime.task_manager is None:
        raise TaskActivationError("Task system is not initialized on this runtime.")
    return runtime.task_manager


def _metadata_exit_code(metadata: dict[str, Any] | None) -> int:
    meta = metadata if isinstance(metadata, dict) else {}
    if meta.get("error") == "task_activation" or meta.get("task_activation_error"):
        return 1
    validation_errors = meta.get("pipeline_validation_errors")
    if isinstance(validation_errors, list) and validation_errors:
        return 1
    if meta.get("pipeline_error"):
        return 1
    if meta.get("stopped"):
        return 1
    if meta.get("cancelled"):
        return 1
    if meta.get("pipeline_completed") is True:
        return 0
    return 1


def _run_status_exit_code(status: str, metadata: dict[str, Any] | None = None) -> int:
    normalized = str(status or "").strip().lower()
    if normalized in {"error", "cancelled"}:
        return 1
    if normalized == "done":
        meta = metadata if isinstance(metadata, dict) else {}
        if meta:
            return _metadata_exit_code(meta)
        return 1
    return 1


def _response_exit_code(response: AgentResponse) -> int:
    metadata = response.metadata if isinstance(response.metadata, dict) else {}
    return _metadata_exit_code(metadata)


def _log_metadata_summary(metadata: dict[str, Any] | None, *, content: str = "") -> None:
    meta = metadata if isinstance(metadata, dict) else {}
    pipeline_completed = meta.get("pipeline_completed")
    validation_errors = meta.get("pipeline_validation_errors") or []
    stopped = meta.get("stopped")
    tool_trace = meta.get("tool_trace")
    tool_steps = len(tool_trace) if isinstance(tool_trace, list) else 0

    if pipeline_completed is True:
        LOGGER.info("Pipeline completed successfully (tool_steps=%d)", tool_steps)
        return

    if validation_errors:
        LOGGER.error("Pipeline validation failed: %s", "; ".join(str(item) for item in validation_errors))
    if meta.get("task_activation_error"):
        LOGGER.error("Task activation failed: %s", meta.get("task_activation_error"))
    if meta.get("pipeline_error"):
        LOGGER.error("Pipeline error: %s", meta.get("pipeline_error"))
    if stopped:
        LOGGER.error("Agent stopped: %s", stopped)
    if meta.get("cancelled"):
        LOGGER.error("Run cancelled")
    if meta.get("error") and meta.get("error") != "task_activation":
        LOGGER.error("Run error: %s", meta.get("message") or meta.get("error"))

    preview = str(content or "").strip()
    if preview:
        LOGGER.error("Agent response preview: %s", preview[:500])


def _log_response_summary(response: AgentResponse) -> None:
    metadata = response.metadata if isinstance(response.metadata, dict) else {}
    _log_metadata_summary(metadata, content=str(response.content or ""))


async def _close_dojo_client(client: Any) -> None:
    close = getattr(client, "aclose", None)
    if callable(close):
        await close()
        return
    http_client = getattr(client, "_client", None)
    close = getattr(http_client, "aclose", None)
    if callable(close):
        await close()


async def _prepare_task_runtime(
    config_path: str,
    *,
    preload: bool = True,
) -> tuple[Runtime, Any]:
    store = ConfigStore(config_path)
    configure_logging(store.snapshot().logging)
    config = store.snapshot()
    if not config.tasks.enabled:
        raise TaskActivationError("tasks.enabled is false in config; enable tasks to use the CLI.")

    from dojoagents.dashboard.integrations.runtime_factory import (
        create_embedded_runtime,
    )
    from dojoagents.dashboard.services.app_container import (
        DashboardAppServices,
        DashboardAppServicesConfig,
    )

    services_config = DashboardAppServicesConfig.from_agents_config(config)
    if not preload:
        services_config = DashboardAppServicesConfig(
            **{
                **services_config.__dict__,
                "preload_offline_data": False,
                "preload_registry": False,
                "refresh_enabled": False,
            }
        )
    services = DashboardAppServices(services_config)
    try:
        await services.startup()
        runtime = await create_embedded_runtime(store, services)
    except Exception:
        await services.shutdown()
        raise
    if runtime.command_router is None or runtime.task_manager is None:
        await runtime.shutdown()
        await services.shutdown()
        raise TaskActivationError("Task system is not initialized on this runtime.")
    return runtime, services


async def _run_pipeline_task_local(args: argparse.Namespace, *, pipeline_id: str, trading_date: str) -> int:
    runtime: Runtime | None = None
    services: Any | None = None

    try:
        runtime, services = await _prepare_task_runtime(
            args.config,
            preload=not bool(args.no_preload),
        )
        manager = runtime.task_manager
        if manager.get_pipeline(pipeline_id) is None:
            available = ", ".join(manager.list_pipelines()) or "(none)"
            raise TaskActivationError(f"Unknown pipeline: {pipeline_id}. Available: {available}.")

        session_id = f"cli-task-{_sanitize_session_token(pipeline_id)}-{trading_date}"
        message = f"/pipeline {pipeline_id} {trading_date}"
        LOGGER.info(
            "Starting local pipeline run: pipeline=%s date=%s session_id=%s",
            pipeline_id,
            trading_date,
            session_id,
        )

        request = ChatRequest(
            message=message,
            principal=SessionPrincipal("local"),
            session_id=session_id,
            channel="cli",
            metadata={"persist_session": False},
        )
        response = await run_agent_with_tasks(
            runtime,
            request,
            run_agent=runtime.agent.run,
        )
        exit_code = _response_exit_code(response)
        _log_response_summary(response)
        return exit_code
    finally:
        if runtime is not None:
            await runtime.shutdown()
        if services is not None:
            await services.shutdown()


async def _run_pipeline_task_remote(args: argparse.Namespace, *, pipeline_id: str, trading_date: str) -> int:
    store = ConfigStore(args.config)
    configure_logging(store.snapshot().logging)
    config = store.snapshot()
    if not config.tasks.enabled:
        raise TaskActivationError("tasks.enabled is false in config; enable tasks to use the CLI.")

    base_url = dashboard_base_url_from_config(args.config, override=args.dashboard_url or None)
    session_id = f"cli-task-{_sanitize_session_token(pipeline_id)}-{trading_date}"

    record = await run_pipeline_via_dashboard(
        base_url=base_url,
        pipeline_id=pipeline_id,
        trading_date=trading_date,
        session_id=session_id,
    )
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    status = str(record.get("status") or "")
    exit_code = _run_status_exit_code(status, metadata)
    _log_metadata_summary(metadata, content=str(record.get("content") or ""))
    return exit_code


def _select_eval_artifacts(task: TaskSpec, artifact_filter: str) -> list[TaskArtifactSpec]:
    outputs = list(task.contract.outputs)
    wanted = str(artifact_filter or "").strip()
    if not wanted:
        return [item for item in outputs if item.required]
    matched = [item for item in outputs if item.filename == wanted or Path(item.filename).name == wanted]
    if not matched:
        available = ", ".join(item.filename for item in outputs) or "(none)"
        raise TaskActivationError(f"Unknown artifact {wanted!r} for task {task.contract.id}. Available: {available}.")
    return matched


def eval_task_output(args: argparse.Namespace) -> int:
    store = ConfigStore(args.config)
    configure_logging(store.snapshot().logging)
    config = store.snapshot()
    if not config.tasks.enabled:
        raise TaskActivationError("tasks.enabled is false in config; enable tasks to use the CLI.")

    trading_date = _validate_trading_date(args.date)
    task_id = str(args.task or "").strip()
    if not task_id:
        raise TaskActivationError("Missing required --task")

    manager = load_task_manager(args.config)
    task = manager.get_task(task_id)
    if task is None:
        available = ", ".join(manager.list_tasks()) or "(none)"
        raise TaskActivationError(f"Unknown task: {task_id}. Available: {available}.")

    output_root = str(args.output_root or "").strip() or config.tasks.output_root
    params = {"trading_date": trading_date}
    validator = TaskOutputValidator(manager)
    artifacts = _select_eval_artifacts(task, str(args.artifact or ""))
    if not artifacts:
        raise TaskActivationError(f"Task {task_id} has no required output artifacts to eval.")

    total_issues = 0
    for artifact in artifacts:
        filename = resolve_dated_filename(artifact.filename, params)
        try:
            path = resolve_task_output_file(output_root, task.contract.id, filename)
        except ValueError as exc:
            LOGGER.error("%s", exc)
            total_issues += 1
            continue
        if not path.is_file():
            LOGGER.error("Missing output file: %s", path)
            total_issues += 1
            continue
        issues = validator.validate_artifact(task=task, artifact=artifact, path=path)
        if issues:
            total_issues += len(issues)
            LOGGER.error("Eval failed for %s (%d issue(s)):", path, len(issues))
            for issue in issues:
                LOGGER.error("  - %s", issue)
            continue
        LOGGER.info("Eval passed: %s", path)

    if total_issues:
        LOGGER.error("Task eval failed with %d issue(s)", total_issues)
        return 1
    LOGGER.info("Task eval passed for %s date=%s", task_id, trading_date)
    return 0


async def run_pipeline_task(args: argparse.Namespace) -> int:
    pipeline_id = str(args.pipeline or "").strip()
    if not pipeline_id:
        raise TaskActivationError("Missing required --pipeline")

    raw_date = args.date or datetime.date.today().isoformat()
    trading_date = _validate_trading_date(raw_date)
    manager = load_task_manager(args.config)
    pipeline = manager.get_pipeline(pipeline_id)
    if pipeline is None:
        available = ", ".join(manager.list_pipelines()) or "(none)"
        raise TaskActivationError(f"Unknown pipeline: {pipeline_id}. Available: {available}.")

    runtime = Runtime.from_config_store(ConfigStore(args.config))
    evaluate_preflight = getattr(
        runtime.harness,
        "evaluate_pipeline_preflight",
        None,
    )
    if not callable(evaluate_preflight):
        raise TaskActivationError(f"Harness does not support pipeline preflight: {pipeline_id}")
    preflight = evaluate_preflight(
        pipeline,
        trading_date=trading_date,
        force=bool(getattr(args, "force", False)),
    )
    if preflight.action == "skip":
        LOGGER.info("%s", preflight.reason)
        return 0
    if preflight.open_markets:
        LOGGER.info("Preflight ok: %s", preflight.reason)

    store = ConfigStore(args.config)
    config = store.snapshot()

    if not getattr(args, "force_rerun", False) and pipeline_id == "daily-market-events":
        output_root = Path(config.tasks.output_root).expanduser()
        file_path = output_root / "event-trigger" / f"market_event_triggers_{trading_date}.jsonl"
        if file_path.is_file():
            LOGGER.info("Task output %s already exists. Skipping pipeline execution.", file_path)
            if not getattr(args, "skip_upload", False):
                await _upload_daily_market_events(args.config, trading_date)
            return 0

    max_retries = getattr(args, "max_retries", 3)
    exit_code = 1

    for attempt in range(1, max_retries + 1):
        try:
            if bool(args.local):
                exit_code = await _run_pipeline_task_local(args, pipeline_id=pipeline_id, trading_date=trading_date)
            else:
                exit_code = await _run_pipeline_task_remote(args, pipeline_id=pipeline_id, trading_date=trading_date)
        except Exception as exc:
            LOGGER.error("Exception during pipeline %s execution on attempt %d: %s", pipeline_id, attempt, exc)
            exit_code = 1

        if exit_code == 0:
            break

        if attempt < max_retries:
            LOGGER.warning("Pipeline %s failed on attempt %d of %d. Retrying...", pipeline_id, attempt, max_retries)
        else:
            LOGGER.error("Pipeline %s failed after %d attempts.", pipeline_id, max_retries)

    if exit_code == 0 and pipeline_id == "daily-market-events":
        if not getattr(args, "skip_upload", False):
            await _upload_daily_market_events(args.config, trading_date)
    else:
        LOGGER.error(f"Pipeline execution failed: exit_code: {exit_code}")
    return exit_code


async def _upload_daily_market_events(config_path: str, trading_date: str) -> None:
    store = ConfigStore(config_path)
    config = store.snapshot()

    output_root = Path(config.tasks.output_root).expanduser()
    file_path = output_root / "event-trigger" / f"market_event_triggers_{trading_date}.jsonl"
    if not file_path.is_file():
        LOGGER.error("Cannot upload events: %s not found", file_path)
        return

    items = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    parsed = json.loads(line)
                    if isinstance(parsed, list):
                        items.extend(parsed)
                    elif isinstance(parsed, dict):
                        items.append(parsed)
    except Exception as exc:
        LOGGER.error("Error reading market event output file %s: %s", file_path, exc)
        return

    if not items:
        LOGGER.info("No market events to upload.")
        return

    sdk_cfg = config.dojosdk
    client_kwargs = {
        "api_key": sdk_cfg.api_key if sdk_cfg else None,
        "base_url": sdk_cfg.base_url if sdk_cfg else None,
        "timeout": sdk_cfg.timeout if sdk_cfg else 60.0,
        "max_retries": sdk_cfg.max_retries if sdk_cfg else 1,
    }
    client = AsyncDojo(**{key: value for key, value in client_kwargs.items() if value is not None})
    try:
        LOGGER.info("Uploading %d market events to DojoSDK...", len(items))
        for item in items:
            await client.analysis.create_market_dynamics(**item)
        LOGGER.info("Successfully uploaded market events.")
    except Exception as exc:
        LOGGER.error("Failed to upload market events: %s", exc)
    finally:
        await _close_dojo_client(client)


async def run_tasks_command(args: argparse.Namespace) -> int:
    if args.tasks_command == "run":
        try:
            return await run_pipeline_task(args)
        except (TaskActivationError, DashboardTaskClientError) as exc:
            LOGGER.error("%s", exc)
            return 1
    if args.tasks_command == "eval":
        try:
            return eval_task_output(args)
        except TaskActivationError as exc:
            LOGGER.error("%s", exc)
            return 1
    return 2
