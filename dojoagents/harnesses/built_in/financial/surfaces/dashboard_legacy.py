"""Compatibility lifecycle for the synchronous Financial Dashboard host."""

from __future__ import annotations

import asyncio
import datetime
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from dojo.client.async_client import AsyncDojo

from dojoagents.config.models import FinancialDashboardConfig
from dojoagents.logging import LOGGER
from ..context import FinancialRequestContextCodec
from ..services.constituent_kline_refresh_state import RefreshStateStore
from ..services.financial_registry import FinancialDomainRegistry
from ..services.market_refresh_jobs import start_refresh_loop
from ..services.stock_quote_filter import configure_ticker_market_cap_mins
from ..tools.domain_runtime import register_dashboard_domain_tools
from ..tools.portfolio_runtime import register_dashboard_portfolio_tools
from .dashboard import FinancialDashboardSurface


async def _close_client(client: Any) -> None:
    close = getattr(client, "aclose", None)
    if callable(close):
        await close()
        return
    http_client = getattr(client, "_client", None)
    close = getattr(http_client, "aclose", None)
    if callable(close):
        await close()


class LegacyFinancialDashboardSurface(FinancialDashboardSurface):
    """Keep the old synchronous Runtime usable without polluting the host."""

    def __init__(
        self,
        root_config: Any | None,
        *,
        client_factory=AsyncDojo,
        registry: Any | None = None,
        data_root: Path | None = None,
    ) -> None:
        self.root_config = root_config
        self.client_factory = client_factory
        self._registry = registry or FinancialDomainRegistry()
        self.data_root_override = data_root
        self.context_codec = FinancialRequestContextCodec()
        super().__init__(type("_RegistryContainer", (), {"registry": self._registry})())

    @classmethod
    def from_runtime(
        cls,
        runtime: Any,
        **options: Any,
    ) -> "LegacyFinancialDashboardSurface":
        store = getattr(runtime, "config_store", None)
        config = store.snapshot() if store is not None else None
        return cls(config, **options)

    def decode_request_context(self, value: Any) -> Any:
        return self.context_codec.decode(value)

    def configure_runtime(self, runtime: Any) -> None:
        agent = getattr(runtime, "agent", None)
        executor = getattr(agent, "tool_executor", None)
        registry = getattr(executor, "registry", None)
        if registry is None:
            return
        register_dashboard_domain_tools(registry, self.registry)
        register_dashboard_portfolio_tools(registry, self.registry)

    @asynccontextmanager
    async def lifespan(self, app: Any, runtime: Any):
        config = self.root_config
        sdk_config = getattr(config, "dojosdk", None)
        offline_mode = getattr(config, "offline_mode", True)
        financial_config = config.dashboard.financial if config is not None else FinancialDashboardConfig()
        configure_ticker_market_cap_mins(
            sh=financial_config.ticker_market_cap_min_sh,
            us=financial_config.ticker_market_cap_min_us,
            hk=financial_config.ticker_market_cap_min_hk,
        )
        os.environ["DOJO_CACHE_DIR"] = str(financial_config.sdk_cache_path)
        if offline_mode:
            os.environ["DOJO_ONLINE"] = "0"
        data_root = (self.data_root_override or financial_config.dashboard_data_path).expanduser()
        client = self.client_factory(
            api_key=sdk_config.api_key if sdk_config else None,
            base_url=sdk_config.base_url if sdk_config else None,
            timeout=sdk_config.timeout if sdk_config else 60.0,
            max_retries=sdk_config.max_retries if sdk_config else 1,
        )
        refresh_task = None
        try:
            if hasattr(client, "preload_offline_data"):
                LOGGER.info("开始预加载 DojoSDK 离线数据")
                await client.preload_offline_data()
            await self.registry.init_and_load_all(
                client,
                data_root=data_root,
                preload=True,
            )
            refresh_store = RefreshStateStore(data_root / "runtime")
            await refresh_store.set_last_refresh_date_async(
                "preload_offline_data",
                datetime.date.today(),
            )
            app.state.dojo_client = client
            app.state.financial_registry = self.registry
            app.state.market_data_revision = refresh_store.get_market_data_revision()
            refresh_task = asyncio.create_task(
                start_refresh_loop(
                    runtime_dir=data_root / "runtime",
                    registry=self.registry,
                )
            )
            yield
        finally:
            if refresh_task is not None:
                refresh_task.cancel()
                try:
                    await refresh_task
                except asyncio.CancelledError:
                    pass
            await _close_client(client)
            reset = getattr(self.registry, "reset", None)
            if callable(reset):
                reset()


__all__ = ["LegacyFinancialDashboardSurface"]
