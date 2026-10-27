from __future__ import annotations

from pathlib import Path
from typing import Any

import anyio

from dojoagents.logging import LOGGER
from dojoagents.memory.file_io import atomic_write_text, read_text_if_present
from dojoagents.memory.path_names import bounded_session_name


class LocalMemoryProvider:
    name = "local_memory"

    def __init__(self, memory_dir: str | Path = "~/.dojo/agents/memory") -> None:
        self.memory_dir = Path(memory_dir).expanduser()
        self.session_id = ""

    def is_available(self) -> bool:
        return True

    async def initialize(self, session_id: str, **_context: Any) -> None:
        self.session_id = session_id
        await anyio.Path(self.memory_dir).mkdir(parents=True, exist_ok=True)

    def system_prompt_block(self) -> str:
        return "Memory provider: has persistent recall of consolidated summaries for the session."

    async def prefetch(self, _query: str, *, session_id: str) -> str:
        mem_file = self._memory_file(session_id)
        try:
            content = await read_text_if_present(mem_file)
        except OSError:
            LOGGER.exception("Failed to prefetch local memory for session %s", session_id)
            return ""
        if content:
            return f"[CONSOLIDATED MEMORY FROM PREVIOUS TURNS]:\n{content.strip()}"
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
        return None

    async def save_memory(
        self,
        session_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        del metadata
        mem_file = self._memory_file(session_id)
        try:
            await atomic_write_text(mem_file, content)
        except OSError:
            LOGGER.exception("Failed to save local memory for session %s", session_id)

    async def retrieve_memory(self, session_id: str, _query: str) -> str:
        mem_file = self._memory_file(session_id)
        try:
            return await read_text_if_present(mem_file)
        except OSError:
            LOGGER.exception("Failed to retrieve local memory for session %s", session_id)
            return ""

    async def on_session_end(self, messages: list[dict[str, Any]]) -> None:
        return None

    async def shutdown(self) -> None:
        return None

    def _memory_file(self, session_id: str) -> Path:
        filename = bounded_session_name(
            session_id,
            prefix="session_",
            suffix=".txt",
        )
        return self.memory_dir / filename

