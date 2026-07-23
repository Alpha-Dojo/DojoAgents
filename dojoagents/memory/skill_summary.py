from __future__ import annotations

import re
from pathlib import Path
from typing import Any


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
        self.generated_skill_dir.mkdir(parents=True, exist_ok=True)

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
        slug = self._slug(self.session_id or "session")
        skill_dir = self.generated_skill_dir / f"generated-{slug}"
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill = (
            "---\n"
            f"name: generated-{slug}\n"
            "description: Generated procedural memory from a DojoAgents session.\n"
            "---\n\n"
            "# Generated Workflow Memory\n\n"
            "Use this skill only as procedural context for similar future analysis.\n\n"
            "## Session Summary\n\n"
            f"{text}\n"
        )
        (skill_dir / "SKILL.md").write_text(skill, encoding="utf-8")

    async def shutdown(self) -> None:
        return None

    @staticmethod
    def _slug(value: str) -> str:
        slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip()).strip("-").lower()
        return slug or "session"
