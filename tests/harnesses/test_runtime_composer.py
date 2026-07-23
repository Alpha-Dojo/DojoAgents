import sys

import pytest

from dojoagents.agent.runtime import Runtime
from dojoagents.agent.models import ChatRequest, LLMResult, ToolCall
from dojoagents.agent.providers import StaticLLMProvider
from dojoagents.config.models import AgentsConfig, HarnessConfig, SessionsConfig, StoreProviderConfig
from dojoagents.harnesses.base import HarnessDescriptor
from dojoagents.harnesses.capabilities import ServiceSpec
from dojoagents.harnesses.errors import HarnessLifecycleError
from dojoagents.harnesses.lifecycle import ExternalServiceBinding
from dojoagents.sessions.models import SessionPrincipal

from tests.test_runtime_multi_agent_plan import _make_store

EVENTS = []
CREATED = 0


class Service:
    def __init__(self, name, fail=False):
        self.name = name
        self.fail = fail

    async def startup(self):
        EVENTS.append(f"service:start:{self.name}")
        if self.fail:
            raise RuntimeError("service failed")

    async def health(self):
        return True

    async def shutdown(self):
        EVENTS.append(f"service:stop:{self.name}")


class ComposeHarness:
    descriptor = HarnessDescriptor("compose", "1", "Compose")

    def __init__(self, config):
        self.config = config

    def configure(self, builder, context):
        builder.add_service(ServiceSpec("db", "harness:compose", factory=lambda: Service("db")))
        builder.add_service(
            ServiceSpec(
                "api",
                "harness:compose",
                factory=lambda: Service("api", self.config.get("fail_service", False)),
                dependencies=("db",),
            )
        )

    async def startup(self, context):
        EVENTS.append("harness:start")
        if self.config.get("fail_harness"):
            raise RuntimeError("harness failed")

    async def shutdown(self, context):
        EVENTS.append("harness:stop")


def create_compose_harness(config, context):
    global CREATED
    CREATED += 1
    return ComposeHarness(config)


def _config(tmp_path, **harness_config):
    return AgentsConfig(
        harness=HarnessConfig(
            id="compose",
            factory="tests.harnesses.test_runtime_composer:create_compose_harness",
            config=harness_config,
        ),
        sessions=SessionsConfig(
            store=StoreProviderConfig(options={"root": str(tmp_path / "sessions")}),
            blob_store=StoreProviderConfig(options={"root": str(tmp_path / "blobs")}),
        ),
    )


def test_compose_rejects_external_binding_for_undeclared_service(tmp_path):
    with pytest.raises(HarnessLifecycleError, match="not declared"):
        Runtime.compose(
            _make_store(_config(tmp_path)),
            service_bindings={
                "unknown": ExternalServiceBinding(object()),
            },
        )


@pytest.mark.asyncio
async def test_compose_is_side_effect_free_then_startup_and_shutdown_are_ordered(tmp_path):
    global CREATED
    CREATED = 0
    EVENTS.clear()
    runtime = Runtime.compose(_make_store(_config(tmp_path)), host="library")

    assert CREATED == 1
    assert runtime.state == "composed"
    assert runtime.session_store is None
    assert EVENTS == []

    await runtime.startup()
    await runtime.shutdown()
    await runtime.shutdown()

    assert runtime.state == "stopped"
    assert EVENTS == [
        "service:start:db",
        "service:start:api",
        "harness:start",
        "harness:stop",
        "service:stop:api",
        "service:stop:db",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["fail_service", "fail_harness"])
async def test_startup_failure_rolls_back_every_started_resource(tmp_path, failure):
    EVENTS.clear()
    runtime = Runtime.compose(_make_store(_config(tmp_path, **{failure: True})))

    with pytest.raises(HarnessLifecycleError):
        await runtime.startup()

    assert runtime.state == "failed"
    assert runtime.session_store is None
    assert "service:stop:db" in EVENTS


@pytest.mark.asyncio
async def test_minimal_harness_composes_without_importing_financial_modules(tmp_path):
    config = AgentsConfig(
        harness=HarnessConfig(
            id="minimal",
            factory="tests.fixtures.minimal_harness:create_harness",
        ),
        sessions=SessionsConfig(
            store=StoreProviderConfig(options={"root": str(tmp_path / "sessions")}),
            blob_store=StoreProviderConfig(options={"root": str(tmp_path / "blobs")}),
        ),
    )
    before = set(sys.modules)
    runtime = await Runtime.create(_make_store(config), host="library")
    newly_loaded = set(sys.modules).difference(before)

    assert runtime.capabilities.descriptor.id == "minimal"
    assert runtime.capabilities.tools[0].tool_names == ("echo",)
    assert not any(name.startswith("dojoagents.harnesses.built_in.financial") for name in newly_loaded)
    assert {
        "echo",
        "execute_code",
        "read_session_input",
        "read_session_output",
        "terminal",
        "tools_list",
        "web_extract",
        "web_search",
        "write_session_file",
    } <= {spec.name for spec in runtime.agent.tool_executor.registry.all()}

    runtime.agent.llm_provider = StaticLLMProvider(
        [
            LLMResult("", [ToolCall("echo-1", "echo", {"text": "hello"})]),
            LLMResult("echoed"),
        ]
    )
    response = await runtime.agent.run(ChatRequest("use echo", session_id="minimal-session", principal=SessionPrincipal("alice")))
    assert response.content == "echoed"
    assert response.metadata["tool_trace"][0]["tool"] == "echo"
    system_messages = [message for call in runtime.agent.llm_provider.calls for message in call["messages"] if message.get("role") == "system"]
    assert any("Minimal agent" in str(message.get("content")) for message in system_messages)
    await runtime.shutdown()
