import asyncio
import logging
from pathlib import Path
from typing import Optional, Any

from dojo.client.async_client import AsyncDojo
from dojoagents.dashboard.services.benchmark_store import BenchmarkStore
from dojoagents.dashboard.services.kline_store import KlineStore
from dojoagents.dashboard.services.portfolio_store import PortfolioStore
from dojoagents.dashboard.services.portfolio_service import PortfolioService
from dojoagents.dashboard.services.sector_store import SectorStore
from dojoagents.dashboard.services.stock_fin_indicators_store import StockFinIndicatorsStore
from dojoagents.dashboard.services.stock_event_store import StockEventStore
from dojoagents.dashboard.services.stock_income_store import StockIncomeStore
from dojoagents.dashboard.services.stock_news_store import StockNewsStore
from dojoagents.dashboard.services.stock_sector_store import StockSectorStore
from dojoagents.dashboard.services.stock_store import StockStore
from dojoagents.dashboard.services.dojo_data_gateway import DojoDataGateway
from dojoagents.dashboard.services.dojo_sphere_service import DojoSphereService
from dojoagents.dashboard.services.sector_metrics_store import SectorMetricsStore
from dojoagents.dashboard.services.sector_movers_service import SectorMoversService
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
        "sector_precomputed_store",
    ),
    ("kline_store",),
)


class GlobalStores:
    client: Optional[AsyncDojo] = None
    gateway: Optional[DojoDataGateway] = None
    sector_store: Optional[SectorStore] = None
    stock_store: Optional[StockStore] = None
    benchmark_store: Optional[BenchmarkStore] = None
    stock_sector_store: Optional[StockSectorStore] = None
    kline_store: Optional[KlineStore] = None
    stock_fin_indicators_store: Optional[StockFinIndicatorsStore] = None
    stock_event_store: Optional[StockEventStore] = None
    stock_income_store: Optional[StockIncomeStore] = None
    stock_news_store: Optional[StockNewsStore] = None
    forex_store: Optional[Any] = None
    portfolio_store: Optional[PortfolioStore] = None
    portfolio_service: Optional[PortfolioService] = None
    dojo_sphere_service: Optional[DojoSphereService] = None
    sector_precomputed_store: Optional[SectorPrecomputedStore] = None
    sector_movers_service: Optional[SectorMoversService] = None

    @classmethod
    async def init_and_load_all(
        cls,
        client: AsyncDojo,
        *,
        data_root: Path,
        preload: bool = True,
    ) -> None:
        cls.client = client
        cls.gateway = DojoDataGateway(client)
        cls.sector_store = SectorStore(cls.gateway)
        cls.stock_store = StockStore(cls.gateway)
        cls.benchmark_store = BenchmarkStore(cls.gateway)
        cls.stock_sector_store = StockSectorStore(cls.gateway)
        cls.kline_store = KlineStore(
            cls.gateway,
            cls.stock_store,
            cls.stock_sector_store,
        )
        cls.stock_fin_indicators_store = StockFinIndicatorsStore(cls.gateway)
        cls.stock_event_store = StockEventStore(cls.gateway)
        cls.stock_income_store = StockIncomeStore(cls.gateway)
        cls.stock_news_store = StockNewsStore(cls.gateway)
        from dojoagents.dashboard.services.forex_store import ForexStore

        cls.forex_store = ForexStore(cls.gateway)
        cls.portfolio_store = PortfolioStore(Path("~/.dojo/data").expanduser())
        cls.portfolio_service = PortfolioService(
            store=cls.portfolio_store,
            stock_store=cls.stock_store,
            stock_sector_store=cls.stock_sector_store,
            kline_store=cls.kline_store,
            benchmark_store=cls.benchmark_store,
        )
        cls.dojo_sphere_service = DojoSphereService(
            SectorMetricsStore(data_root, schema_version=1),
        )
        cls.sector_precomputed_store = SectorPrecomputedStore(data_root)
        cls.kline_store.sector_precomputed_store = cls.sector_precomputed_store
        cls.sector_movers_service = SectorMoversService(
            sector_store=cls.sector_store,
            stock_store=cls.stock_store,
            sector_precomputed_store=cls.sector_precomputed_store,
        )
        cls.sector_precomputed_store.sector_movers_service = cls.sector_movers_service

        if preload:
            await cls.preload()

    @classmethod
    async def preload(cls, store_names: list[str] | None = None) -> list[Exception]:
        from typing import Any

        try:
            from tqdm.asyncio import tqdm
        except ImportError:
            tqdm = None

        logger.info("Initializing and preloading store data...")
        phases = [store_names] if store_names is not None else PRELOAD_PHASES
        errors: list[Exception] = []
        for phase_idx, phase in enumerate(phases, 1):
            tasks = []

            async def _load_store(name: str, inst: Any) -> Any:
                logger.info(f"开始加载 Store: {name} ...")
                try:
                    await inst.load()
                    logger.info(f"Store {name} 加载完成。")
                except Exception as e:
                    logger.error(f"Store {name} 加载失败: {e}")
                    raise

            for store_name in phase:
                store_inst = getattr(cls, store_name)
                if hasattr(store_inst, "load") and callable(store_inst.load):
                    tasks.append(_load_store(store_name, store_inst))
            if not tasks:
                continue

            if tqdm is not None:
                pbar = tqdm(total=len(tasks), desc=f"Store Preload Phase {phase_idx}")

                async def _wrap_task(task):
                    try:
                        return await task
                    finally:
                        pbar.update(1)

                wrapped_tasks = [_wrap_task(t) for t in tasks]
                results = await asyncio.gather(*wrapped_tasks, return_exceptions=True)
                pbar.close()
            else:
                results = await asyncio.gather(*tasks, return_exceptions=True)

            for res in results:
                if isinstance(res, Exception):
                    errors.append(res)
                    logger.error("Store preload error: %s", res)
        logger.info("Store data preloading complete.")
        return errors

    @classmethod
    def reset(cls) -> None:
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
            "sector_movers_service",
        ):
            setattr(cls, name, None)


stores = GlobalStores()
