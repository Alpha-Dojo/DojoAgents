from __future__ import annotations

from typing import Any

from dojoagents.memory.provider import MemoryProvider


class MemoryManager:
    def __init__(self) -> None:
        self._providers: list[MemoryProvider] = []
        self._has_external = False
        self.turns: list[dict[str, str]] = []

    def add_provider(self, provider: MemoryProvider) -> None:
        if provider.name != "skill_summary":
            if self._has_external:
                raise ValueError("Only one external memory provider can be active")
            self._has_external = True
        self._providers.append(provider)

    async def initialize(self, session_id: str, **context: Any) -> None:
        for provider in self._providers:
            if provider.is_available():
                await provider.initialize(session_id, **context)

    def build_system_prompt(self) -> str:
        blocks = [provider.system_prompt_block() for provider in self._providers]
        return "\n\n".join(block for block in blocks if block)

    async def prefetch_all(self, query: str, *, session_id: str) -> str:
        blocks = []
        for provider in self._providers:
            blocks.append(await provider.prefetch(query, session_id=session_id))
        return "\n\n".join(block for block in blocks if block)

    async def sync_turn(
        self, user_content: str, assistant_content: str, *, session_id: str
    ) -> None:
        self.turns.append(
            {"session_id": session_id, "user": user_content, "assistant": assistant_content}
        )
        for provider in self._providers:
            await provider.sync_turn(
                user_content, assistant_content, session_id=session_id
            )

    async def queue_prefetch_all(self, query: str, *, session_id: str) -> None:
        for provider in self._providers:
            await provider.queue_prefetch(query, session_id=session_id)

    async def on_session_end(self, messages: list[dict[str, Any]]) -> None:
        for provider in self._providers:
            await provider.on_session_end(messages)

    async def shutdown(self) -> None:
        for provider in self._providers:
            await provider.shutdown()
