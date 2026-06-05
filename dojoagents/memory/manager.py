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

    def as_hook_provider(self) -> MemoryHookProvider:
        return MemoryHookProvider(self)


class MemoryHookProvider:
    def __init__(self, manager: MemoryManager) -> None:
        self.manager = manager

    def register_hooks(self, registry: Any, **kwargs: Any) -> None:
        from strands.hooks.events import BeforeInvocationEvent, MessageAddedEvent, AfterInvocationEvent
        registry.add_callback(BeforeInvocationEvent, self._on_before_invocation)
        registry.add_callback(MessageAddedEvent, self._on_message_added)
        registry.add_callback(AfterInvocationEvent, self._on_after_invocation)

    async def _on_before_invocation(self, event: Any) -> None:
        session_id = event.invocation_state.get("session_id", "default")
        await self.manager.initialize(session_id)
        # Prefetch memory context based on the user's latest query
        query = ""
        if event.messages:
            last_msg = event.messages[-1]
            if last_msg.get("role") == "user":
                content = last_msg.get("content")
                if isinstance(content, list):
                    query = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and "text" in b)
                elif isinstance(content, str):
                    query = content
        
        if query:
            mem_prompt = await self.manager.prefetch_all(query, session_id=session_id)
            if mem_prompt and event.messages:
                # Add as a system block
                event.messages.insert(0, {
                    "role": "system",
                    "content": [{"type": "text", "text": mem_prompt}]
                })

    async def _on_message_added(self, event: Any) -> None:
        pass

    async def _on_after_invocation(self, event: Any) -> None:
        # Sync the final turn at the end of invocation
        agent = event.agent
        if agent and agent.messages:
            assistant_content = ""
            user_content = ""
            session_id = event.invocation_state.get("session_id", "default")
            
            # Walk backwards to find assistant message and user message
            idx = len(agent.messages) - 1
            while idx >= 0:
                msg = agent.messages[idx]
                if msg.get("role") == "assistant" and not assistant_content:
                    content = msg.get("content")
                    if isinstance(content, list):
                        assistant_content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and "text" in b)
                    elif isinstance(content, str):
                        assistant_content = content
                elif msg.get("role") == "user" and assistant_content and not user_content:
                    content = msg.get("content")
                    if isinstance(content, list):
                        curr_user_content = "\n".join(b.get("text", "") for b in content if isinstance(b, dict) and "text" in b)
                    elif isinstance(content, str):
                        curr_user_content = content
                    else:
                        curr_user_content = ""
                    if curr_user_content.strip():
                        user_content = curr_user_content
                        break
                idx -= 1
            
            if user_content and assistant_content:
                await self.manager.sync_turn(user_content, assistant_content, session_id=session_id)
        
        # Finally trigger session end callbacks
        await self.manager.on_session_end(agent.messages if agent else [])
