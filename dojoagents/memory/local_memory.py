from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dojoagents.memory.provider import MemoryProvider


class LocalMemoryProvider:
    name = "local_memory"

    def __init__(self, memory_dir: str | Path = "~/.dojo/agents/memory") -> None:
        self.memory_dir = Path(memory_dir).expanduser()
        self.session_id = ""

    def is_available(self) -> bool:
        return True

    async def initialize(self, session_id: str, **_context: Any) -> None:
        self.session_id = session_id
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    def system_prompt_block(self) -> str:
        return "Memory provider: has persistent recall of consolidated summaries for the session."

    async def prefetch(self, _query: str, *, session_id: str) -> str:
        # Automatically load consolidated memory if it exists
        mem_file = self.memory_dir / f"session_{session_id}.txt"
        if mem_file.exists():
            try:
                content = mem_file.read_text(encoding="utf-8").strip()
                if content:
                    return f"[CONSOLIDATED MEMORY FROM PREVIOUS TURNS]:\n{content}"
            except Exception:
                pass
        return ""

    async def queue_prefetch(self, _query: str, *, session_id: str) -> None:
        return None

    async def sync_turn(
        self, user_content: str, assistant_content: str, *, session_id: str
    ) -> None:
        pass

    async def save_memory(self, session_id: str, content: str, metadata: dict = None) -> None:
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        mem_file = self.memory_dir / f"session_{session_id}.txt"
        # Overwrite or append consolidated summaries
        try:
            mem_file.write_text(content, encoding="utf-8")
        except Exception:
            pass

    async def retrieve_memory(self, session_id: str, query: str) -> str:
        mem_file = self.memory_dir / f"session_{session_id}.txt"
        if mem_file.exists():
            try:
                return mem_file.read_text(encoding="utf-8")
            except Exception:
                pass
        return ""

    async def on_session_end(self, messages: list[dict[str, Any]]) -> None:
        pass

    async def shutdown(self) -> None:
        pass
