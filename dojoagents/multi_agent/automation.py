from __future__ import annotations

from typing import Any

from dojoagents.agent.models import ChatRequest
from dojoagents.multi_agent.pool import AgentPool
from dojoagents.utils.event_bus import event_bus


class MultiAgentAutoDispatcher:
    def __init__(self, pool: AgentPool) -> None:
        self.pool = pool
        event_bus.subscribe("ToolExecutionFailed", self.handle_tool_failure)
        event_bus.subscribe("DataVolumeLarge", self.handle_large_data)

    async def handle_tool_failure(self, payload: dict[str, Any]) -> str | None:
        """Automatically spawn a Reviewer agent when code execution fails."""
        tool_name = payload["tool_name"]
        args = payload["args"]
        error_msg = payload["error"]
        session_id = payload["session_id"]

        if tool_name != "code_execution":
            return None

        failed_code = args.get("code", "")
        if not failed_code:
            failed_code = args.get("command", "")

        try:
            reviewer = self.pool.get_or_create("reviewer")
        except KeyError:
            return None

        fix_request = ChatRequest(
            message=(
                f"The following execution failed with error:\n"
                f"```\n{error_msg}\n```\n\n"
                f"Original input:\n"
                f"```\n{failed_code}\n```\n\n"
                f"Please analyze the error, fix the issue, and provide a corrected outcome/result."
            ),
            user_id="multi_agent_dispatcher",
            channel="internal",
            session_id=f"review-{session_id}",
        )

        response = await reviewer.run(fix_request)
        return response.content

    async def handle_large_data(self, payload: dict[str, Any]) -> str | None:
        """Automatically spawn an Analyst agent when large data is returned."""
        data_summary = payload["data_summary"]
        session_id = payload["session_id"]

        try:
            analyst = self.pool.get_or_create("analyst")
        except KeyError:
            return None

        analyze_request = ChatRequest(
            message=(
                f"A tool returned a large volume of market data. "
                f"Please analyze the following data summary and extract key insights:\n\n"
                f"{data_summary}"
            ),
            user_id="multi_agent_dispatcher",
            channel="internal",
            session_id=f"analysis-{session_id}",
        )

        response = await analyst.run(analyze_request)
        return response.content
