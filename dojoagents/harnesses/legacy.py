"""Temporary contract for Harness-owned contributions to the synchronous Runtime facade."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class LegacyRuntimeContributions:
    """Scenario behavior required by ``Runtime.from_config_store``.

    New integrations should use ``Runtime.create``. This contract keeps the old
    synchronous entry point domain-neutral while existing hosts migrate.
    """

    artifact_adapter: Any = None
    presenter_factory: Callable[[], Any] | None = None
    behavior: Any = None
    additional_tool_specs: tuple[Any, ...] = ()
    task_harness_factory: Callable[[Any, Any], tuple[Any, ...]] | None = None
    task_directories: tuple[Any, ...] = ()
    pipeline_directories: tuple[Any, ...] = ()

    def build_task_harnesses(self, task_manager: Any, config: Any) -> tuple[Any, ...]:
        if self.task_harness_factory is None:
            return ()
        return tuple(self.task_harness_factory(task_manager, config))


__all__ = ["LegacyRuntimeContributions"]
