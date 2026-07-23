"""Validated configuration adapter for the built-in financial Harness."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from dojoagents.harnesses.context import HarnessBuildContext


def _path(value: Any, default: Path) -> Path:
    return Path(str(value if value is not None else default)).expanduser().resolve()


def _bool(options: Mapping[str, Any], key: str, default: bool) -> bool:
    value = options.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"financial harness config '{key}' must be a boolean")
    return value


@dataclass(frozen=True)
class FinancialSDKConfig:
    api_key: str | None
    base_url: str | None
    timeout: float
    max_retries: int
    cache_dir: Path
    offline_mode: bool

    def __post_init__(self) -> None:
        if self.timeout <= 0:
            raise ValueError("financial SDK timeout must be greater than zero")
        if self.max_retries < 0:
            raise ValueError("financial SDK max_retries must not be negative")


@dataclass(frozen=True)
class FinancialTasksConfig:
    enabled: bool
    directories: tuple[Path, ...]
    output_root: Path


@dataclass(frozen=True)
class FinancialHarnessConfig:
    sdk: FinancialSDKConfig
    tasks: FinancialTasksConfig
    data_root: Path
    portfolio_data_root: Path
    memory_generated_skill_dir: Path
    preload_offline_data: bool = True
    preload_registry: bool = True
    refresh_enabled: bool = False
    refresh_poll_seconds: int = 3600

    def __post_init__(self) -> None:
        if self.refresh_poll_seconds <= 0:
            raise ValueError("financial harness config 'refresh_poll_seconds' must be greater than zero")

    @classmethod
    def from_context(cls, context: HarnessBuildContext) -> "FinancialHarnessConfig":
        """Adapt legacy dashboard/dojosdk/tasks fields with harness.config overrides."""

        root = context.config
        options = dict(context.harness_config)
        dashboard = root.dashboard.financial
        sdk = root.dojosdk
        tasks = root.tasks
        host = str(context.host).lower()

        sdk_config = FinancialSDKConfig(
            api_key=options.get("api_key", sdk.api_key),
            base_url=options.get("base_url", sdk.base_url),
            timeout=float(options.get("timeout", sdk.timeout)),
            max_retries=int(options.get("max_retries", sdk.max_retries)),
            cache_dir=_path(options.get("sdk_cache_dir"), dashboard.sdk_cache_path),
            offline_mode=_bool(options, "offline_mode", True),
        )
        task_dirs = options.get("task_dirs", tasks.dirs)
        if not isinstance(task_dirs, (list, tuple)):
            raise ValueError("financial harness config 'task_dirs' must be a list")
        task_config = FinancialTasksConfig(
            enabled=_bool(options, "tasks_enabled", tasks.enabled),
            directories=tuple(_path(item, context.config_dir) for item in task_dirs),
            output_root=_path(options.get("task_output_root"), Path(tasks.output_root)),
        )
        return cls(
            sdk=sdk_config,
            tasks=task_config,
            data_root=_path(options.get("data_root"), dashboard.dashboard_data_path),
            portfolio_data_root=_path(options.get("portfolio_data_root"), Path("~/.dojo/data")),
            memory_generated_skill_dir=_path(options.get("memory_generated_skill_dir"), Path(root.memory.generated_skill_dir)),
            preload_offline_data=_bool(options, "preload_offline_data", True),
            preload_registry=_bool(options, "preload_registry", True),
            refresh_enabled=_bool(options, "refresh_enabled", host == "dashboard"),
            refresh_poll_seconds=int(options.get("refresh_poll_seconds", 3600)),
        )


__all__ = ["FinancialHarnessConfig", "FinancialSDKConfig", "FinancialTasksConfig"]
