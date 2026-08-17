"""Dashboard-only financial tool protocol contributor."""

from dojoagents.tasks.run_context import PACK_DASHBOARD_PROTOCOL, RunContext

from .dashboard_protocol import DASHBOARD_TOOL_PROTOCOL


def dashboard_tool_prompt(context=None) -> str:
    if context is None:
        return DASHBOARD_TOOL_PROTOCOL
    request = getattr(context, "request", None)
    if request is None:
        return DASHBOARD_TOOL_PROTOCOL
    ctx = RunContext.resolve(request)
    if not ctx.has_prompt_pack(PACK_DASHBOARD_PROTOCOL):
        return ""
    return DASHBOARD_TOOL_PROTOCOL


__all__ = ["dashboard_tool_prompt"]
