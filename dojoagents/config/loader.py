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
    DEFAULT_LOG_DATE_FORMAT,
    DEFAULT_LOG_FORMAT,
    DashboardConfig,
    FinancialDashboardConfig,
    DojoExtensionsConfig,
    GatewayConfig,
    HarnessConfig,
    LLMConfig,
    LLMProviderConfig,
    LoggingConfig,
    MemoryConfig,
    MultiAgentConfig,
    PlanConfig,
    SkillsConfig,
    SandboxConfig,
    SchedulerConfig,
    ToolsConfig,
    WebToolsConfig,
    DojoSDKConfig,
    ProfilerConfig,
    SessionRuntimeConfig,
    SessionsConfig,
    StoreProviderConfig,
    TasksConfig,
)

_ENV_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")
_DEFAULT_PROVIDER_AUTHORS: dict[str, str] = {
    "openai": "openai",
    "anthropic": "anthropic",
    "gemini": "google",
    "deepseek": "deepseek",
    "qwen": "qwen",
    "zhipu": "z-ai",
    "glm": "z-ai",
    "moonshot": "moonshotai",
    "kimi": "moonshotai",
    "ollama": "ollama",
    "minimax": "minimax",
    "openrouter": "",
}


def load_yaml_mapping(path: str | Path) -> dict[str, Any]:
    """Load a YAML mapping through the repository's shared config boundary."""

    config_path = Path(path).expanduser()
    with config_path.open("r", encoding="utf-8") as handle:
        value = yaml.safe_load(handle) or {}
    if not isinstance(value, dict):
        raise ValueError(f"configuration must be a mapping: {config_path}")
    return _expand_env(value)


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


def _as_non_empty_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    trimmed = value.strip()
    return trimmed or None


def _split_author_and_model(model: str | None) -> tuple[str | None, str | None]:
    if not isinstance(model, str):
        return None, None
    trimmed = model.strip()
    if not trimmed:
        return None, None
    if "/" not in trimmed:
        return None, trimmed
    author, slug = trimmed.split("/", 1)
    author = author.strip()
    slug = slug.strip()
    if not author or not slug:
        return None, trimmed
    return author, slug


def _provider_config(name: str, raw: dict[str, Any]) -> LLMProviderConfig:
    api_key_env = raw.get("api_key_env")
    api_key = raw.get("api_key")
    if not api_key and api_key_env:
        api_key = os.getenv(str(api_key_env))
    context_window = raw.get("context_window")
    raw_model = _as_non_empty_string(raw.get("model"))
    parsed_author, parsed_model = _split_author_and_model(raw_model)
    author = _as_non_empty_string(raw.get("author")) or parsed_author or _DEFAULT_PROVIDER_AUTHORS.get(name, "")
    return LLMProviderConfig(
        model=parsed_model,
        author=author or None,
        base_url=raw.get("base_url"),
        api_key_env=api_key_env,
        api_key=api_key,
        context_window=int(context_window) if context_window is not None else None,
    )


def resolve_provider_config(llm: LLMConfig, requested_name: str | None = None) -> tuple[str | None, LLMProviderConfig | None]:
    if not llm.providers:
        return None, None
    if requested_name and requested_name in llm.providers:
        return requested_name, llm.providers[requested_name]
    name = llm.default if isinstance(llm.default, str) and llm.default in llm.providers else None
    if name is None:
        name = next(iter(llm.providers))
    return name, llm.providers[name]


def _reject_unknown_keys(raw: dict[str, Any], allowed: set[str], section: str) -> None:
    unknown = sorted(set(raw) - allowed)
    if unknown:
        raise ValueError(f"{section} contains unknown keys: {', '.join(unknown)}")


def _resolve_path(value: str, base_dir: Path | None) -> str:
    path = Path(value).expanduser()
    if path.is_absolute():
        return str(path.resolve())
    if base_dir is None:
        return str(path)
    return str((base_dir / path).resolve())


def _store_provider_config(raw: dict[str, Any], *, section: str) -> StoreProviderConfig:
    _reject_unknown_keys(raw, {"provider", "factory", "options"}, section)
    provider = str(raw.get("provider", "file"))
    factory = raw.get("factory")
    if factory is not None:
        factory = str(factory)
    options = raw.get("options", {})
    if not isinstance(options, dict):
        raise ValueError(f"{section}.options must be a mapping")
    if provider != "file" and not factory:
        raise ValueError(f"{section}.factory is required for provider {provider!r}")
    return StoreProviderConfig(provider=provider, factory=factory, options=dict(options))


def _to_config(raw: dict[str, Any], *, base_dir: Path | None = None, source_raw: dict[str, Any] | None = None) -> AgentsConfig:
    providers = {name: _provider_config(name, value or {}) for name, value in raw.get("llm_provider", {}).get("providers", {}).items()}
    llm = LLMConfig(
        default=raw.get("llm_provider", {}).get("default"),
        providers=providers,
    )
    _, default_provider = resolve_provider_config(llm)
    agent_raw = raw.get("agent", {})
    compression_ratio = agent_raw.get("compression_threshold_ratio", agent_raw.get("threshold_ratio", 0.8))
    cap_raw = agent_raw.get("session_max_tokens_cap")
    if "model" in agent_raw:
        agent_model = agent_raw.get("model")
        if not isinstance(agent_model, str) or not agent_model.strip():
            agent_model = None
    elif default_provider is not None and default_provider.model:
        agent_model = default_provider.model
    else:
        agent_model = None
    agent = AgentConfig(
        model=agent_model,
        max_iterations=int(agent_raw.get("max_iterations", 100)),
        max_tool_workers=int(agent_raw.get("max_tool_workers", 4)),
        lazy_skills=bool(agent_raw.get("lazy_skills", True)),
        enable_skill_cache=bool(agent_raw.get("enable_skill_cache", True)),
        enable_guardrails=bool(agent_raw.get("enable_guardrails", True)),
        enable_think_scrubbing=bool(agent_raw.get("enable_think_scrubbing", True)),
        enable_context_compression=bool(agent_raw.get("enable_context_compression", True)),
        compression_threshold_ratio=float(compression_ratio),
        session_max_tokens_cap=int(cap_raw) if cap_raw is not None else None,
        default_context_window=int(agent_raw.get("default_context_window", 32768)),
        session_max_tokens=int(agent_raw.get("session_max_tokens", 100000)),
        threshold_ratio=float(compression_ratio),
        default_skills=list(agent_raw.get("default_skills", ["dojo-quant-analyst"])),
    )
    sandbox_raw = raw.get("tools", {}).get("sandbox", {})
    web_raw = raw.get("tools", {}).get("web", {})
    tools = ToolsConfig(
        sandbox=SandboxConfig(
            allowed_roots=list(sandbox_raw.get("allowed_roots", ["${PWD}", "/tmp"])),
            allow_network=bool(sandbox_raw.get("allow_network", False)),
            allowed_commands=list(sandbox_raw.get("allowed_commands", [])),
            timeout_seconds=float(sandbox_raw.get("timeout_seconds", 120)),
        ),
        web=WebToolsConfig(
            search_backend=web_raw.get("search_backend") or "ddgs",
            extract_backend=web_raw.get("extract_backend") or "fetch",
            user_agent=web_raw.get("user_agent"),
            search_base_url=web_raw.get("search_base_url"),
            extract_base_url=web_raw.get("extract_base_url"),
            max_extract_urls=int(web_raw.get("max_extract_urls", 5)),
            max_content_bytes=int(web_raw.get("max_content_bytes", 2_000_000)),
            summary_threshold_chars=int(web_raw.get("summary_threshold_chars", 6000)),
            max_summary_chars=int(web_raw.get("max_summary_chars", 2500)),
            debug=bool(web_raw.get("debug", False)),
        ),
    )
    memory_raw = raw.get("memory", {})
    skills_raw = raw.get("skills", {})
    scheduler_raw = raw.get("scheduler", {})
    gateway_raw = raw.get("gateway", {})
    dashboard_raw = raw.get("dashboard", {})
    financial_raw = dashboard_raw.get("financial", {})
    extensions_raw = raw.get("dojo_extensions", {})
    logging_raw = raw.get("logging", {})
    multi_agent_raw = raw.get("multi_agent", {})
    planning_raw = raw.get("planning", {})
    harness_raw = raw.get("harness", {})
    sessions_raw = raw.get("sessions", {})
    tasks_raw = raw.get("tasks", {})

    if not isinstance(harness_raw, dict):
        raise ValueError("harness must be a mapping")
    _reject_unknown_keys(
        harness_raw,
        {"id", "factory", "manifest", "config", "extra_skill_dirs", "extra_tool_dirs"},
        "harness",
    )
    harness_factory = harness_raw.get("factory", HarnessConfig().factory)
    harness_manifest = harness_raw.get("manifest")
    if (harness_factory is None) == (harness_manifest is None):
        raise ValueError("harness must configure exactly one of factory or manifest")
    harness_config_raw = harness_raw.get("config", {})
    if not isinstance(harness_config_raw, dict):
        raise ValueError("harness.config must be a mapping")
    harness = HarnessConfig(
        id=str(harness_raw.get("id", "financial")),
        factory=str(harness_factory) if harness_factory is not None else None,
        manifest=_resolve_path(str(harness_manifest), base_dir) if harness_manifest is not None else None,
        config=dict(harness_config_raw),
        extra_skill_dirs=[_resolve_path(str(path), base_dir) for path in harness_raw.get("extra_skill_dirs", [])],
        extra_tool_dirs=[_resolve_path(str(path), base_dir) for path in harness_raw.get("extra_tool_dirs", [])],
    )

    if not isinstance(sessions_raw, dict):
        raise ValueError("sessions must be a mapping")
    _reject_unknown_keys(
        sessions_raw,
        {
            "enabled",
            "store",
            "blob_store",
            "runtime",
            "provider",
            "root",
            "agent_id",
            "persist_openai_history",
            "sync_memory",
            "export_default_dir",
        },
        "sessions",
    )
    root = str(sessions_raw.get("root", "~/.dojo/agents/strands_sessions"))
    legacy_provider = str(sessions_raw.get("provider", "dojo_repository"))
    nested_store_raw = sessions_raw.get("store")
    if nested_store_raw is None:
        store_config = StoreProviderConfig(
            provider="file",
            options={"root": root, "compatibility_mode": legacy_provider},
        )
    else:
        if not isinstance(nested_store_raw, dict):
            raise ValueError("sessions.store must be a mapping")
        store_config = _store_provider_config(nested_store_raw, section="sessions.store")
        if store_config.provider == "file" and not store_config.options:
            store_config = StoreProviderConfig(
                provider="file",
                factory=store_config.factory,
                options={"root": root, "compatibility_mode": legacy_provider},
            )
    nested_blob_raw = sessions_raw.get("blob_store")
    if nested_blob_raw is None:
        blob_config = StoreProviderConfig(provider="file", options={"root": root})
    else:
        if not isinstance(nested_blob_raw, dict):
            raise ValueError("sessions.blob_store must be a mapping")
        blob_config = _store_provider_config(nested_blob_raw, section="sessions.blob_store")
        if blob_config.provider == "file" and not blob_config.options:
            blob_config = StoreProviderConfig(provider="file", factory=blob_config.factory, options={"root": root})
    runtime_raw = sessions_raw.get("runtime", {})
    if not isinstance(runtime_raw, dict):
        raise ValueError("sessions.runtime must be a mapping")
    _reject_unknown_keys(
        runtime_raw,
        {"require_user_id", "lease_seconds", "heartbeat_seconds", "event_batch_size"},
        "sessions.runtime",
    )
    session_runtime = SessionRuntimeConfig(
        require_user_id=bool(runtime_raw.get("require_user_id", True)),
        lease_seconds=int(runtime_raw.get("lease_seconds", 90)),
        heartbeat_seconds=int(runtime_raw.get("heartbeat_seconds", 30)),
        event_batch_size=int(runtime_raw.get("event_batch_size", 20)),
    )
    explicit_sessions = (source_raw or raw).get("sessions", {})
    if isinstance(explicit_sessions, dict) and ({"provider", "root"} & set(explicit_sessions)):
        from dojoagents.logging import LOGGER

        LOGGER.warning(
            "Deprecated flat session configuration converted to file store",
            extra={"event": "sessions.config.deprecated", "provider": legacy_provider},
        )
    return AgentsConfig(
        version=int(raw.get("version", 1)),
        llm_provider=llm,
        agent=agent,
        tools=tools,
        memory=MemoryConfig(
            provider=memory_raw.get("provider", "skill_summary"),
            generated_skill_dir=memory_raw.get("generated_skill_dir", "~/.dojo/skills/generated"),
        ),
        skills=SkillsConfig(
            dir=skills_raw.get("dir", "~/.dojo/skills"),
            generated_skill_dir=skills_raw.get("generated_skill_dir", "~/.dojo/skills/generated"),
            external_dirs=list(skills_raw.get("external_dirs", [])),
            disabled=list(skills_raw.get("disabled", [])),
            platform_disabled=dict(skills_raw.get("platform_disabled", {})),
            read_claude_skills=bool(skills_raw.get("read_claude_skills", False)),
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
            profiler=ProfilerConfig(enabled=bool(dashboard_raw.get("profiler", {}).get("enabled", False))),
            financial=FinancialDashboardConfig(
                enabled=bool(financial_raw.get("enabled", True)),
                sdk_cache_dir=str(financial_raw.get("sdk_cache_dir", "~/.cache/huggingface/hub")),
                dashboard_data_root=str(financial_raw.get("dashboard_data_root", "~/.dojo/dashboard-data")),
                stock_quote_refresh_seconds=int(financial_raw.get("stock_quote_refresh_seconds", 15)),
                constituent_kline_post_close_poll_seconds=int(financial_raw.get("constituent_kline_post_close_poll_seconds", 300)),
                constituent_kline_max_concurrent=int(financial_raw.get("constituent_kline_max_concurrent", 8)),
                ticker_market_cap_min_sh=float(financial_raw.get("ticker_market_cap_min_sh", 1_000_000_000.0)),
                ticker_market_cap_min_us=float(financial_raw.get("ticker_market_cap_min_us", 1_000_000_000.0)),
                ticker_market_cap_min_hk=float(financial_raw.get("ticker_market_cap_min_hk", 1_000_000_000.0)),
                derived_cache_schema_version=int(financial_raw.get("derived_cache_schema_version", 1)),
                market_calendar_provider=str(financial_raw.get("market_calendar_provider", "exchange_calendars")),
            ),
        ),
        dojo_extensions=DojoExtensionsConfig(enabled=list(extensions_raw.get("enabled", ["dojo_research"]))),
        logging=LoggingConfig(
            level=str(logging_raw.get("level", "INFO")),
            format=str(logging_raw.get("format", DEFAULT_LOG_FORMAT)),
            date_format=str(logging_raw.get("date_format", DEFAULT_LOG_DATE_FORMAT)),
        ),
        mcp_servers=dict(raw.get("mcp_servers", {})),
        dojosdk=DojoSDKConfig(
            api_key=raw.get("dojosdk", {}).get("api_key"),
            base_url=raw.get("dojosdk", {}).get("base_url"),
            timeout=float(raw.get("dojosdk", {}).get("timeout", 60.0)),
            max_retries=int(raw.get("dojosdk", {}).get("max_retries", 1)),
        ),
        multi_agent=MultiAgentConfig(
            enabled=bool(multi_agent_raw.get("enabled", False)),
            max_workers=int(multi_agent_raw.get("max_workers", 3)),
            default_agents=list(multi_agent_raw.get("default_agents", MultiAgentConfig().default_agents)),
        ),
        planning=PlanConfig(
            enabled=bool(planning_raw.get("enabled", False)),
            auto_plan_threshold=int(planning_raw.get("auto_plan_threshold", 100)),
            plan_store_path=str(planning_raw.get("plan_store_path", "~/.dojo/agents/plans")),
            max_plan_steps=int(planning_raw.get("max_plan_steps", 10)),
        ),
        harness=harness,
        sessions=SessionsConfig(
            enabled=bool(sessions_raw.get("enabled", True)),
            store=store_config,
            blob_store=blob_config,
            runtime=session_runtime,
            provider=str(sessions_raw.get("provider", "dojo_repository")),
            root=str(sessions_raw.get("root", "~/.dojo/agents/strands_sessions")),
            agent_id=str(sessions_raw.get("agent_id", "dojo-agent")),
            persist_openai_history=bool(sessions_raw.get("persist_openai_history", True)),
            sync_memory=bool(sessions_raw.get("sync_memory", True)),
            export_default_dir=str(sessions_raw.get("export_default_dir", "~/Desktop/dojo-chat-export")),
        ),
        tasks=TasksConfig(
            enabled=bool(tasks_raw.get("enabled", True)),
            dirs=list(tasks_raw.get("dirs", ["~/.dojo/tasks"])),
            output_root=str(tasks_raw.get("output_root", "~/.dojo/tasks/outputs")),
            auto_detect=bool(tasks_raw.get("auto_detect", False)),
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
        return _to_config(self._load_raw(), base_dir=self.path.parent.resolve(), source_raw=self.raw())

    def snapshot(self) -> AgentsConfig:
        fingerprint = self._stat_fingerprint()
        if self._snapshot is None or fingerprint != self._fingerprint:
            self._snapshot = self._load_and_validate()
            self._fingerprint = fingerprint
        return self._snapshot

    def redacted(self) -> dict[str, Any]:
        data = asdict(self.snapshot())
        for name, provider in data.get("llm_provider", {}).get("providers", {}).items():
            configured = bool(provider.get("api_key"))
            if not configured and name == "ollama":
                configured = bool(str(provider.get("model") or "").strip())
            provider["api_key_configured"] = configured
            if provider.get("api_key") or provider.get("api_key_env"):
                provider["api_key"] = "***"
        sensitive_fragments = ("dsn", "password", "secret", "access_key", "api_key", "token", "credential", "endpoint")

        def redact_options(value: Any) -> Any:
            if isinstance(value, dict):
                return {key: "***" if any(fragment in key.lower() for fragment in sensitive_fragments) else redact_options(item) for key, item in value.items()}
            if isinstance(value, list):
                return [redact_options(item) for item in value]
            return value

        data["harness"]["config"] = redact_options(data["harness"]["config"])
        data["sessions"]["store"]["options"] = redact_options(data["sessions"]["store"]["options"])
        data["sessions"]["blob_store"]["options"] = redact_options(data["sessions"]["blob_store"]["options"])
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
