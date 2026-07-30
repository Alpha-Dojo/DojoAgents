from __future__ import annotations

import inspect
from dataclasses import replace
from typing import Any

from dojoagents.agent.models import AgentResponse, ChatRequest
from dojoagents.logging import LOGGER
from dojoagents.tasks.activator import TaskActivationError


async def _invoke_run_agent(
    run_agent: Any,
    request: ChatRequest,
    *,
    event_sink: Any | None = None,
) -> AgentResponse:
    if event_sink is None:
        return await run_agent(request)
    try:
        signature = inspect.signature(run_agent)
    except (TypeError, ValueError):
        return await run_agent(request, event_sink=event_sink)
    if "event_sink" in signature.parameters or any(param.kind is inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
        return await run_agent(request, event_sink=event_sink)
    return await run_agent(request)


def _emit_pipeline_step_phase(event_sink: Any | None, request: ChatRequest) -> None:
    if event_sink is None or not hasattr(event_sink, "phase"):
        return
    pipeline = request.metadata.get("pipeline") if isinstance(request.metadata, dict) else None
    active = request.metadata.get("active_task") if isinstance(request.metadata, dict) else None
    task_id = ""
    if isinstance(active, dict):
        task_id = str(active.get("task_id") or "").strip()
    step = ""
    if isinstance(pipeline, dict):
        step = str(pipeline.get("step") or "").strip()
    label = f"pipeline step {step}: {task_id}".strip(": ")
    try:
        event_sink.phase(label or "pipeline")
    except Exception:
        LOGGER.exception("Failed to emit pipeline step phase event")


def _finalize_event_sink(event_sink: Any | None, response: AgentResponse | None) -> None:
    """Emit a single terminal done after deferred pipeline step invokes."""
    if event_sink is None or not hasattr(event_sink, "done"):
        return
    events = getattr(event_sink, "events", None) or []
    if events and events[-1].get("type") in {"done", "error"}:
        return
    tool_trace: list[Any] = []
    if response is not None and isinstance(response.metadata, dict):
        raw_trace = response.metadata.get("tool_trace")
        if isinstance(raw_trace, list):
            tool_trace = raw_trace
    try:
        event_sink.done(model_id="", tool_trace=tool_trace, tool_steps=len(tool_trace))
    except Exception:
        LOGGER.exception("Failed to emit deferred pipeline done event")


async def run_agent_with_tasks(
    runtime: Any,
    request: ChatRequest,
    *,
    run_agent: Any,
    event_sink: Any | None = None,
    max_pipeline_steps: int = 5,
) -> AgentResponse:
    """Preprocess task commands and optionally continue a pipeline in the same session."""
    router = getattr(runtime, "command_router", None)
    pipeline_runner = getattr(runtime, "pipeline_runner", None)

    if router is None:
        return await _invoke_run_agent(run_agent, request, event_sink=event_sink)

    try:
        current = router.preprocess(request)
    except TaskActivationError as exc:
        return AgentResponse(
            content=str(exc),
            session_id=request.session_id,
            metadata={"error": "task_activation", "task_activation_error": str(exc)},
        )

    last_response: AgentResponse | None = None
    try:
        for step_idx in range(max(1, max_pipeline_steps)):
            _emit_pipeline_step_phase(event_sink, current)
            last_response = await _invoke_run_agent(run_agent, current, event_sink=event_sink)
            if pipeline_runner is None:
                return last_response
            advance = pipeline_runner.maybe_advance(current, last_response)
            if advance.validation_errors:
                last_response.metadata.setdefault("pipeline_validation_errors", [])
                last_response.metadata["pipeline_validation_errors"].extend(advance.validation_errors)
                last_response = _append_pipeline_notice(
                    last_response,
                    title="Pipeline stopped",
                    details=advance.validation_errors,
                )
            if advance.next_request is None:
                if advance.completed:
                    last_response.metadata["pipeline_completed"] = True
                return last_response
            LOGGER.info(
                "Pipeline advancing: pipeline=%s next_step=%s session_id=%s",
                (advance.next_request.metadata.get("pipeline") or {}).get("id"),
                (advance.next_request.metadata.get("active_task") or {}).get("task_id"),
                current.session_id,
            )
            current = advance.next_request
            current.metadata["pipeline_step_index"] = step_idx + 2

        if last_response is not None:
            last_response.metadata["pipeline_completed"] = False
            last_response.metadata["pipeline_error"] = "max_pipeline_steps_exceeded"
            last_response = _append_pipeline_notice(
                last_response,
                title="Pipeline incomplete",
                details=["max_pipeline_steps_exceeded"],
            )
        return last_response or AgentResponse(content="", session_id=request.session_id)
    finally:
        # AgentLoop defers done while pipeline metadata is present so SSE stays open
        # across steps; close the outer sink exactly once here.
        if isinstance(getattr(current, "metadata", None), dict) and current.metadata.get("pipeline"):
            _finalize_event_sink(event_sink, last_response)


def _append_pipeline_notice(
    response: AgentResponse,
    *,
    title: str,
    details: list[str],
) -> AgentResponse:
    if not details:
        return response
    metadata = dict(response.metadata)
    metadata["pipeline_notice"] = {"title": title, "details": list(details)}
    body = "\n".join(str(item) for item in details if str(item).strip())
    suffix = f"\n\n⚠️ {title}: {body}"
    content = str(response.content or "")
    if body and body not in content:
        content = f"{content.rstrip()}{suffix}"
    return replace(response, content=content, metadata=metadata)
