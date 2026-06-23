from typing import TypeVar

from fastapi import Request

from dojoagents.dashboard.services.financial_registry import FinancialDomainRegistry
from dojoagents.dashboard.store_manager import stores

from dojoagents.dashboard.services.benchmark_store import BenchmarkStore
from dojoagents.dashboard.services.kline_store import KlineStore
from dojoagents.dashboard.services.portfolio_service import PortfolioService
from dojoagents.dashboard.services.sector_store import SectorStore
from dojoagents.dashboard.services.stock_fin_indicators_store import StockFinIndicatorsStore
from dojoagents.dashboard.services.stock_event_store import StockEventStore
from dojoagents.dashboard.services.stock_income_store import StockIncomeStore
from dojoagents.dashboard.services.stock_news_store import StockNewsStore
from dojoagents.dashboard.services.stock_sector_store import StockSectorStore
from dojoagents.dashboard.services.stock_store import StockStore
from dojoagents.dashboard.services.dojo_sphere_service import DojoSphereService
from dojoagents.dashboard.services.sector_precomputed_store import SectorPrecomputedStore

T = TypeVar("T")


def _require(value: T | None, name: str) -> T:
    if value is None:
        raise RuntimeError(f"{name} is not initialized; Dashboard lifespan is not running")
    return value


def _registry_from_request(request: Request = None) -> FinancialDomainRegistry | None:
    if request is None:
        return None
    return getattr(request.app.state, "financial_registry", None)


def get_financial_registry(request: Request) -> FinancialDomainRegistry:
    registry = _registry_from_request(request)
    return _require(registry, "financial_registry")


def get_sector_store(request: Request = None) -> SectorStore:
    registry = _registry_from_request(request)
    if registry is not None:
        return _require(registry.sector_store, "sector_store")
    return _require(stores.sector_store, "sector_store")


def get_stock_store(request: Request = None) -> StockStore:
    registry = _registry_from_request(request)
    if registry is not None:
        return _require(registry.stock_store, "stock_store")
    return _require(stores.stock_store, "stock_store")


def get_benchmark_store(request: Request = None) -> BenchmarkStore:
    registry = _registry_from_request(request)
    if registry is not None:
        return _require(registry.benchmark_store, "benchmark_store")
    return _require(stores.benchmark_store, "benchmark_store")


def get_stock_sector_store(request: Request = None) -> StockSectorStore:
    registry = _registry_from_request(request)
    if registry is not None:
        return _require(registry.stock_sector_store, "stock_sector_store")
    return _require(stores.stock_sector_store, "stock_sector_store")


def get_kline_store(request: Request = None) -> KlineStore:
    registry = _registry_from_request(request)
    if registry is not None:
        return _require(registry.kline_store, "kline_store")
    return _require(stores.kline_store, "kline_store")


def get_stock_fin_indicators_store(
    request: Request = None,
) -> StockFinIndicatorsStore:
    registry = _registry_from_request(request)
    if registry is not None:
        return _require(registry.stock_fin_indicators_store, "stock_fin_indicators_store")
    return _require(stores.stock_fin_indicators_store, "stock_fin_indicators_store")


def get_stock_event_store(request: Request = None) -> StockEventStore:
    registry = _registry_from_request(request)
    if registry is not None:
        return _require(registry.stock_event_store, "stock_event_store")
    return _require(stores.stock_event_store, "stock_event_store")


def get_stock_income_store(request: Request = None) -> StockIncomeStore:
    registry = _registry_from_request(request)
    if registry is not None:
        return _require(registry.stock_income_store, "stock_income_store")
    return _require(stores.stock_income_store, "stock_income_store")


def get_stock_news_store(request: Request = None) -> StockNewsStore:
    registry = _registry_from_request(request)
    if registry is not None:
        return _require(registry.stock_news_store, "stock_news_store")
    return _require(stores.stock_news_store, "stock_news_store")


def get_portfolio_service(request: Request = None) -> PortfolioService:
    registry = _registry_from_request(request)
    if registry is not None:
        return _require(registry.portfolio_service, "portfolio_service")
    return _require(stores.portfolio_service, "portfolio_service")


def get_dojo_sphere_service(request: Request = None) -> DojoSphereService:
    registry = _registry_from_request(request)
    if registry is not None:
        return _require(registry.dojo_sphere_service, "dojo_sphere_service")
    return _require(stores.dojo_sphere_service, "dojo_sphere_service")


def get_sector_precomputed_store(request: Request = None) -> SectorPrecomputedStore:
    registry = _registry_from_request(request)
    if registry is not None:
        return _require(registry.sector_precomputed_store, "sector_precomputed_store")
    return _require(stores.sector_precomputed_store, "sector_precomputed_store")
