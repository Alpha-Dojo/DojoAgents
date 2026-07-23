"""FastAPI dependencies owned by the Financial Dashboard surface."""

from __future__ import annotations

from typing import TypeVar

from fastapi import Request

from ..services.benchmark_store import BenchmarkStore
from ..services.dojo_sphere_service import DojoSphereService
from ..services.financial_registry import FinancialDomainRegistry
from ..services.kline_store import KlineStore
from ..services.legacy_store_manager import stores
from ..services.portfolio_service import PortfolioService
from ..services.sector_precomputed_store import SectorPrecomputedStore
from ..services.sector_store import SectorStore
from ..services.stock_event_store import StockEventStore
from ..services.stock_fin_indicators_store import StockFinIndicatorsStore
from ..services.stock_income_store import StockIncomeStore
from ..services.stock_news_store import StockNewsStore
from ..services.stock_sector_store import StockSectorStore
from ..services.stock_store import StockStore

T = TypeVar("T")


def _require(value: T | None, name: str) -> T:
    if value is None:
        raise RuntimeError(f"{name} is not initialized; Dashboard lifespan is not running")
    return value


def _registry_from_request(
    request: Request = None,
) -> FinancialDomainRegistry | None:
    if request is None:
        return None
    return getattr(request.app.state, "financial_registry", None)


def get_financial_registry(request: Request) -> FinancialDomainRegistry:
    return _require(_registry_from_request(request), "financial_registry")


def _registry_value(request: Request, name: str):
    registry = _registry_from_request(request)
    if registry is not None:
        return _require(getattr(registry, name, None), name)
    return _require(getattr(stores, name, None), name)


def get_sector_store(request: Request = None) -> SectorStore:
    return _registry_value(request, "sector_store")


def get_stock_store(request: Request = None) -> StockStore:
    return _registry_value(request, "stock_store")


def get_benchmark_store(request: Request = None) -> BenchmarkStore:
    return _registry_value(request, "benchmark_store")


def get_stock_sector_store(
    request: Request = None,
) -> StockSectorStore:
    return _registry_value(request, "stock_sector_store")


def get_kline_store(request: Request = None) -> KlineStore:
    return _registry_value(request, "kline_store")


def get_stock_fin_indicators_store(
    request: Request = None,
) -> StockFinIndicatorsStore:
    return _registry_value(request, "stock_fin_indicators_store")


def get_stock_event_store(
    request: Request = None,
) -> StockEventStore:
    return _registry_value(request, "stock_event_store")


def get_stock_income_store(
    request: Request = None,
) -> StockIncomeStore:
    return _registry_value(request, "stock_income_store")


def get_stock_news_store(request: Request = None) -> StockNewsStore:
    return _registry_value(request, "stock_news_store")


def get_portfolio_service(
    request: Request = None,
) -> PortfolioService:
    return _registry_value(request, "portfolio_service")


def get_dojo_sphere_service(
    request: Request = None,
) -> DojoSphereService:
    return _registry_value(request, "dojo_sphere_service")


def get_sector_precomputed_store(
    request: Request = None,
) -> SectorPrecomputedStore:
    return _registry_value(request, "sector_precomputed_store")


def get_forex_store(request: Request = None):
    registry = _registry_from_request(request)
    if registry is not None:
        return getattr(registry, "forex_store", None)
    return getattr(stores, "forex_store", None)


__all__ = [
    "get_benchmark_store",
    "get_dojo_sphere_service",
    "get_financial_registry",
    "get_forex_store",
    "get_kline_store",
    "get_portfolio_service",
    "get_sector_precomputed_store",
    "get_sector_store",
    "get_stock_event_store",
    "get_stock_fin_indicators_store",
    "get_stock_income_store",
    "get_stock_news_store",
    "get_stock_sector_store",
    "get_stock_store",
]
