from __future__ import annotations

import anyio
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
from dojoagents.dashboard.services.sector_store import SectorStore
from dojoagents.dashboard.services.stock_event_store import StockEventStore
from dojoagents.dashboard.services.stock_fin_indicators_store import StockFinIndicatorsStore
from dojoagents.dashboard.services.stock_income_store import StockIncomeStore
from dojoagents.dashboard.services.stock_news_store import StockNewsStore
from dojoagents.dashboard.services.stock_sector_store import StockSectorStore
from dojoagents.dashboard.services.stock_store import StockStore
from dojoagents.dashboard.services.sector_movers_service import SectorMoversService
from dojoagents.dashboard.services.sector_precomputed_store import SectorPrecomputedStore
from dojoagents.dashboard.services.theme_state_precomputed_store import ThemeStatePrecomputedStore
from dojoagents.logging import LOGGER
from dojoagents.utils.async_runtime import gather_ordered

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
        "theme_state_precomputed_store",
    ),
)

STARTUP_PRELOAD_STORE_ALLOWLIST = frozenset(
    {
        "sector_store",
        "benchmark_store",
        "portfolio_store",
        "portfolio_service",
    }
)


def _repo_slug(repo_id: str) -> str:
    return str(repo_id).strip().rsplit("/", 1)[-1].lower()


class FinancialDomainRegistry:
    """Instance-scoped dashboard registry bound to one FastAPI app."""

    def __init__(self) -> None:
        self.client: Optional[AsyncDojo] = None
        self.live_client: Optional[AsyncDojo] = None
        self.gateway: Optional[DojoDataGateway] = None
        self.data_root: Optional[Path] = None
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
        self.theme_state_precomputed_store: Optional[ThemeStatePrecomputedStore] = None
        self.sector_movers_service: Optional[SectorMoversService] = None
        self.refresh_store = None
        self._loaded_store_names: set[str] = set()
        self._lazy_load_locks: dict[str, anyio.Lock] = {}

    async def init_and_load_all(
        self,
        client: AsyncDojo,
        *,
        live_client: AsyncDojo | None = None,
        data_root: Path,
        preload: bool = True,
        portfolio_data_root: Path | None = None,
        kline_max_concurrent: int = 50,
    ) -> None:
        self.client = client
        self.live_client = live_client
        self.gateway = DojoDataGateway(
            client,
            live_client=live_client,
            kline_max_concurrent=kline_max_concurrent,
        )
        self.data_root = data_root.expanduser().resolve()
        self.sector_store = SectorStore(self.gateway)
        self.stock_store = StockStore(self.gateway)
        self.benchmark_store = BenchmarkStore(self.gateway)
        self.stock_sector_store = StockSectorStore(self.gateway)
        self.kline_store = KlineStore(
            self.gateway,
            self.stock_store,
            self.stock_sector_store,
            data_root=self.data_root,
        )
        self.stock_fin_indicators_store = StockFinIndicatorsStore(self.gateway)
        self.stock_event_store = StockEventStore(self.gateway)
        self.stock_income_store = StockIncomeStore(self.gateway)
        self.stock_news_store = StockNewsStore(self.gateway)
        from dojoagents.dashboard.services.forex_store import ForexStore

        self.forex_store = ForexStore(self.gateway)
        self.portfolio_store = PortfolioStore((portfolio_data_root or Path("~/.dojo/data")).expanduser().resolve())
        from dojoagents.dashboard.services.constituent_kline_refresh_state import RefreshStateStore

        refresh_store = RefreshStateStore(self.data_root / "runtime")
        self.refresh_store = refresh_store
        self.portfolio_service = PortfolioService(
            store=self.portfolio_store,
            stock_store=self.stock_store,
            stock_sector_store=self.stock_sector_store,
            kline_store=self.kline_store,
            benchmark_store=self.benchmark_store,
            market_data_revision_reader=lambda: refresh_store.get_market_data_revision().get("revision") or "",
        )
        self.dojo_sphere_service = DojoSphereService(
            SectorMetricsStore(data_root, schema_version=1),
            revision_provider=lambda: (
                self.sector_precomputed_store.data_revision()
                if self.sector_precomputed_store is not None
                else None
            ),
        )
        self.sector_precomputed_store = SectorPrecomputedStore(
            self.data_root,
            snapshot_client=client,
        )
        self.theme_state_precomputed_store = ThemeStatePrecomputedStore(self.data_root)
        self.kline_store.sector_precomputed_store = self.sector_precomputed_store
        self.sector_movers_service = SectorMoversService(
            sector_store=self.sector_store,
            stock_store=self.stock_store,
            sector_precomputed_store=self.sector_precomputed_store,
        )
        self.sector_precomputed_store.sector_movers_service = self.sector_movers_service

        if preload:
            await self.preload()

    async def preload(self, store_names: list[str] | None = None) -> list[Exception]:
        from typing import Any

        try:
            from tqdm.asyncio import tqdm
        except ImportError:
            tqdm = None

        LOGGER.debug("Initializing and preloading registry data...")
        phases = [store_names] if store_names is not None else PRELOAD_PHASES
        errors: list[Exception] = []
        for phase_idx, phase in enumerate(phases, 1):
            operations = []

            async def _load_store(name: str, inst: Any) -> Any:
                LOGGER.debug(f"开始加载 Store: {name} ...")
                try:
                    await inst.load()
                    self._loaded_store_names.add(name)
                    LOGGER.debug(f"Store {name} 加载完成。")
                except Exception as e:
                    LOGGER.error(f"Store {name} 加载失败: {e}")
                    raise

            for store_name in phase:
                store_inst = getattr(self, store_name)
                if hasattr(store_inst, "load") and callable(store_inst.load):
                    operations.append(
                        lambda store_name=store_name, store_inst=store_inst: _load_store(store_name, store_inst)
                    )
            if not operations:
                continue

            if tqdm is not None:
                pbar = tqdm(total=len(operations), desc=f"Registry Preload Phase {phase_idx}")

                async def _wrap_operation(operation):
                    try:
                        return await operation()
                    finally:
                        pbar.update(1)

                wrapped_operations = [
                    lambda operation=operation: _wrap_operation(operation)
                    for operation in operations
                ]
                results = await gather_ordered(wrapped_operations, return_exceptions=True)
                pbar.close()
            else:
                results = await gather_ordered(operations, return_exceptions=True)

            for res in results:
                if isinstance(res, Exception):
                    errors.append(res)
                    LOGGER.error("Registry preload error: %s", res)
        LOGGER.debug("Registry preload complete.")
        return errors

    async def ensure_stores_loaded(self, *store_names: str) -> None:
        """Load feature stores once, on first use, without blocking startup.

        A per-store lock prevents concurrent Dashboard requests from loading the
        same Parquet-backed store more than once.
        """
        for name in dict.fromkeys(str(item).strip() for item in store_names if str(item).strip()):
            if name in self._loaded_store_names:
                continue
            store = getattr(self, name, None)
            if store is None or not callable(getattr(store, "load", None)):
                raise RuntimeError(f"{name} is not initialized or loadable")
            lock = self._lazy_load_locks.setdefault(name, anyio.Lock())
            async with lock:
                if name in self._loaded_store_names:
                    continue
                await store.load()
                self._loaded_store_names.add(name)

    async def preload_startup(self, store_names: tuple[str, ...] | list[str]) -> list[Exception]:
        """Preload only explicitly approved small stores during Dashboard startup."""
        selected = list(dict.fromkeys(str(name).strip() for name in store_names if str(name).strip()))
        unsupported = [name for name in selected if name not in STARTUP_PRELOAD_STORE_ALLOWLIST]
        if unsupported:
            raise ValueError(
                "Dashboard startup preload contains non-whitelisted stores: "
                + ", ".join(unsupported)
            )
        return await self.preload(selected)

    async def refresh_after_offline_data_update(
        self,
        *,
        updated_repos: tuple[str, ...] | list[str],
    ) -> None:
        """Invalidate only response/derived caches that depend on committed repos."""
        repo_ids = tuple(dict.fromkeys(str(repo) for repo in updated_repos if str(repo).strip()))
        if not repo_ids:
            return
        slugs = {_repo_slug(repo) for repo in repo_ids}
        LOGGER.info("Refreshing caches for committed snapshot repositories: %s", repo_ids)

        if "dojo_stock_kline" in slugs:
            if self.kline_store is not None:
                self.kline_store.invalidate_repos(repo_ids)
            if self.gateway is not None and hasattr(self.gateway, "invalidate_kline_snapshot"):
                self.gateway.invalidate_kline_snapshot()

        reload_stores: list[str] = []
        if slugs & {"dojo_stock_info", "dojo_quote"}:
            reload_stores.append("stock_store")
        if "dojo_benchmark_kline" in slugs:
            reload_stores.append("benchmark_store")
        if "dojo_sector_info" in slugs:
            reload_stores.append("sector_store")
        if "dojo_sector_symbol_relations" in slugs:
            reload_stores.append("stock_sector_store")

        cache_store_by_repo = {
            "dojo_fin_indicators": "stock_fin_indicators_store",
            "dojo_event_remind": "stock_event_store",
            "dojo_main_income": "stock_income_store",
            "dojo_stock_news": "stock_news_store",
        }
        for repo_slug, store_name in cache_store_by_repo.items():
            if repo_slug not in slugs:
                continue
            store = getattr(self, store_name, None)
            cache = getattr(store, "cache", None)
            if isinstance(cache, dict):
                cache.clear()

        if "dojo_market_dynamics" in slugs:
            try:
                from dojoagents.dashboard.services.market_dynamics_service import (
                    clear_market_dynamics_cache,
                )

                clear_market_dynamics_cache()
            except Exception:
                LOGGER.exception("Failed to clear market dynamics cache after refresh")

        sector_dependencies = {
            "dojo_sector_info",
            "dojo_sector_symbol_relations",
            "dojo_sector_precomputed",
            "dojo_stock_info",
            "dojo_quote",
            "dojo_stock_kline",
        }
        if self.sector_movers_service is not None and slugs & sector_dependencies:
            self.sector_movers_service.invalidate()

        if "dojo_sector_precomputed" in slugs:
            if self.sector_precomputed_store is not None:
                self.sector_precomputed_store.clear_cache()
                await self.sector_precomputed_store.reload_async()
            if self.theme_state_precomputed_store is not None:
                self.theme_state_precomputed_store.clear_cache()
                self.theme_state_precomputed_store.reload()

        derived_metric_dependencies = sector_dependencies | {"dojo_benchmark_kline"}
        if self.dojo_sphere_service is not None and slugs & derived_metric_dependencies:
            await self.dojo_sphere_service.metrics_store.clear_all()

        for store_name in reload_stores:
            store = getattr(self, store_name, None)
            if store is not None and hasattr(store, "load"):
                try:
                    await store.load()
                except Exception:
                    LOGGER.exception(
                        "Failed to reload %s after repository update: %s",
                        store_name,
                        repo_ids,
                    )

    def reset(self) -> None:
        self._loaded_store_names.clear()
        self._lazy_load_locks.clear()
        for name in (
            "client",
            "gateway",
            "data_root",
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
            "theme_state_precomputed_store",
            "sector_movers_service",
            "refresh_store",
        ):
            setattr(self, name, None)
