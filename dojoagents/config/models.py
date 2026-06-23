from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_LOG_FORMAT = "%(asctime)s %(process)d %(thread)d %(levelname)s %(name)s " "%(filename)s:%(lineno)d - %(message)s"
DEFAULT_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class LLMProviderConfig:
    model: str = "gpt-4.1"
    base_url: str | None = None
    api_key_env: str | None = "OPENAI_API_KEY"
    api_key: str | None = None


@dataclass(frozen=True)
class LLMConfig:
    default: str = "openai"
    providers: dict[str, LLMProviderConfig] = field(default_factory=lambda: {"openai": LLMProviderConfig()})


@dataclass(frozen=True)
class AgentConfig:
    model: str = "gpt-4.1"
    max_iterations: int = 100
    max_tool_workers: int = 4
    lazy_skills: bool = True
    enable_skill_cache: bool = True
    enable_guardrails: bool = True
    enable_think_scrubbing: bool = True
    enable_context_compression: bool = True
    session_max_tokens: int = 100000
    threshold_ratio: float = 0.9
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
class SkillsConfig:
    dir: str = "~/.dojo/skills"
    generated_skill_dir: str = "~/.dojo/skills/generated"
    external_dirs: list[str] = field(default_factory=list)
    disabled: list[str] = field(default_factory=list)
    platform_disabled: dict[str, list[str]] = field(default_factory=dict)
    read_claude_skills: bool = False


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
class ProfilerConfig:
    enabled: bool = False


@dataclass(frozen=True)
class FinancialDashboardConfig:
    enabled: bool = True
    sdk_cache_dir: str = "~/.cache/dojo"
    dashboard_data_root: str = "~/.dojo/dashboard-data"
    stock_quote_refresh_seconds: int = 15
    constituent_kline_post_close_poll_seconds: int = 300
    constituent_kline_max_concurrent: int = 8
    ticker_market_cap_min_sh: float = 1_000_000_000.0
    ticker_market_cap_min_us: float = 1_000_000_000.0
    ticker_market_cap_min_hk: float = 1_000_000_000.0
    derived_cache_schema_version: int = 1
    market_calendar_provider: str = "exchange_calendars"

    @property
    def sdk_cache_path(self) -> Path:
        return Path(self.sdk_cache_dir).expanduser()

    @property
    def dashboard_data_path(self) -> Path:
        return Path(self.dashboard_data_root).expanduser()


@dataclass(frozen=True)
class DashboardConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    profiler: ProfilerConfig = field(default_factory=ProfilerConfig)
    financial: FinancialDashboardConfig = field(default_factory=FinancialDashboardConfig)


@dataclass(frozen=True)
class DojoExtensionsConfig:
    enabled: list[str] = field(default_factory=lambda: ["dojo_research"])


@dataclass(frozen=True)
class LoggingConfig:
    level: str = "INFO"
    format: str = DEFAULT_LOG_FORMAT
    date_format: str = DEFAULT_LOG_DATE_FORMAT


@dataclass(frozen=True)
class DojoSDKConfig:
    api_key: str | None = None
    base_url: str | None = None
    timeout: float = 60.0
    max_retries: int = 1


@dataclass(frozen=True)
class MultiAgentConfig:
    enabled: bool = False
    max_workers: int = 3
    default_agents: list[dict[str, Any]] = field(
        default_factory=lambda: [
            {"role": "analyst", "name": "analyst"},
            {"role": "implementer", "name": "implementer"},
            {"role": "reviewer", "name": "reviewer"},
        ]
    )


@dataclass(frozen=True)
class PlanConfig:
    enabled: bool = False
    auto_plan_threshold: int = 100
    plan_store_path: str = "~/.dojo/agents/plans"
    max_plan_steps: int = 10


@dataclass(frozen=True)
class AgentsConfig:
    version: int = 1
    llm_provider: LLMConfig = field(default_factory=LLMConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    tools: ToolsConfig = field(default_factory=ToolsConfig)
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    skills: SkillsConfig = field(default_factory=SkillsConfig)
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)
    gateway: GatewayConfig = field(default_factory=GatewayConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    dojo_extensions: DojoExtensionsConfig = field(default_factory=DojoExtensionsConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    mcp_servers: dict[str, Any] = field(default_factory=dict)
    dojosdk: DojoSDKConfig = field(default_factory=DojoSDKConfig)
    multi_agent: MultiAgentConfig = field(default_factory=MultiAgentConfig)
    planning: PlanConfig = field(default_factory=PlanConfig)
