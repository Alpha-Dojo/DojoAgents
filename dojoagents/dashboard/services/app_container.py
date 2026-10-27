"""Dashboard-owned financial application service lifecycle."""

from __future__ import annotations

import anyio
import datetime
import inspect
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from dojo.client.async_client import AsyncDojo

from dojoagents.dojo_sdk import dojo_client_kwargs
from dojoagents.dashboard.services.constituent_kline_refresh_state import (
    SNAPSHOT_REFRESH_STATE_KEY,
    RefreshStateStore,
)
from dojoagents.dashboard.services.financial_registry import FinancialDomainRegistry
from dojoagents.dashboard.services.market_refresh_jobs import start_refresh_loop
from dojoagents.config.models import AgentsConfig, DEFAULT_DOJOSDK_STARTUP_PATHS
from dojoagents.logging import LOGGER
from dojoagents.utils.async_runtime import SyncWorkload, run_sync_bounded


HOT_SNAPSHOT_PATHS = (
    "/api/qdata/v1/stocks/current_quote",
    "/api/qdata/v1/analysis/market_dynamics",
    "/api/qdata/v1/sector/precomputed/constituents",
    "/api/qdata/v1/sector/precomputed/sector_daily",
    "/api/qdata/v1/sector/precomputed/ticker_daily",
)


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
    offline_cache_dir: Path
    data_root: Path
    portfolio_data_root: Path
    data_backend: str = "auto"
    local_files_only: bool = False
    startup_paths: tuple[str, ...] = DEFAULT_DOJOSDK_STARTUP_PATHS
    startup_repos: tuple[str, ...] = ()
    constituent_kline_max_concurrent: int = 50
    offline_mode: bool = True
    ensure_offline_snapshots: bool = True
    startup_preload_stores: tuple[str, ...] = (
        "sector_store",
        "benchmark_store",
    )
    refresh_enabled: bool = True
    refresh_poll_seconds: int = 120

    @classmethod
    def from_agents_config(cls, config: AgentsConfig) -> "DashboardAppServicesConfig":
        financial = config.dashboard.financial
        sdk = config.dojosdk
        offline = sdk.offline
        has_snapshot_scope = bool(offline.startup_paths or offline.startup_repos)
        return cls(
            api_key=sdk.api_key,
            base_url=sdk.base_url,
            timeout=sdk.timeout,
            max_retries=sdk.max_retries,
            offline_cache_dir=offline.cache_path.resolve(),
            data_backend=offline.backend,
            local_files_only=offline.local_files_only,
            startup_paths=offline.startup_paths,
            startup_repos=offline.startup_repos,
            data_root=financial.dashboard_data_path.resolve(),
            portfolio_data_root=Path("~/.dojo/data").expanduser().resolve(),
            constituent_kline_max_concurrent=financial.constituent_kline_max_concurrent,
            startup_preload_stores=financial.startup_preload_stores,
            offline_mode=offline.enabled,
            ensure_offline_snapshots=offline.enabled,
            refresh_enabled=offline.enabled and has_snapshot_scope,
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
        self.live_client: Any | None = None
        self.registry: Any | None = None
        self.gateway: Any | None = None
        self.portfolio_store: Any | None = None
        self.portfolio_service: Any | None = None
        self.refresh_store = RefreshStateStore(config.data_root / "runtime")
        self._refresh_running = False
        self.market_data_revision: dict[str, Any] = {}
        self._ready = False
        self._stopped = False
        # A portal bound to the startup loop so a *foreign* thread can ask for
        # cancellation without touching the loop from outside it.
        self._portal: anyio.from_thread.BlockingPortal | None = None
        self._portal_thread_ident: int | None = None
        self._startup_scope: anyio.CancelScope | None = None

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

    async def startup(self, *, task_group: anyio.abc.TaskGroup | None = None) -> None:
        """Start Dashboard financial services, cancellable from a signal thread.

        The portal is owned by this component for exactly the duration of the
        startup call: it is entered here, closed in this same task's ``finally``,
        and never created per request.
        """

        if self._ready:
            return
        portal = anyio.from_thread.BlockingPortal()
        await portal.__aenter__()
        self._portal = portal
        # The portal is created on the startup loop, so this is that loop's thread.
        self._portal_thread_ident = threading.get_ident()
        self._stopped = False
        try:
            with anyio.CancelScope() as scope:
                self._startup_scope = scope
                await self._startup_services(task_group=task_group)
            if scope.cancelled_caught:
                # ``cancel_startup`` fired while startup was in flight.  The cancel
                # scope would otherwise swallow the cancellation, but the Dashboard
                # lifespan shutdown path depends on observing it.
                raise anyio.get_cancelled_exc_class()()
        finally:
            self._startup_scope = None
            self._portal = None
            self._portal_thread_ident = None
            # Exited at the same depth it was entered: AnyIO only allows a cancel
            # scope to be closed while it is the task's current scope, so this must
            # not be wrapped in a shield (``BlockingPortal.__aexit__`` closes a
            # task group).  ``__aexit__`` itself performs no cancellable await when
            # the portal has no child tasks, which is always the case here.
            await portal.__aexit__(None, None, None)

    async def _startup_services(self, *, task_group: anyio.abc.TaskGroup | None = None) -> None:
        LOGGER.info(
            "Starting Dashboard financial services: data_mode=%s ensure_offline_snapshots=%s refresh_enabled=%s",
            "offline" if self.config.offline_mode else "online",
            self.config.ensure_offline_snapshots,
            self.config.refresh_enabled,
        )
        try:
            self.client = self._client_factory(**dojo_client_kwargs(
                api_key=self.config.api_key,
                base_url=self.config.base_url,
                timeout=self.config.timeout,
                max_retries=self.config.max_retries,
                offline_enabled=self.config.offline_mode,
                cache_dir=self.config.offline_cache_dir,
                backend=self.config.data_backend,
                local_files_only=self.config.local_files_only,
            ))
            # Snapshot mode is intentionally limited to historical/bulk data.
            # When credentials are available, keep a separate online client for
            # current quotes, market dynamics, news, and events.
            if self.config.offline_mode and self.config.api_key:
                self.live_client = self._client_factory(**dojo_client_kwargs(
                    api_key=self.config.api_key,
                    base_url=self.config.base_url,
                    timeout=self.config.timeout,
                    max_retries=self.config.max_retries,
                    offline_enabled=False,
                    cache_dir=self.config.offline_cache_dir,
                    backend=self.config.data_backend,
                    local_files_only=False,
                    online=True,
                ))
            elif not self.config.offline_mode:
                self.live_client = self.client
            elif self.config.offline_mode:
                LOGGER.info(
                    "Using the local DojoSDK snapshot feed for quotes, market dynamics, news, and events; "
                    "a Dojo HTTP API key is not required"
                )
            self.registry = self._registry_factory()

            startup_sync_result: Any | None = None
            if self.config.ensure_offline_snapshots and hasattr(self.client, "ensure_offline_snapshots"):
                ensure = self.client.ensure_offline_snapshots
                kwargs = {
                    "paths": list(self.config.startup_paths) or None,
                    "repos": list(self.config.startup_repos) or None,
                }
                if kwargs["paths"] or kwargs["repos"]:
                    if inspect.iscoroutinefunction(ensure):
                        await ensure(**kwargs)
                    else:
                        await run_sync_bounded(ensure, workload=SyncWorkload.SDK_IO, **kwargs)
                # ``ensure`` deliberately reuses an existing active snapshot. A
                # bounded remote revision check is therefore required at startup
                # to preserve the old local-SDK behaviour of seeing newly
                # published HF/ModelScope data after a restart.
                sync = getattr(self.client, "sync_offline_snapshots", None)
                if callable(sync) and not self.config.local_files_only:
                    sync_kwargs = {
                        **kwargs,
                        "check_remote": True,
                        "force": False,
                    }
                    if inspect.iscoroutinefunction(sync):
                        startup_sync_result = await sync(**sync_kwargs)
                    else:
                        startup_sync_result = await run_sync_bounded(
                            sync,
                            workload=SyncWorkload.SDK_IO,
                            **sync_kwargs,
                        )
                    failures = tuple(getattr(startup_sync_result, "failures", ()) or ())
                    if failures:
                        LOGGER.warning(
                            "Startup snapshot revision check had %d failed repositories; "
                            "committed local snapshots remain available",
                            len(failures),
                        )
            init_kwargs = {
                "data_root": self.config.data_root,
                "preload": False,
                "portfolio_data_root": self.config.portfolio_data_root,
                "kline_max_concurrent": self.config.constituent_kline_max_concurrent,
            }
            signature = inspect.signature(self.registry.init_and_load_all)
            if "live_client" in signature.parameters:
                init_kwargs["live_client"] = self.live_client
            await self.registry.init_and_load_all(self.client, **init_kwargs)
            if self.config.startup_preload_stores:
                preload_startup = getattr(self.registry, "preload_startup", None)
                if not callable(preload_startup):
                    raise RuntimeError("financial registry does not support bounded startup preload")
                await preload_startup(self.config.startup_preload_stores)
            self.gateway = getattr(self.registry, "gateway", None)
            self.portfolio_store = getattr(self.registry, "portfolio_store", None)
            self.portfolio_service = getattr(self.registry, "portfolio_service", None)
            self.market_data_revision = self.refresh_store.get_market_data_revision()
            if self.config.refresh_enabled:
                if task_group is None:
                    raise RuntimeError("refresh-enabled Dashboard services require a parent TaskGroup")
                await task_group.start(self._run_refresh_service)
            self._ready = True
        except BaseException:
            # Shielded: this path runs while a cancellation is already pending, and
            # an unshielded await would abort before the clients are released.
            with anyio.CancelScope(shield=True):
                try:
                    await self.shutdown()
                except Exception:
                    LOGGER.exception("Failed to clean up interrupted Dashboard financial startup")
            raise

    def cancel_startup(self) -> None:
        """Cancel startup safely when the CLI receives Ctrl+C.

        Uvicorn's ``add_signal_handler`` callbacks run *on the startup loop's own
        thread*, while a plain OS signal handler runs elsewhere.  Both paths must
        work, so the cancellation is delivered directly when it is already on the
        right loop and through the component's portal when it is not — the portal
        would otherwise refuse to re-enter its own loop.
        """

        scope = self._startup_scope
        if scope is None:
            return
        portal = self._portal
        if portal is not None and threading.get_ident() != self._portal_thread_ident:
            try:
                portal.call(scope.cancel)
                return
            except RuntimeError:
                LOGGER.debug("Dashboard startup cancel signal could not reach the startup portal")
        scope.cancel()

    async def health(self) -> DashboardServiceHealth:
        client_ready = self.client is not None
        registry_ready = self.registry is not None and getattr(self.registry, "client", None) is self.client
        refresh_running = self._refresh_running
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
        sync = getattr(self.client, "sync_offline_snapshots", None)
        if not callable(sync):
            raise RuntimeError("DojoSDK client does not support snapshot synchronization")
        kwargs = {
            "paths": list(self.config.startup_paths) or None,
            "repos": list(self.config.startup_repos) or None,
            "check_remote": True,
            "force": False,
        }
        if not kwargs["paths"] and not kwargs["repos"]:
            raise RuntimeError("snapshot refresh requires explicit startup_paths or startup_repos")
        if inspect.iscoroutinefunction(sync):
            result = await sync(**kwargs)
        else:
            result = await run_sync_bounded(sync, workload=SyncWorkload.SDK_IO, **kwargs)
        failures = tuple(getattr(result, "failures", ()) or ())
        updated_repos = tuple(getattr(result, "updated_repos", ()) or ())
        if bool(getattr(result, "changed", False)) and updated_repos:
            callback = getattr(self.registry, "refresh_after_offline_data_update", None)
            if callable(callback):
                if inspect.iscoroutinefunction(callback):
                    await callback(updated_repos=updated_repos)
                else:
                    await run_sync_bounded(
                        callback,
                        updated_repos=updated_repos,
                        workload=SyncWorkload.SDK_IO,
                    )
        if failures:
            LOGGER.warning(
                "Manual snapshot refresh had %d failed repositories; successful repositories remain committed",
                len(failures),
            )
        else:
            await self.refresh_store.set_last_refresh_date_async(
                SNAPSHOT_REFRESH_STATE_KEY,
                datetime.date.today(),
            )
        self.market_data_revision = self.refresh_store.get_market_data_revision()

    async def shutdown(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._ready = False
        errors: list[str] = []
        clients = [client for client in (self.live_client, self.client) if client is not None]
        unique_clients = list(dict.fromkeys(map(id, clients)))
        clients_by_id = {id(client): client for client in clients}
        for client_id in unique_clients:
            client = clients_by_id[client_id]
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
        self.live_client = None
        self.gateway = None
        self.portfolio_store = None
        self.portfolio_service = None
        self.registry = None
        if errors:
            raise RuntimeError("financial service shutdown failed: " + "; ".join(errors))

    async def _run_refresh_service(
        self,
        *,
        task_status: anyio.abc.TaskStatus[None] = anyio.TASK_STATUS_IGNORED,
    ) -> None:
        """Run refresh work inside the Dashboard lifespan's TaskGroup."""

        self._refresh_running = True
        kwargs = {
            "runtime_dir": self.config.data_root / "runtime",
            "registry": self.registry,
            "poll_interval": self.config.refresh_poll_seconds,
            "paths": self.config.startup_paths,
            "repos": self.config.startup_repos,
            "hot_paths": HOT_SNAPSHOT_PATHS,
        }
        try:
            if "task_status" in inspect.signature(self._refresh_loop).parameters:
                await self._refresh_loop(**kwargs, task_status=task_status)
            else:
                task_status.started()
                await self._refresh_loop(**kwargs)
        finally:
            self._refresh_running = False


__all__ = [
    "DashboardAppServices",
    "DashboardAppServicesConfig",
    "DashboardServiceHealth",
]
