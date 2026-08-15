"""Dashboard-owned financial application service lifecycle."""

from __future__ import annotations

import asyncio
import datetime
import inspect
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from dojo.client.async_client import AsyncDojo
from dojo.datasource.config import is_online

from dojoagents.dashboard.services.constituent_kline_refresh_state import RefreshStateStore
from dojoagents.dashboard.services.financial_registry import FinancialDomainRegistry
from dojoagents.dashboard.services.market_refresh_jobs import start_refresh_loop
from dojoagents.config.models import AgentsConfig
from dojoagents.logging import LOGGER


@dataclass(frozen=True)
class DashboardServiceHealth:
    healthy: bool
    ready: bool
    client_ready: bool
    registry_ready: bool
    refresh_running: bool
    detail: str = ""


@dataclass(frozen=True)
class DashboardAppServicesConfig:
    api_key: str | None
    base_url: str | None
    timeout: float
    max_retries: int
    sdk_cache_dir: Path
    data_root: Path
    portfolio_data_root: Path
    constituent_kline_max_concurrent: int = 50
    offline_mode: bool = True
    preload_offline_data: bool = True
    preload_registry: bool = True
    refresh_enabled: bool = True
    refresh_poll_seconds: int = 3600

    @classmethod
    def from_agents_config(cls, config: AgentsConfig) -> "DashboardAppServicesConfig":
        financial = config.dashboard.financial
        sdk = config.dojosdk
        online = is_online()
        return cls(
            api_key=sdk.api_key,
            base_url=sdk.base_url,
            timeout=sdk.timeout,
            max_retries=sdk.max_retries,
            sdk_cache_dir=financial.sdk_cache_path.resolve(),
            data_root=financial.dashboard_data_path.resolve(),
            portfolio_data_root=Path("~/.dojo/data").expanduser().resolve(),
            constituent_kline_max_concurrent=financial.constituent_kline_max_concurrent,
            offline_mode=not online,
            preload_offline_data=not online,
            refresh_enabled=not online,
        )


class DashboardAppServices:
    """Own AsyncDojo, Dashboard financial stores, and refresh jobs."""

    def __init__(
        self,
        config: DashboardAppServicesConfig,
        *,
        client_factory: Callable[..., Any] = AsyncDojo,
        registry_factory: Callable[[], Any] = FinancialDomainRegistry,
        refresh_loop: Callable[..., Any] = start_refresh_loop,
    ) -> None:
        self.config = config
        self._client_factory = client_factory
        self._registry_factory = registry_factory
        self._refresh_loop = refresh_loop
        self.client: Any | None = None
        self.registry: Any | None = None
        self.gateway: Any | None = None
        self.portfolio_store: Any | None = None
        self.portfolio_service: Any | None = None
        self.refresh_store = RefreshStateStore(config.data_root / "runtime")
        self.refresh_task: asyncio.Task[Any] | None = None
        self.market_data_revision: dict[str, Any] = {}
        self._ready = False
        self._stopped = False
        self._previous_environment: dict[str, str | None] | None = None
        self._startup_task: asyncio.Task[Any] | None = None
        self._startup_loop: asyncio.AbstractEventLoop | None = None

    def replace_factories_for_testing(
        self,
        *,
        client_factory: Callable[..., Any],
        registry_factory: Callable[[], Any],
        refresh_loop: Callable[..., Any] | None = None,
    ) -> None:
        """Inject fakes before startup without introducing global registries."""

        if self.client is not None or self.registry is not None:
            raise RuntimeError("financial service factories cannot change after startup")
        self._client_factory = client_factory
        self._registry_factory = registry_factory
        if refresh_loop is not None:
            self._refresh_loop = refresh_loop

    async def startup(self) -> None:
        if self._ready:
            return
        self._startup_task = asyncio.current_task()
        self._startup_loop = asyncio.get_running_loop()
        self._stopped = False
        try:
            LOGGER.info(
                "Starting Dashboard financial services: data_mode=%s preload_offline_data=%s refresh_enabled=%s",
                "offline" if self.config.offline_mode else "online",
                self.config.preload_offline_data,
                self.config.refresh_enabled,
            )
            self._previous_environment = {
                "DOJO_CACHE_DIR": os.environ.get("DOJO_CACHE_DIR"),
                "DOJO_ONLINE": os.environ.get("DOJO_ONLINE"),
            }
            os.environ["DOJO_CACHE_DIR"] = str(self.config.sdk_cache_dir)
            os.environ["DOJO_ONLINE"] = "0" if self.config.offline_mode else "1"
            self.client = self._client_factory(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                max_retries=self.config.max_retries,
            )
            self.registry = self._registry_factory()

            if self.config.preload_offline_data and hasattr(self.client, "preload_offline_data"):
                preload = self.client.preload_offline_data
                if inspect.iscoroutinefunction(preload):
                    await preload()
                else:
                    await asyncio.to_thread(preload)
            await self.registry.init_and_load_all(
                self.client,
                data_root=self.config.data_root,
                preload=self.config.preload_registry,
                portfolio_data_root=self.config.portfolio_data_root,
                kline_max_concurrent=self.config.constituent_kline_max_concurrent,
            )
            self.gateway = getattr(self.registry, "gateway", None)
            self.portfolio_store = getattr(self.registry, "portfolio_store", None)
            self.portfolio_service = getattr(self.registry, "portfolio_service", None)
            if self.config.preload_offline_data:
                await self.refresh_store.set_last_refresh_date_async("preload_offline_data", datetime.date.today())
            self.market_data_revision = self.refresh_store.get_market_data_revision()
            if self.config.refresh_enabled:
                self.refresh_task = asyncio.create_task(
                    self._refresh_loop(
                        runtime_dir=self.config.data_root / "runtime",
                        registry=self.registry,
                        poll_interval=self.config.refresh_poll_seconds,
                    ),
                    name="financial-market-refresh",
                )
            self._ready = True
        except BaseException:
            try:
                await self.shutdown()
            except Exception:
                LOGGER.exception("Failed to clean up interrupted Dashboard financial startup")
            raise
        finally:
            self._startup_task = None
            self._startup_loop = None

    def cancel_startup(self) -> None:
        """Cancel startup safely when the CLI receives Ctrl+C."""
        client = self.client
        cancel_preload = getattr(client, "cancel_preload_offline_data", None)
        if callable(cancel_preload):
            cancel_preload()
        task = self._startup_task
        loop = self._startup_loop
        if task is not None and not task.done() and loop is not None:
            loop.call_soon_threadsafe(task.cancel)

    async def health(self) -> DashboardServiceHealth:
        client_ready = self.client is not None
        registry_ready = self.registry is not None and getattr(self.registry, "client", None) is self.client
        refresh_running = self.refresh_task is not None and not self.refresh_task.done()
        healthy = self._ready and client_ready and registry_ready
        return DashboardServiceHealth(
            healthy=healthy,
            ready=self._ready,
            client_ready=client_ready,
            registry_ready=registry_ready,
            refresh_running=refresh_running,
            detail="ready" if healthy else "financial services are not ready",
        )

    async def refresh(self) -> None:
        if not self._ready or self.registry is None:
            raise RuntimeError("financial services are not ready")
        preload = getattr(self.client, "preload_offline_data", None)
        if callable(preload):
            if inspect.iscoroutinefunction(preload):
                await preload()
            else:
                await asyncio.to_thread(preload)
        callback = getattr(self.registry, "refresh_after_offline_data_update", None)
        if callable(callback):
            if inspect.iscoroutinefunction(callback):
                await callback()
            else:
                await asyncio.to_thread(callback)
        await self.refresh_store.set_last_refresh_date_async("preload_offline_data", datetime.date.today())
        self.market_data_revision = self.refresh_store.get_market_data_revision()

    async def shutdown(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._ready = False
        errors: list[str] = []
        if self.refresh_task is not None:
            self.refresh_task.cancel()
            try:
                await self.refresh_task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                errors.append(f"refresh task: {exc}")
            finally:
                self.refresh_task = None

        client = self.client
        if client is not None:
            try:
                close = getattr(client, "aclose", None)
                if callable(close):
                    await close()
                else:
                    http_client = getattr(client, "_client", None)
                    close = getattr(http_client, "aclose", None)
                    if callable(close):
                        await close()
            except Exception as exc:
                errors.append(f"client: {exc}")
        if self.registry is not None:
            reset = getattr(self.registry, "reset", None)
            if callable(reset):
                try:
                    reset()
                except Exception as exc:
                    errors.append(f"registry: {exc}")
        self.client = None
        self.gateway = None
        self.portfolio_store = None
        self.portfolio_service = None
        self.registry = None
        if self._previous_environment is not None:
            for name, previous in self._previous_environment.items():
                if previous is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = previous
            self._previous_environment = None
        if errors:
            raise RuntimeError("financial service shutdown failed: " + "; ".join(errors))


__all__ = [
    "DashboardAppServices",
    "DashboardAppServicesConfig",
    "DashboardServiceHealth",
]
