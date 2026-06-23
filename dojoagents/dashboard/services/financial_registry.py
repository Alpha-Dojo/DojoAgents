from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Optional

from dojo.client.async_client import AsyncDojo

from dojoagents.dashboard.services.benchmark_store import BenchmarkStore
from dojoagents.dashboard.services.dojo_data_gateway import DojoDataGateway
from dojoagents.dashboard.services.dojo_sphere_service import DojoSphereService
from dojoagents.dashboard.services.kline_store import KlineStore
from dojoagents.dashboard.services.portfolio_service import PortfolioService
from dojoagents.dashboard.services.portfolio_store import PortfolioStore
from dojoagents.dashboard.services.sector_metrics_store import SectorMetricsStore
from dojoagents.dashboard.services.sector_performance_cache import SectorPerformanceCache
from dojoagents.dashboard.services.sector_store import SectorStore
from dojoagents.dashboard.services.stock_event_store import StockEventStore
from dojoagents.dashboard.services.stock_fin_indicators_store import StockFinIndicatorsStore
from dojoagents.dashboard.services.stock_income_store import StockIncomeStore
from dojoagents.dashboard.services.stock_news_store import StockNewsStore
from dojoagents.dashboard.services.stock_sector_store import StockSectorStore
from dojoagents.dashboard.services.stock_store import StockStore
from dojoagents.dashboard.services.sector_precomputed_store import SectorPrecomputedStore

logger = logging.getLogger(__name__)

PRELOAD_PHASES: tuple[tuple[str, ...], ...] = (
    (
        "sector_store",
        "stock_store",
        "benchmark_store",
        "stock_sector_store",
        "stock_fin_indicators_store",
        "stock_event_store",
        "stock_income_store",
        "stock_news_store",
        "portfolio_store",
        "portfolio_service",
    ),
    ("kline_store",),
)


class FinancialDomainRegistry:
    """Instance-scoped dashboard registry bound to one FastAPI app."""

    def __init__(self) -> None:
        self.client: Optional[AsyncDojo] = None
        self.gateway: Optional[DojoDataGateway] = None
        self.sector_store: Optional[SectorStore] = None
        self.stock_store: Optional[StockStore] = None
        self.benchmark_store: Optional[BenchmarkStore] = None
        self.stock_sector_store: Optional[StockSectorStore] = None
        self.kline_store: Optional[KlineStore] = None
        self.stock_fin_indicators_store: Optional[StockFinIndicatorsStore] = None
        self.stock_event_store: Optional[StockEventStore] = None
        self.stock_income_store: Optional[StockIncomeStore] = None
        self.stock_news_store: Optional[StockNewsStore] = None
        self.forex_store = None
        self.portfolio_store: Optional[PortfolioStore] = None
        self.portfolio_service: Optional[PortfolioService] = None
        self.dojo_sphere_service: Optional[DojoSphereService] = None
        self.sector_precomputed_store: Optional[SectorPrecomputedStore] = None

    async def init_and_load_all(
        self,
        client: AsyncDojo,
        *,
        data_root: Path,
        preload: bool = True,
    ) -> None:
        self.client = client
        self.gateway = DojoDataGateway(client)
        self.sector_store = SectorStore(self.gateway)
        self.stock_store = StockStore(self.gateway)
        self.benchmark_store = BenchmarkStore(self.gateway)
        self.stock_sector_store = StockSectorStore(self.gateway)
        self.kline_store = KlineStore(
            self.gateway,
            self.stock_store,
            self.stock_sector_store,
            data_root=data_root,
        )
        self.stock_fin_indicators_store = StockFinIndicatorsStore(self.gateway)
        self.stock_event_store = StockEventStore(self.gateway)
        self.stock_income_store = StockIncomeStore(self.gateway)
        self.stock_news_store = StockNewsStore(self.gateway)
        from dojoagents.dashboard.services.forex_store import ForexStore

        self.forex_store = ForexStore(data_root, self.gateway)
        self.portfolio_store = PortfolioStore(data_root)
        self.portfolio_service = PortfolioService(
            store=self.portfolio_store,
            stock_store=self.stock_store,
            stock_sector_store=self.stock_sector_store,
            kline_store=self.kline_store,
            benchmark_store=self.benchmark_store,
        )
        self.dojo_sphere_service = DojoSphereService(
            SectorPerformanceCache(data_root, schema_version=1),
            SectorMetricsStore(data_root, schema_version=1),
        )
        self.sector_precomputed_store = SectorPrecomputedStore(data_root)

        if preload:
            await self.preload()

    async def preload(self, store_names: list[str] | None = None) -> list[Exception]:
        logger.info("Initializing and preloading registry data...")
        phases = [store_names] if store_names is not None else PRELOAD_PHASES
        errors: list[Exception] = []
        for phase in phases:
            tasks = []
            for store_name in phase:
                store_inst = getattr(self, store_name)
                if hasattr(store_inst, "load") and callable(store_inst.load):
                    tasks.append(store_inst.load())
            if not tasks:
                continue
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, Exception):
                    errors.append(res)
                    logger.error("Registry preload error: %s", res)
        logger.info("Registry preload complete.")
        return errors

    def reset(self) -> None:
        for name in (
            "client",
            "gateway",
            "sector_store",
            "stock_store",
            "benchmark_store",
            "stock_sector_store",
            "kline_store",
            "stock_fin_indicators_store",
            "stock_event_store",
            "stock_income_store",
            "stock_news_store",
            "forex_store",
            "portfolio_store",
            "portfolio_service",
            "dojo_sphere_service",
            "sector_precomputed_store",
        ):
            setattr(self, name, None)
