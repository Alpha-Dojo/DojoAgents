import asyncio
from pathlib import Path

import pytest


def test_config_store_loads_defaults_merges_user_config_expands_env_and_redacts(tmp_path, monkeypatch):
    from dojoagents.config.loader import ConfigStore

    monkeypatch.setenv("DOJO_TEST_KEY", "secret-value")
    cfg_path = tmp_path / "agents.yaml"
    cfg_path.write_text(
        """
llm_provider:
  default: openai_compatible
  providers:
    openai_compatible:
      model: qwen-plus
      base_url: "${DOJO_BASE_URL}"
      api_key_env: DOJO_TEST_KEY
dashboard:
  port: 9999
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("DOJO_BASE_URL", "https://models.example.test/v1")

    store = ConfigStore(cfg_path)
    snapshot = store.snapshot()

    assert snapshot.llm_provider.default == "openai_compatible"
    assert snapshot.llm_provider.providers["openai_compatible"].base_url == "https://models.example.test/v1"
    assert snapshot.dashboard.port == 9999
    assert snapshot.memory.provider == "skill_summary"

    redacted = store.redacted()
    assert "secret-value" not in str(redacted)
    assert redacted["llm_provider"]["providers"]["openai_compatible"]["api_key"] == "***"


@pytest.mark.asyncio
async def test_tool_registry_and_executor_return_ordered_structured_results():
    from dojoagents.agent.models import ToolCall
    from dojoagents.tools.executor import ToolExecutor
    from dojoagents.tools.registry import ToolRegistry, ToolSpec
    from dojoagents.tools.sandbox import SandboxPolicy

    async def echo(args):
        return {"content": args["value"]}

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="echo",
            description="Echo a value.",
            parameters={"type": "object"},
            handler=echo,
        )
    )
    executor = ToolExecutor(registry, SandboxPolicy(timeout_seconds=2))

    results = await executor.execute_many(
        [
            ToolCall(id="one", name="echo", arguments={"value": "first"}),
            ToolCall(id="two", name="missing", arguments={}),
        ],
        session_id="s1",
    )

    assert [result.call_id for result in results] == ["one", "two"]
    assert results[0].ok is True
    assert results[0].content == "first"
    assert results[1].ok is False
    assert "not registered" in results[1].error
    assert results.to_messages()[0]["tool_call_id"] == "one"


@pytest.mark.asyncio
async def test_memory_manager_uses_skill_summary_provider_at_session_end(tmp_path):
    from dojoagents.memory.manager import MemoryManager
    from dojoagents.memory.skill_summary import SkillSummaryMemoryProvider

    provider = SkillSummaryMemoryProvider(generated_skill_dir=tmp_path)
    manager = MemoryManager()
    manager.add_provider(provider)

    await manager.initialize("session-1", platform="cli")
    await manager.sync_turn(
        "Please remember my BTC funding workflow",
        "Use funding, open interest, and spot premium.",
        session_id="session-1",
    )
    await manager.on_session_end(
        [
            {"role": "user", "content": "Please remember my BTC funding workflow"},
            {"role": "assistant", "content": "Use funding, open interest, and spot premium."},
        ]
    )

    generated = list(tmp_path.glob("generated-session-1*/SKILL.md"))
    assert generated
    assert "BTC funding workflow" in generated[0].read_text(encoding="utf-8")


def test_dojo_extension_registry_exposes_tool_specs_and_prompt_context():
    from dojoagents.dojo_extensions.quant_data import DojoMarketDataExtension
    from dojoagents.dojo_extensions.registry import DojoExtensionRegistry
    from dojoagents.quant.context import QuantContext

    registry = DojoExtensionRegistry()
    registry.register(DojoMarketDataExtension())

    tools = registry.tool_specs()
    assert [tool.name for tool in tools] == ["dojo.market.snapshot"]
    prompt = registry.prompt_context(
        QuantContext(market="crypto", symbols=["BTC-USD"], timeframe="1d")
    )
    assert "BTC-USD" in prompt
    assert registry.status()[0]["name"] == "dojo_market_data"


@pytest.mark.asyncio
async def test_agent_loop_runs_tool_roundtrip_and_syncs_memory():
    from dojoagents.agent.loop import AgentLoop
    from dojoagents.agent.models import ChatRequest, LLMResult, ToolCall
    from dojoagents.agent.providers import StaticLLMProvider
    from dojoagents.config.models import AgentConfig
    from dojoagents.dojo_extensions.registry import DojoExtensionRegistry
    from dojoagents.memory.manager import MemoryManager
    from dojoagents.skills.manager import SkillManager
    from dojoagents.tools.executor import ToolExecutor
    from dojoagents.tools.registry import ToolRegistry, ToolSpec
    from dojoagents.tools.sandbox import SandboxPolicy

    async def market_snapshot(args):
        return {"content": f"snapshot:{','.join(args['symbols'])}"}

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            name="dojo.market.snapshot",
            description="Return a market snapshot.",
            parameters={"type": "object"},
            handler=market_snapshot,
        )
    )
    llm = StaticLLMProvider(
        [
            LLMResult(
                content="",
                tool_calls=[
                    ToolCall(
                        id="call-1",
                        name="dojo.market.snapshot",
                        arguments={"market": "crypto", "symbols": ["BTC-USD"]},
                    )
                ],
            ),
            LLMResult(content="BTC looks constructive after snapshot review."),
        ]
    )
    memory = MemoryManager()
    loop = AgentLoop(
        llm_provider=llm,
        tool_executor=ToolExecutor(registry, SandboxPolicy(timeout_seconds=2)),
        skill_manager=SkillManager([]),
        memory_manager=memory,
        extension_registry=DojoExtensionRegistry(),
        config=AgentConfig(model="test-model", max_iterations=3),
    )

    response = await loop.run(
        ChatRequest(
            user_id="local",
            session_id="s1",
            message="Analyze BTC.",
        )
    )

    assert response.content == "BTC looks constructive after snapshot review."
    assert response.metadata["iterations"] == 2
    assert memory.turns[-1]["assistant"] == response.content
    assert any(message.get("role") == "tool" for message in llm.calls[1]["messages"])
