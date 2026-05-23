from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class LLMProviderConfig:
    model: str = "gpt-4.1"
    base_url: str | None = None
    api_key_env: str | None = "OPENAI_API_KEY"
    api_key: str | None = None


@dataclass(frozen=True)
class LLMConfig:
    default: str = "openai"
    providers: dict[str, LLMProviderConfig] = field(
        default_factory=lambda: {"openai": LLMProviderConfig()}
    )


@dataclass(frozen=True)
class AgentConfig:
    model: str = "gpt-4.1"
    max_iterations: int = 8
    max_tool_workers: int = 4
    default_skills: list[str] = field(default_factory=lambda: ["dojo-quant-analyst"])


@dataclass(frozen=True)
class SandboxConfig:
    allowed_roots: list[str] = field(default_factory=lambda: ["${PWD}", "/tmp"])
    allow_network: bool = False
    allowed_commands: list[str] = field(default_factory=list)
    timeout_seconds: float = 120


@dataclass(frozen=True)
class ToolsConfig:
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)


@dataclass(frozen=True)
class MemoryConfig:
    provider: str = "skill_summary"
    generated_skill_dir: str = "~/.dojo/skills/generated"


@dataclass(frozen=True)
class SchedulerConfig:
    enabled: bool = True
    timezone: str = "Asia/Shanghai"
    store: str = "~/.dojo/agents/jobs.yaml"


@dataclass(frozen=True)
class GatewayConfig:
    enabled: bool = True
    hooks: dict[str, dict[str, Any]] = field(default_factory=dict)


@dataclass(frozen=True)
class DashboardConfig:
    host: str = "127.0.0.1"
    port: int = 8765


@dataclass(frozen=True)
class DojoExtensionsConfig:
    enabled: list[str] = field(
        default_factory=lambda: ["dojo_market_data", "dojo_research"]
    )


@dataclass(frozen=True)
class AgentsConfig:
    version: int = 1
    llm_provider: LLMConfig = field(default_factory=LLMConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    dojo_extensions: DojoExtensionsConfig = field(default_factory=DojoExtensionsConfig)
