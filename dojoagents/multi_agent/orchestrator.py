"""High-level orchestration coordinator for multi-agent workflows."""

from __future__ import annotations

from typing import Any


ORCHESTRATION_PROMPT = (
    "You are operating in multi-agent orchestration mode. "
    "You have access to specialist agents that you can delegate tasks to:\n"
    "- **analyst**: Market research, data analysis, trend evaluation\n"
    "- **implementer**: Code generation, strategy coding, implementation\n"
    "- **reviewer**: QA, validation, backtesting, code review\n\n"
    "Use the `delegate_task` tool to assign subtasks to specialist agents. "
    "Coordinate their results to produce a comprehensive response."
)


class Orchestrator:
    """Coordinates multi-agent orchestration across specialist workers."""

    def __init__(self) -> None:
        self._active_sessions: dict[str, str] = {}

    def get_orchestration_prompt(self) -> str:
        """Return system prompt instructions for the LLM about delegation."""
        return ORCHESTRATION_PROMPT

    def activate(self, action: str, session_id: str) -> None:
        """Mark a session as needing multi-agent orchestration."""
        self._active_sessions[session_id] = action

    def is_active(self, session_id: str) -> bool:
        """Check whether a session is currently in multi-agent mode."""
        return session_id in self._active_sessions

    def get_action(self, session_id: str) -> str | None:
        """Return the activation action for a session, or None."""
        return self._active_sessions.get(session_id)
