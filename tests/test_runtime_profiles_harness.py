from __future__ import annotations

from dojoagents.agent.runtime import RuntimeFactory
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
