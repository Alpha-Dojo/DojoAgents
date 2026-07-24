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
    memory_generated_skill_dir: Path
    backend: str = "sdk"
    dashboard_base_url: str | None = None
    dashboard_auth_token: str | None = None

    @classmethod
    def from_context(cls, context: HarnessBuildContext) -> "FinancialHarnessConfig":
        """Read only Agent-runtime financial settings."""

        root = context.config
        options = dict(context.harness_config)
        sdk = root.dojosdk
        tasks = root.tasks

        sdk_config = FinancialSDKConfig(
            api_key=options.get("api_key", sdk.api_key),
            base_url=options.get("base_url", sdk.base_url),
            timeout=float(options.get("timeout", sdk.timeout)),
            max_retries=int(options.get("max_retries", sdk.max_retries)),
            cache_dir=_path(
                options.get("sdk_cache_dir"),
                Path("~/.cache/huggingface/hub"),
            ),
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
            memory_generated_skill_dir=_path(options.get("memory_generated_skill_dir"), Path(root.memory.generated_skill_dir)),
            backend=str(options.get("backend", "sdk")).strip().lower(),
            dashboard_base_url=(str(options["dashboard_base_url"]).strip() if options.get("dashboard_base_url") else None),
            dashboard_auth_token=(str(options["dashboard_auth_token"]).strip() if options.get("dashboard_auth_token") else None),
        )


__all__ = ["FinancialHarnessConfig", "FinancialSDKConfig", "FinancialTasksConfig"]
