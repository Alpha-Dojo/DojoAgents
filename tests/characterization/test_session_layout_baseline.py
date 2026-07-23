from __future__ import annotations

import json

import pytest

from dojoagents.agent.loop import AgentLoop
from dojoagents.agent.models import ChatRequest, LLMResult
from dojoagents.agent.providers import StaticLLMProvider
from dojoagents.agent.session_manager import DojoAgentSessionManager
from dojoagents.config.models import AgentConfig
from dojoagents.dojo_extensions.registry import DojoExtensionRegistry
from dojoagents.memory.manager import MemoryManager
from dojoagents.skills.manager import SkillManager
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy


@pytest.mark.asyncio
async def test_current_session_layout_contains_all_sidecars(tmp_path):
    root = tmp_path / "sessions"
    memory = MemoryManager()
    sessions = DojoAgentSessionManager(root=root, memory_manager=memory)
    loop = AgentLoop(
        llm_provider=StaticLLMProvider(
            [
                LLMResult(content=('{"continue_unfinished": false, ' '"prior_task_summary": "", ' '"last_turn_status": "complete"}')),
                LLMResult(content="baseline reply"),
            ]
        ),
        tool_executor=ToolExecutor(ToolRegistry(), SandboxPolicy(timeout_seconds=2)),
        skill_manager=SkillManager([]),
        memory_manager=memory,
        extension_registry=DojoExtensionRegistry(),
        config=AgentConfig(
            model="test-model",
            enable_guardrails=False,
            enable_context_compression=False,
        ),
        session_manager=sessions,
    )

    request = ChatRequest(user_id="baseline-user", session_id="baseline-session", message="hello")
    handle = await sessions.begin_run(request, model="test-model", run_id="baseline-run")
    response = await loop.run(request)
    await sessions.finish_run(handle, response)

    assert response.content == "baseline reply"
    session_dir = root / "session_baseline-session"
    assert (session_dir / "dojo_session.json").is_file()
    assert (session_dir / "dojo_turns.jsonl").is_file()
    assert (session_dir / "agents" / "agent_dojo-agent" / "messages").is_dir()
    assert memory.turns[-1]["session_id"] == "baseline-session"

    summary = json.loads((session_dir / "dojo_session.json").read_text(encoding="utf-8"))
    assert summary["user_id"] == "baseline-user"
    assert summary["status"] == "idle"
    assert summary["turn_count"] == 1

    [turn] = [json.loads(line) for line in (session_dir / "dojo_turns.jsonl").read_text(encoding="utf-8").splitlines()]
    assert turn["schema_version"] == 1
    assert set(turn) >= {"turn_id", "events", "tool_trace", "usage"}
