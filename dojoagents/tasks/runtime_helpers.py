from __future__ import annotations

import inspect
from dataclasses import replace
from typing import Any

from dojoagents.agent.models import AgentResponse, ChatRequest
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
    for step_idx in range(max(1, max_pipeline_steps)):
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
