"""Canonical DojoSDK client construction from DojoAgents configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dojo.client.async_client import AsyncDojo
from dojo.client.sync import Dojo
from dojo.datasource.config import HFConfig

from dojoagents.config.models import AgentsConfig, DojoSDKConfig


def dojo_client_kwargs(
    *,
    api_key: str | None,
    base_url: str | None,
    timeout: float,
    max_retries: int,
    offline_enabled: bool,
    cache_dir: str | Path,
    backend: str,
    local_files_only: bool,
    online: bool | None = None,
) -> dict[str, Any]:
    """Build explicit SDK arguments without mutating process environment."""
    offline_config = HFConfig.from_env()
    offline_config.cache_dir = str(Path(cache_dir).expanduser().resolve())
    offline_config.backend = backend
    offline_config.local_only = local_files_only
    return {
        "api_key": api_key,
        "base_url": base_url,
        "timeout": timeout,
        "max_retries": max_retries,
        "online": (not offline_enabled) if online is None else online,
        "offline_config": offline_config,
    }


def _sdk_config(config: AgentsConfig | DojoSDKConfig) -> DojoSDKConfig:
    return config.dojosdk if isinstance(config, AgentsConfig) else config


def dojo_client_kwargs_from_config(
    config: AgentsConfig | DojoSDKConfig,
    *,
    online: bool | None = None,
) -> dict[str, Any]:
    sdk = _sdk_config(config)
    offline = sdk.offline
    return dojo_client_kwargs(
        api_key=sdk.api_key,
        base_url=sdk.base_url,
        timeout=sdk.timeout,
        max_retries=sdk.max_retries,
        offline_enabled=offline.enabled,
        cache_dir=offline.cache_dir,
        backend=offline.backend,
        local_files_only=offline.local_files_only,
        online=online,
    )


def create_async_dojo(
    config: AgentsConfig | DojoSDKConfig,
    *,
    online: bool | None = None,
) -> AsyncDojo:
    return AsyncDojo(**dojo_client_kwargs_from_config(config, online=online))


def create_async_dojo_from_settings(**settings: Any) -> AsyncDojo:
    return AsyncDojo(**dojo_client_kwargs(**settings))


def create_dojo(
    config: AgentsConfig | DojoSDKConfig,
    *,
    online: bool | None = None,
) -> Dojo:
    return Dojo(**dojo_client_kwargs_from_config(config, online=online))


async def close_async_dojo(client: Any) -> None:
    close = getattr(client, "aclose", None)
    if callable(close):
        await close()
        return
    close = getattr(getattr(client, "_client", None), "aclose", None)
    if callable(close):
        await close()


__all__ = [
    "close_async_dojo",
    "create_async_dojo",
    "create_async_dojo_from_settings",
    "create_dojo",
    "dojo_client_kwargs",
    "dojo_client_kwargs_from_config",
]
