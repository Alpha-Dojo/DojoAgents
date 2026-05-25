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
logging:
  level: DEBUG
  format: "%(levelname)s:%(message)s"
  date_format: "%H:%M:%S"
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
    assert snapshot.logging.level == "DEBUG"
    assert snapshot.logging.format == "%(levelname)s:%(message)s"
    assert snapshot.logging.date_format == "%H:%M:%S"

    redacted = store.redacted()
    assert "secret-value" not in str(redacted)
    assert redacted["llm_provider"]["providers"]["openai_compatible"]["api_key"] == "***"


def test_config_store_logging_defaults():
    from dojoagents.config.loader import ConfigStore

    snapshot = ConfigStore(path="/tmp/dojoagents-missing-config.yaml").snapshot()

    assert snapshot.logging.level == "INFO"
    assert "%(asctime)s" in snapshot.logging.format
    assert "%(process)d" in snapshot.logging.format
    assert "%(thread)d" in snapshot.logging.format
    assert "%(filename)s:%(lineno)d" in snapshot.logging.format
    assert snapshot.logging.date_format == "%Y-%m-%d %H:%M:%S"


def test_global_logger_uses_configured_format_without_duplicate_handlers():
    import io

    from dojoagents.config.models import LoggingConfig
    from dojoagents.logging import configure_logging, get_logger

    stream = io.StringIO()
    config = LoggingConfig(
        level="DEBUG",
        format="%(process)d|%(thread)d|%(filename)s:%(lineno)d|%(levelname)s|%(message)s",
        date_format="%H:%M:%S",
    )

    logger = configure_logging(config, stream=stream)
    configure_logging(config, stream=stream)
    get_logger("test").debug("hello")

    lines = stream.getvalue().strip().splitlines()
    assert len(lines) == 1
    assert "|DEBUG|hello" in lines[0]
    assert "test_core_contracts.py:" in lines[0]
    assert logger.name == "dojoagents"


def test_global_logger_rejects_invalid_level():
    import pytest

    from dojoagents.config.models import LoggingConfig
    from dojoagents.logging import configure_logging

    with pytest.raises(ValueError, match="Invalid log level"):
        configure_logging(LoggingConfig(level="NOPE"))


def test_module_logger_initializes_from_config_store_yaml(tmp_path, monkeypatch):
    import importlib

    config_dir = tmp_path / ".dojo"
    config_dir.mkdir()
    (config_dir / "agents.yaml").write_text(
        """
logging:
  level: DEBUG
  format: "CONFIG:%(levelname)s:%(message)s"
  date_format: "%H:%M"
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(tmp_path))

    import dojoagents.logging as dojo_logging

    dojo_logging = importlib.reload(dojo_logging)
    handler = next(
        handler
        for handler in dojo_logging.LOGGER.handlers
        if getattr(handler, "_dojoagents_managed_handler", False)
    )

    assert dojo_logging.LOGGER.level == 10
    assert handler.formatter._fmt == "CONFIG:%(levelname)s:%(message)s"
    assert handler.formatter.datefmt == "%H:%M"


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


@pytest.mark.asyncio
async def test_agent_loop_sanitizes_tool_names_for_openai_compatible_providers():
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
                        name="dojo_market_snapshot",
                        arguments={"symbols": ["BTC-USD"]},
                    )
                ],
            ),
            LLMResult(content="done"),
        ]
    )
    loop = AgentLoop(
        llm_provider=llm,
        tool_executor=ToolExecutor(registry, SandboxPolicy(timeout_seconds=2)),
        skill_manager=SkillManager([]),
        memory_manager=MemoryManager(),
        extension_registry=DojoExtensionRegistry(),
        config=AgentConfig(model="test-model", max_iterations=3),
    )

    response = await loop.run(
        ChatRequest(user_id="local", session_id="s1", message="Analyze BTC.")
    )

    assert response.content == "done"
    assert llm.calls[0]["tools"][0]["name"] == "dojo_market_snapshot"
    assistant_message = llm.calls[1]["messages"][-2]
    tool_message = llm.calls[1]["messages"][-1]
    assert assistant_message["tool_calls"][0]["function"]["name"] == "dojo_market_snapshot"
    assert tool_message["name"] == "dojo_market_snapshot"
    assert tool_message["content"] == "snapshot:BTC-USD"
