from __future__ import annotations

from pathlib import Path
from typing import Any

import anyio

from dojoagents.memory.file_io import atomic_write_text
from dojoagents.memory.path_names import (
    SESSION_HASH_LENGTH,
    SESSION_PATH_COMPONENT_MAX_LENGTH,
    bounded_session_name,
    slug_session_id,
)


GENERATED_SKILL_NAME_MAX_LENGTH = SESSION_PATH_COMPONENT_MAX_LENGTH


class SkillSummaryMemoryProvider:
    name = "skill_summary"

    def __init__(self, generated_skill_dir: str | Path = "~/.dojo/skills/generated") -> None:
        self.generated_skill_dir = Path(generated_skill_dir).expanduser()
        self.session_id = ""
        self.turns: list[dict[str, str]] = []

    def is_available(self) -> bool:
        return True

    async def initialize(self, session_id: str, **_context: Any) -> None:
        self.session_id = session_id
        await anyio.Path(self.generated_skill_dir).mkdir(parents=True, exist_ok=True)

    def system_prompt_block(self) -> str:
        return "Memory provider: repeatable workflows may be summarized into Dojo skills."

    async def prefetch(self, _query: str, *, session_id: str) -> str:
        return ""

    async def queue_prefetch(self, _query: str, *, session_id: str) -> None:
        return None

    async def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str,
        idempotency_context: dict[str, Any] | None = None,
    ) -> None:
        self.turns.append({"user": user_content, "assistant": assistant_content})

    async def on_session_end(self, messages: list[dict[str, Any]]) -> None:
        text = "\n".join(str(message.get("content", "")) for message in messages).strip()
        if not text:
            return
        skill_name = self._generated_skill_name(self.session_id)
        skill_dir = self.generated_skill_dir / skill_name
        skill = (
            "---\n"
            f"name: {skill_name}\n"
            "description: Generated procedural memory from a DojoAgents session.\n"
            "---\n\n"
            "# Generated Workflow Memory\n\n"
            "Use this skill only as procedural context for similar future analysis.\n\n"
            "## Session Summary\n\n"
            f"{text}\n"
        )
        await atomic_write_text(skill_dir / "SKILL.md", skill)

    async def shutdown(self) -> None:
        return None

    @staticmethod
    def _slug(value: str) -> str:
        return slug_session_id(value)

    @classmethod
    def _generated_skill_name(cls, session_id: str) -> str:
        return bounded_session_name(
            session_id,
            prefix="generated-",
            max_length=GENERATED_SKILL_NAME_MAX_LENGTH,
        )


__all__ = [
    "GENERATED_SKILL_NAME_MAX_LENGTH",
    "SESSION_HASH_LENGTH",
    "SkillSummaryMemoryProvider",
]
