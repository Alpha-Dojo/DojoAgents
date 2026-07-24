from __future__ import annotations

from types import MappingProxyType

import pytest

from dojoagents.agent.runtime import Runtime
from dojoagents.config.models import (
    AgentsConfig,
    HarnessConfig,
    SessionsConfig,
    StoreProviderConfig,
)
from dojoagents.harnesses.built_in.financial import FinancialHarness
from dojoagents.harnesses.built_in.financial.harness import (
    FINANCIAL_SERVICE_ID,
)
from dojoagents.harnesses.lifecycle import ExternalServiceBinding

from tests.test_runtime_multi_agent_plan import _make_store


class FakeBackend:
    supported_tools = frozenset()
    tool_definitions = MappingProxyType({})

    def __init__(self) -> None:
        self.start_calls = 0
        self.stop_calls = 0

    async def startup(self) -> None:
        self.start_calls += 1

    async def health(self) -> bool:
        return True

    async def shutdown(self) -> None:
        self.stop_calls += 1


def _config(tmp_path):
    return AgentsConfig(
        harness=HarnessConfig(
            id="financial",
            factory="dojoagents.harnesses.built_in.financial:create_harness",
            config={},
        ),
        sessions=SessionsConfig(
            store=StoreProviderConfig(options={"root": str(tmp_path / "sessions")}),
            blob_store=StoreProviderConfig(options={"root": str(tmp_path / "blobs")}),
        ),
    )


def test_financial_harness_config_excludes_dashboard_app_lifecycle(tmp_path):
    runtime = Runtime.compose(_make_store(_config(tmp_path)), host="dashboard")

    assert isinstance(runtime.harness, FinancialHarness)
    assert runtime.harness.descriptor.id == "financial"
    assert not hasattr(runtime.harness.config, "data_root")
    assert not hasattr(runtime.harness.config, "refresh_enabled")
    assert runtime.capabilities.surfaces == ()


@pytest.mark.asyncio
async def test_external_backend_is_bound_without_double_lifecycle(tmp_path):
    backend = FakeBackend()
    runtime = Runtime.compose(
        _make_store(_config(tmp_path)),
        host="dashboard",
        service_bindings={FINANCIAL_SERVICE_ID: ExternalServiceBinding(backend)},
    )

    await runtime.startup()

    assert runtime.harness_runtime_context.services[FINANCIAL_SERVICE_ID] is backend
    assert runtime.agent.tool_executor.registry.get("execute_code") is not None
    assert backend.start_calls == 0

    await runtime.shutdown()
    await runtime.shutdown()
    assert backend.stop_calls == 0


@pytest.mark.asyncio
async def test_owned_external_backend_uses_runtime_lifecycle(tmp_path):
    backend = FakeBackend()
    runtime = await Runtime.create(
        _make_store(_config(tmp_path)),
        host="api",
        service_bindings={
            FINANCIAL_SERVICE_ID: ExternalServiceBinding(
                backend,
                runtime_owns_lifecycle=True,
            )
        },
    )

    assert backend.start_calls == 1
    await runtime.shutdown()
    assert backend.stop_calls == 1
