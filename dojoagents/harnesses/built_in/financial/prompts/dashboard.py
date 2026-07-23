"""Dashboard-only financial tool protocol contributor."""

from dojoagents.agent.dashboard_tool_protocol import DASHBOARD_TOOL_PROTOCOL


def dashboard_tool_prompt(_context=None) -> str:
    return DASHBOARD_TOOL_PROTOCOL


__all__ = ["dashboard_tool_prompt"]
