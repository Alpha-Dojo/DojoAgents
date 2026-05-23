from __future__ import annotations

import copy
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

import yaml

from dojoagents.config.models import (
    AgentConfig,
    AgentsConfig,
    DashboardConfig,
    DojoExtensionsConfig,
    GatewayConfig,
    LLMConfig,
    LLMProviderConfig,
    MemoryConfig,
    SandboxConfig,
    SchedulerConfig,
    ToolsConfig,
)

_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _expand_env(value: Any) -> Any:
    if isinstance(value, str):
        return _ENV_RE.sub(lambda match: os.getenv(match.group(1), ""), value)
    if isinstance(value, list):
        return [_expand_env(item) for item in value]
    if isinstance(value, dict):
        return {key: _expand_env(item) for key, item in value.items()}
    return value


def _provider_config(raw: dict[str, Any]) -> LLMProviderConfig:
    api_key_env = raw.get("api_key_env")
    api_key = raw.get("api_key")
    if not api_key and api_key_env:
        api_key = os.getenv(str(api_key_env))
    return LLMProviderConfig(
        model=raw.get("model", "gpt-4.1"),
        base_url=raw.get("base_url"),
        api_key_env=api_key_env,
        api_key=api_key,
    )


def _to_config(raw: dict[str, Any]) -> AgentsConfig:
    providers = {
        name: _provider_config(value or {})
        for name, value in raw.get("llm_provider", {}).get("providers", {}).items()
    }
    if not providers:
        providers = {"openai": LLMProviderConfig(api_key=os.getenv("OPENAI_API_KEY"))}
    llm = LLMConfig(
        default=raw.get("llm_provider", {}).get("default", "openai"),
        providers=providers,
    )
    default_provider = llm.providers.get(llm.default) or next(iter(llm.providers.values()))
    agent_raw = raw.get("agent", {})
    agent = AgentConfig(
        model=agent_raw.get("model", default_provider.model),
        max_iterations=int(agent_raw.get("max_iterations", 8)),
        max_tool_workers=int(agent_raw.get("max_tool_workers", 4)),
        default_skills=list(agent_raw.get("default_skills", ["dojo-quant-analyst"])),
    )
    sandbox_raw = raw.get("tools", {}).get("sandbox", {})
    tools = ToolsConfig(
        sandbox=SandboxConfig(
            allowed_roots=list(sandbox_raw.get("allowed_roots", ["${PWD}", "/tmp"])),
            allow_network=bool(sandbox_raw.get("allow_network", False)),
            allowed_commands=list(sandbox_raw.get("allowed_commands", [])),
            timeout_seconds=float(sandbox_raw.get("timeout_seconds", 120)),
        )
    )
    memory_raw = raw.get("memory", {})
    scheduler_raw = raw.get("scheduler", {})
    gateway_raw = raw.get("gateway", {})
    dashboard_raw = raw.get("dashboard", {})
    extensions_raw = raw.get("dojo_extensions", {})
    return AgentsConfig(
        version=int(raw.get("version", 1)),
        llm_provider=llm,
        agent=agent,
        tools=tools,
        memory=MemoryConfig(
            provider=memory_raw.get("provider", "skill_summary"),
            generated_skill_dir=memory_raw.get(
                "generated_skill_dir", "~/.dojo/skills/generated"
            ),
        ),
        scheduler=SchedulerConfig(
            enabled=bool(scheduler_raw.get("enabled", True)),
            timezone=scheduler_raw.get("timezone", "Asia/Shanghai"),
            store=scheduler_raw.get("store", "~/.dojo/agents/jobs.yaml"),
        ),
        gateway=GatewayConfig(
            enabled=bool(gateway_raw.get("enabled", True)),
            hooks=dict(gateway_raw.get("hooks", {})),
        ),
        dashboard=DashboardConfig(
            host=dashboard_raw.get("host", "127.0.0.1"),
            port=int(dashboard_raw.get("port", 8765)),
        ),
        dojo_extensions=DojoExtensionsConfig(
            enabled=list(
                extensions_raw.get("enabled", ["dojo_market_data", "dojo_research"])
            )
        ),
    )


class ConfigStore:
    def __init__(self, path: str | Path = "~/.dojo/agents.yaml") -> None:
        self.path = Path(path).expanduser()
        self._snapshot: AgentsConfig | None = None
        self._fingerprint: tuple[int, int] | None = None

    def _stat_fingerprint(self) -> tuple[int, int]:
        try:
            stat = self.path.stat()
            return (stat.st_mtime_ns, stat.st_size)
        except FileNotFoundError:
            return (0, 0)

    def _load_raw(self) -> dict[str, Any]:
        defaults = asdict(AgentsConfig())
        # Agent model defaults to the selected provider model unless explicitly
        # configured. Keeping it in the deep-merge defaults would mask provider
        # model changes from ~/.dojo/agents.yaml.
        defaults.get("agent", {}).pop("model", None)
        if not self.path.exists():
            return _expand_env(defaults)
        loaded = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"{self.path} must contain a YAML mapping")
        return _expand_env(_deep_merge(defaults, loaded))

    def _load_and_validate(self) -> AgentsConfig:
        return _to_config(self._load_raw())

    def snapshot(self) -> AgentsConfig:
        fingerprint = self._stat_fingerprint()
        if self._snapshot is None or fingerprint != self._fingerprint:
            self._snapshot = self._load_and_validate()
            self._fingerprint = fingerprint
        return copy.deepcopy(self._snapshot)

    def redacted(self) -> dict[str, Any]:
        data = asdict(self.snapshot())
        for provider in data.get("llm_provider", {}).get("providers", {}).values():
            if provider.get("api_key") or provider.get("api_key_env"):
                provider["api_key"] = "***"
        return data

    def raw(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        loaded = yaml.safe_load(self.path.read_text(encoding="utf-8")) or {}
        if not isinstance(loaded, dict):
            raise ValueError(f"{self.path} must contain a YAML mapping")
        return loaded

    def save_raw(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=False),
            encoding="utf-8",
        )
        self._snapshot = None
        self._fingerprint = None
