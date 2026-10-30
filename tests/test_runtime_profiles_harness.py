from __future__ import annotations

import pytest

from dojoagents.agent.runtime import Runtime, RuntimeFactory
from dojoagents.config.loader import ConfigStore


def test_runtime_factory_reuses_same_graph_and_splits_capability_changes(tmp_path):
    config_path = tmp_path / "agents.yaml"
    config_path.write_text(
        """
harness:
  id: minimal
  factory: tests.fixtures.minimal_harness:create_harness
tasks:
  enabled: false
profiles:
  model_only:
    agent:
      model: alternate
  restricted:
    tools:
      sandbox:
        timeout_seconds: 7
""",
        encoding="utf-8",
    )
    factory = RuntimeFactory(ConfigStore(config_path))
    default = factory.for_profile("default")
    assert factory.for_profile("model_only") is default
    assert factory.for_profile("restricted") is not default
    assert default.capabilities.descriptor.id == "minimal"


@pytest.mark.anyio
@pytest.mark.parametrize("retries", [0, 2, 5])
async def test_runtime_passes_provider_retry_configuration(tmp_path, retries):
    config_path = tmp_path / "agents.yaml"
    config_path.write_text(
        f"""
harness:
  id: minimal
  factory: tests.fixtures.minimal_harness:create_harness
llm_provider:
  default: qwen
  providers:
    qwen:
      model: test-model
      api_key: test-only-key
      max_retries: {retries}
sessions:
  enabled: false
  root: {tmp_path / "sessions"}
tasks:
  enabled: false
""",
        encoding="utf-8",
    )
    runtime = await Runtime.create(ConfigStore(config_path))
    try:
        assert runtime.agent.llm_provider.max_retries == retries
    finally:
        await runtime.shutdown()
