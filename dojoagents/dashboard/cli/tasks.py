from __future__ import annotations

import argparse
import datetime
import json
import re
import shlex
import uuid
from pathlib import Path
from typing import Any

from dojo.client.async_client import AsyncDojo

from dojoagents.agent.models import AgentResponse, ChatRequest
from dojoagents.agent.runtime import Runtime
from dojoagents.dashboard.client.tasks import (
    DashboardTaskClientError,
    dashboard_base_url_from_config,
    run_pipeline_via_dashboard,
    run_task_via_dashboard,
)
from dojoagents.config.loader import ConfigStore
from dojoagents.logging import LOGGER, configure_logging
from dojoagents.tasks.activator import TaskActivationError
from dojoagents.tasks.artifacts import resolve_filename_template
from dojoagents.tasks.manager import TaskPromptManager
from dojoagents.tasks.models import TaskArtifactSpec, TaskSpec
from dojoagents.tasks.output_paths import resolve_task_output_file
from dojoagents.tasks.runtime_helpers import run_agent_with_tasks
from dojoagents.tasks.schema_validator import TaskOutputValidator
from dojoagents.sessions.models import SessionPrincipal

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def add_tasks_parser(sub: argparse._SubParsersAction) -> None:
    tasks = sub.add_parser("tasks", help="Run task pipelines or single tasks from the CLI")
    tasks_sub = tasks.add_subparsers(dest="tasks_command", required=True)

    run = tasks_sub.add_parser("run", help="Run a pipeline or a single task")
    target = run.add_mutually_exclusive_group(required=True)
    target.add_argument("--pipeline", help="Pipeline id, e.g. daily-market-events")
    target.add_argument("--task", help="Task id, e.g. attribution-factor-crawl")
    run.add_argument(
        "--date",
        help="Trading date (YYYY-MM-DD). Required semantics: pipelines default to today; " "for --task include only when set (or pass YYYY-MM-DD in trailing args).",
    )
    run.add_argument(
        "--market",
        choices=["us", "cn", "hk"],
        default="",
        help="Market code (us|cn|hk). Required for daily-market-events and other market-scoped pipelines/tasks.",
    )
    run.add_argument(
        "task_args",
        nargs="*",
        help="Extra /task arguments (key=value, YYYY-MM-DD, or positional query). Ignored for --pipeline.",
    )
    run.add_argument("--config", default="~/.dojo/agents.yaml", help="Path to agents.yaml")
    run.add_argument(
        "--model",
        default="",
        help="Request-scoped model override; uses the configured provider",
    )
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
        default=None,
        help="Max attempts on failure (default: 3 for --pipeline, 1 for --task). Each attempt uses a fresh session for --task.",
    )

    evaluate = tasks_sub.add_parser(
        "eval",
        help="Validate a task output artifact against its contract schema",
    )
    evaluate.add_argument("--task", required=True, help="Task id, e.g. event-trigger")
    evaluate.add_argument("--date", required=True, help="Trading date (YYYY-MM-DD)")
    evaluate.add_argument(
        "--market",
        choices=["us", "cn", "hk"],
        default="",
        help="Market code (us|cn|hk). Required when the task artifact filename includes {market}.",
    )
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


def _new_cli_task_session_id(task_id: str) -> str:
    """Fresh session per CLI invocation — never reuse task/date keys across runs."""
    return f"cli-task-{_sanitize_session_token(task_id)}-{uuid.uuid4().hex[:12]}"


def _build_task_slash_message(task_id: str, *, trading_date: str | None, task_args: list[str] | None) -> str:
    """Build `/task <id> [date] [args…]` for CommandRouter activation."""
    parts = [f"/task {str(task_id or '').strip()}"]
    extras = [str(item).strip() for item in (task_args or []) if str(item).strip()]
    date = str(trading_date or "").strip() or None
    if date:
        if not any(_DATE_RE.fullmatch(item) for item in extras):
            parts.append(date)
    parts.extend(shlex.quote(item) for item in extras)
    return " ".join(parts)


def load_task_manager(config_path: str) -> TaskPromptManager:
    store = ConfigStore(config_path)
    configure_logging(store.snapshot().logging)
    runtime = Runtime.from_config_store(store)
    if runtime.task_manager is None:
        raise TaskActivationError("Task system is not initialized on this runtime.")
    return runtime.task_manager


def _metadata_has_failure(metadata: dict[str, Any] | None) -> bool:
    meta = metadata if isinstance(metadata, dict) else {}
    if meta.get("error") == "task_activation" or meta.get("task_activation_error"):
        return True
    validation_errors = meta.get("pipeline_validation_errors")
    if isinstance(validation_errors, list) and validation_errors:
        return True
    if meta.get("pipeline_error"):
        return True
    if meta.get("stopped"):
        return True
    if meta.get("cancelled"):
        return True
    if meta.get("error") and meta.get("error") != "task_activation":
        return True
    return False


def _metadata_exit_code(metadata: dict[str, Any] | None, *, require_pipeline_completed: bool = True) -> int:
    meta = metadata if isinstance(metadata, dict) else {}
    if _metadata_has_failure(meta):
        return 1
    if require_pipeline_completed:
        return 0 if meta.get("pipeline_completed") is True else 1
    return 0


def _run_status_exit_code(
    status: str,
    metadata: dict[str, Any] | None = None,
    *,
    require_pipeline_completed: bool = True,
) -> int:
    normalized = str(status or "").strip().lower()
    if normalized in {"error", "cancelled"}:
        return 1
    if normalized == "done":
        meta = metadata if isinstance(metadata, dict) else {}
        if meta or not require_pipeline_completed:
            return _metadata_exit_code(meta, require_pipeline_completed=require_pipeline_completed)
        return 1
    return 1


def _response_exit_code(response: AgentResponse, *, require_pipeline_completed: bool = True) -> int:
    metadata = response.metadata if isinstance(response.metadata, dict) else {}
    return _metadata_exit_code(metadata, require_pipeline_completed=require_pipeline_completed)


def _log_metadata_summary(
    metadata: dict[str, Any] | None,
    *,
    content: str = "",
    require_pipeline_completed: bool = True,
) -> None:
    meta = metadata if isinstance(metadata, dict) else {}
    pipeline_completed = meta.get("pipeline_completed")
    validation_errors = meta.get("pipeline_validation_errors") or []
    stopped = meta.get("stopped")
    tool_trace = meta.get("tool_trace")
    tool_steps = len(tool_trace) if isinstance(tool_trace, list) else 0

    if pipeline_completed is True:
        LOGGER.info("Pipeline completed successfully (tool_steps=%d)", tool_steps)
        return
    if not require_pipeline_completed and not _metadata_has_failure(meta):
        LOGGER.info("Task completed successfully (tool_steps=%d)", tool_steps)
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


def _log_response_summary(response: AgentResponse, *, require_pipeline_completed: bool = True) -> None:
    metadata = response.metadata if isinstance(response.metadata, dict) else {}
    _log_metadata_summary(
        metadata,
        content=str(response.content or ""),
        require_pipeline_completed=require_pipeline_completed,
    )


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


def _pipeline_slash_message(pipeline_id: str, trading_date: str, market: str = "") -> str:
    parts = [f"/pipeline {pipeline_id}", trading_date]
    market_code = str(market or "").strip().lower()
    if market_code:
        parts.append(f"market={market_code}")
    return " ".join(parts)


def _pipeline_session_id(pipeline_id: str, trading_date: str, market: str = "") -> str:
    token = f"{_sanitize_session_token(pipeline_id)}-{trading_date}"
    market_code = str(market or "").strip().lower()
    if market_code:
        token = f"{token}-{market_code}"
    return f"cli-task-{token}"


async def _run_pipeline_task_local(
    args: argparse.Namespace,
    *,
    pipeline_id: str,
    trading_date: str,
    market: str = "",
) -> int:
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

        session_id = _pipeline_session_id(pipeline_id, trading_date, market)
        message = _pipeline_slash_message(pipeline_id, trading_date, market)
        LOGGER.info(
            "Starting local pipeline run: pipeline=%s date=%s market=%s session_id=%s",
            pipeline_id,
            trading_date,
            market or "-",
            session_id,
        )

        request = ChatRequest(
            message=message,
            principal=SessionPrincipal("local"),
            session_id=session_id,
            channel="cli",
            metadata={
                "persist_session": False,
                **({"model_override": args.model} if str(args.model or "").strip() else {}),
            },
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
            try:
                await runtime.shutdown()
            except Exception:
                LOGGER.exception("Failed to shut down local task runtime")
        if services is not None:
            try:
                await services.shutdown()
            except Exception:
                LOGGER.exception("Failed to shut down local task services")


async def _run_pipeline_task_remote(
    args: argparse.Namespace,
    *,
    pipeline_id: str,
    trading_date: str,
    market: str = "",
) -> int:
    store = ConfigStore(args.config)
    configure_logging(store.snapshot().logging)
    config = store.snapshot()
    if not config.tasks.enabled:
        raise TaskActivationError("tasks.enabled is false in config; enable tasks to use the CLI.")

    base_url = dashboard_base_url_from_config(args.config, override=args.dashboard_url or None)
    session_id = _pipeline_session_id(pipeline_id, trading_date, market)

    record = await run_pipeline_via_dashboard(
        base_url=base_url,
        pipeline_id=pipeline_id,
        trading_date=trading_date,
        market=market,
        session_id=session_id,
        model=str(args.model or "").strip() or "default",
    )
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    status = str(record.get("status") or "")
    exit_code = _run_status_exit_code(status, metadata)
    _log_metadata_summary(metadata, content=str(record.get("content") or ""))
    return exit_code


async def _run_single_task_local(
    args: argparse.Namespace,
    *,
    task_id: str,
    message: str,
    session_id: str,
) -> int:
    runtime: Runtime | None = None
    services: Any | None = None

    try:
        runtime, services = await _prepare_task_runtime(
            args.config,
            preload=not bool(args.no_preload),
        )
        manager = runtime.task_manager
        if manager.get_task(task_id) is None:
            available = ", ".join(manager.list_tasks()) or "(none)"
            raise TaskActivationError(f"Unknown task: {task_id}. Available: {available}.")

        LOGGER.info(
            "Starting local task run: task=%s session_id=%s message=%s",
            task_id,
            session_id,
            message,
        )

        request = ChatRequest(
            message=message,
            principal=SessionPrincipal("local"),
            session_id=session_id,
            channel="cli",
            metadata={
                "persist_session": False,
                **({"model_override": args.model} if str(args.model or "").strip() else {}),
            },
        )
        response = await run_agent_with_tasks(
            runtime,
            request,
            run_agent=runtime.agent.run,
        )
        exit_code = _response_exit_code(response, require_pipeline_completed=False)
        _log_response_summary(response, require_pipeline_completed=False)
        return exit_code
    finally:
        if runtime is not None:
            await runtime.shutdown()
        if services is not None:
            await services.shutdown()


async def _run_single_task_remote(
    args: argparse.Namespace,
    *,
    task_id: str,
    message: str,
    session_id: str,
) -> int:
    store = ConfigStore(args.config)
    configure_logging(store.snapshot().logging)
    config = store.snapshot()
    if not config.tasks.enabled:
        raise TaskActivationError("tasks.enabled is false in config; enable tasks to use the CLI.")

    base_url = dashboard_base_url_from_config(args.config, override=args.dashboard_url or None)

    record = await run_task_via_dashboard(
        base_url=base_url,
        message=message,
        session_id=session_id,
        model=str(args.model or "").strip() or "default",
    )
    metadata = record.get("metadata") if isinstance(record.get("metadata"), dict) else {}
    status = str(record.get("status") or "")
    exit_code = _run_status_exit_code(status, metadata, require_pipeline_completed=False)
    _log_metadata_summary(
        metadata,
        content=str(record.get("content") or ""),
        require_pipeline_completed=False,
    )
    return exit_code


async def run_single_task(args: argparse.Namespace) -> int:
    task_id = str(args.task or "").strip()
    if not task_id:
        raise TaskActivationError("Missing required --task")

    manager = load_task_manager(args.config)
    if manager.get_task(task_id) is None:
        available = ", ".join(manager.list_tasks()) or "(none)"
        raise TaskActivationError(f"Unknown task: {task_id}. Available: {available}.")

    trading_date = None
    if args.date:
        trading_date = _validate_trading_date(args.date)
    task_args = [str(item) for item in (getattr(args, "task_args", None) or [])]
    message = _build_task_slash_message(task_id, trading_date=trading_date, task_args=task_args)

    # Single-task CLI defaults to one attempt; retries (if requested) each get a fresh session.
    max_retries = int(args.max_retries) if args.max_retries is not None else 1
    if max_retries < 1:
        max_retries = 1
    exit_code = 1
    for attempt in range(1, max_retries + 1):
        session_id = _new_cli_task_session_id(task_id)
        try:
            if bool(args.local):
                exit_code = await _run_single_task_local(
                    args,
                    task_id=task_id,
                    message=message,
                    session_id=session_id,
                )
            else:
                exit_code = await _run_single_task_remote(
                    args,
                    task_id=task_id,
                    message=message,
                    session_id=session_id,
                )
        except Exception as exc:
            LOGGER.error("Exception during task %s execution on attempt %d: %s", task_id, attempt, exc)
            exit_code = 1

        if exit_code == 0:
            break
        if attempt < max_retries:
            LOGGER.warning("Task %s failed on attempt %d of %d. Retrying with a new session...", task_id, attempt, max_retries)
        else:
            LOGGER.error("Task %s failed after %d attempts.", task_id, max_retries)
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
    params: dict[str, Any] = {"trading_date": trading_date}
    market = str(getattr(args, "market", "") or "").strip().lower()
    if market:
        params["market"] = market
    needs_market = any("{market}" in str(item.filename or "") for item in task.contract.outputs)
    if needs_market and not market:
        raise TaskActivationError("Missing required --market (us|cn|hk) for this task artifact")
    validator = TaskOutputValidator(manager)
    artifacts = _select_eval_artifacts(task, str(args.artifact or ""))
    if not artifacts:
        raise TaskActivationError(f"Task {task_id} has no required output artifacts to eval.")

    total_issues = 0
    for artifact in artifacts:
        filename = resolve_filename_template(artifact.filename, params)
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
    market = str(getattr(args, "market", "") or "").strip().lower()
    manager = load_task_manager(args.config)
    pipeline = manager.get_pipeline(pipeline_id)
    if pipeline is None:
        available = ", ".join(manager.list_pipelines()) or "(none)"
        raise TaskActivationError(f"Unknown pipeline: {pipeline_id}. Available: {available}.")

    preflight_cfg = pipeline.preflight or {}
    if preflight_cfg.get("require_market") and not market:
        raise TaskActivationError("Missing required --market (us|cn|hk)")

    runtime = Runtime.from_config_store(ConfigStore(args.config))
    evaluate_preflight = getattr(
        runtime.harness,
        "evaluate_pipeline_preflight",
        None,
    )
    if not callable(evaluate_preflight):
        raise TaskActivationError(f"Harness does not support pipeline preflight: {pipeline_id}")
    try:
        preflight = evaluate_preflight(
            pipeline,
            trading_date=trading_date,
            market=market or None,
            force=bool(getattr(args, "force", False)),
        )
    except ValueError as exc:
        raise TaskActivationError(str(exc)) from exc
    if preflight.action == "skip":
        LOGGER.info("%s", preflight.reason)
        return 0
    if preflight.open_markets:
        LOGGER.info("Preflight ok: %s", preflight.reason)

    store = ConfigStore(args.config)
    config = store.snapshot()

    if not getattr(args, "force_rerun", False) and pipeline_id == "daily-market-events":
        output_root = Path(config.tasks.output_root).expanduser()
        file_path = (
            output_root / "event-trigger" / f"market_event_triggers_{market}_{trading_date}.jsonl"
        )
        if file_path.is_file():
            LOGGER.info("Task output %s already exists. Skipping pipeline execution.", file_path)
            if not getattr(args, "skip_upload", False):
                return 0 if await _upload_daily_market_events(args.config, trading_date, market) else 1
            return 0

    max_retries = int(args.max_retries) if args.max_retries is not None else 3
    if max_retries < 1:
        max_retries = 1
    exit_code = 1

    for attempt in range(1, max_retries + 1):
        try:
            if bool(args.local):
                exit_code = await _run_pipeline_task_local(
                    args,
                    pipeline_id=pipeline_id,
                    trading_date=trading_date,
                    market=market,
                )
            else:
                exit_code = await _run_pipeline_task_remote(
                    args,
                    pipeline_id=pipeline_id,
                    trading_date=trading_date,
                    market=market,
                )
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
            return 0 if await _upload_daily_market_events(args.config, trading_date, market) else 1
    else:
        LOGGER.error(f"Pipeline execution failed: exit_code: {exit_code}")
    return exit_code


async def _upload_daily_market_events(config_path: str, trading_date: str, market: str) -> bool:
    store = ConfigStore(config_path)
    config = store.snapshot()

    market_code = str(market or "").strip().lower()
    output_root = Path(config.tasks.output_root).expanduser()
    file_path = output_root / "event-trigger" / f"market_event_triggers_{market_code}_{trading_date}.jsonl"
    if not file_path.is_file():
        LOGGER.error("Cannot upload events: %s not found", file_path)
        return False

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
        return False

    if not items:
        LOGGER.info("No market events to upload.")
        return True

    sdk_cfg = config.dojosdk
    client_kwargs = {
        "api_key": sdk_cfg.api_key if sdk_cfg else None,
        "base_url": sdk_cfg.base_url if sdk_cfg else None,
        "timeout": sdk_cfg.timeout if sdk_cfg else 60.0,
        "max_retries": sdk_cfg.max_retries if sdk_cfg else 1,
    }
    client = AsyncDojo(**{key: value for key, value in client_kwargs.items() if value is not None})
    try:
        LOGGER.info("Uploading %d market events (%s) to DojoSDK...", len(items), market_code or "?")
        for item in items:
            if not isinstance(item, dict):
                continue
            # SDK create accepts only these fields; market identity lives in affected_markets.
            await client.analysis.create_market_dynamics(
                event_time=str(item.get("event_time") or ""),
                event_summary=item.get("event_summary") or {},
                sector_impacts=item.get("sector_impacts") or [],
            )
        LOGGER.info("Successfully uploaded market events.")
        return True
    except Exception as exc:
        LOGGER.error("Failed to upload market events: %s", exc)
        return False
    finally:
        await _close_dojo_client(client)


async def run_tasks_command(args: argparse.Namespace) -> int:
    if args.tasks_command == "run":
        try:
            if str(getattr(args, "task", "") or "").strip():
                return await run_single_task(args)
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
