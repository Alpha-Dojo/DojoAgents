"""Registration point for generic visualization tools used by FinancialHarness."""

from dojoagents.tools.agent_viz import get_agent_viz_specs

VISUALIZATION_TOOL_NAMES = ("agent_viz_build", "agent_viz_kinds")

__all__ = ["VISUALIZATION_TOOL_NAMES", "get_agent_viz_specs"]
