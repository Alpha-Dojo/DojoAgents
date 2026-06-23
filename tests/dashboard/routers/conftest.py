from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from dojoagents.dashboard import deps
from dojoagents.dashboard.routers import dojo_core, dojo_mesh, dojo_sphere
import dojoagents.dashboard.routers.market as market_router
import dojoagents.dashboard.routers.sector as sector_router
import dojoagents.dashboard.routers.utility as utility_router
from dojoagents.dashboard.schemas.benchmark import DojoMeshBenchmarksResponse
from dojoagents.dashboard.schemas.dojo_core import (
    CoreTickerPeBandResponse,
    CoreTickerQuoteResponse,
    CoreTickerSectorResponse,
)
from dojoagents.dashboard.schemas.dojo_mesh import (
    DojoMeshSectorsResponse,
)
from dojoagents.dashboard.schemas.dojo_sphere import (
    SectorConstituentsResponse,
    SectorPerformanceResponse,
    SectorScopeMetricsResponse,
)
from dojoagents.dashboard.schemas.market import MarketStats
from dojoagents.dashboard.schemas.portfolio import (
    PortfolioDetail,
    PortfolioSearchResponse,
    PortfolioSummary,
)
from dojoagents.dashboard.schemas.sector import SectorTaxonomyDocumentResponse
from dojoagents.dashboard.schemas.stock_event import CoreTickerEventsResponse
from dojoagents.dashboard.schemas.stock_fin_indicators import CoreTickerFinIndicatorsResponse
from dojoagents.dashboard.schemas.stock_income import CoreTickerIncomeResponse
from dojoagents.dashboard.schemas.stock_kline import (
    ConstituentKlineBatchResponse,
    ConstituentKlineStatsResponse,
    SectorConstituentKlineResponse,
    StockKlineResponse,
)
from dojoagents.dashboard.schemas.stock_news import CoreTickerNewsResponse
from dojoagents.dashboard.server import create_app
import dojoagents.dashboard.services.domain_api as domain_api
from dojoagents.dashboard.schemas.domain_api import (
    CompanyTickerSearchResponse,
    MarketOverviewMarket,
    MarketOverviewResponse,
    PortfolioAnalysisResponseV1,
    PortfolioListResponseV1,
    SectorAnalysisResponse,
    SectorAnalysisScope,
    SectorConstituentsResponseV1,
    SectorMoversMarket,
    SectorMoversResponse,
)


class ResourceStore:
    async def get_for_ticker(self, ticker, market=None, **_kwargs):
        symbol = ticker.strip().upper()
        market_code = market or "us"
        if self.kind == "events":
            return CoreTickerEventsResponse(ticker=symbol, market=market_code, source="sdk_online")
        if self.kind == "news":
            return CoreTickerNewsResponse(ticker=symbol, market=market_code, source="sdk_online")
        if self.kind == "fin":
            return CoreTickerFinIndicatorsResponse(
                ticker=symbol,
                market=market_code,
                report_type="quarter",
                source="sdk_online",
            )
        return CoreTickerIncomeResponse(ticker=symbol, market=market_code, source="sdk_online")

    def __init__(self, kind: str) -> None:
        self.kind = kind


class KlineStore:
    async def get_or_fetch_kline(self, symbol, **_kwargs):
        return StockKlineResponse(symbol=symbol)

    async def get_kline(self, symbol, **_kwargs):
        return StockKlineResponse(symbol=symbol)

    async def get_klines(self, symbols, **_kwargs):
        return ConstituentKlineBatchResponse(items={symbol: StockKlineResponse(symbol=symbol) for symbol in symbols})

    async def prioritize_sector_path(self, *_args, **_kwargs):
        return None

    async def get_sector_klines(self, path, market=None):
        return SectorConstituentKlineResponse(
            level1_id=path.level1_id,
            level2_id=path.level2_id,
            level3_id=path.level3_id,
            market=market,
        )

    async def stats(self):
        return ConstituentKlineStatsResponse()


class StockStore:
    def get(self, market, ticker):
        return SimpleNamespace(market=market, ticker=ticker)

    def find_market(self, _ticker):
        return "us"

    def all_market_stats(self):
        return {market: self.market_stats(market) for market in ("sh", "hk", "us")}

    def market_stats(self, market):
        return MarketStats(
            market=market,
            listed_count=1,
            total_market_cap=1.0,
            pe_sample_count=1,
        )


class SectorStore:
    path = SimpleNamespace(level1_id="1", level2_id="2", level3_id="3")

    def find_resolved_path(self, *_args):
        return self.path

    def to_taxonomy_document(self):
        return SectorTaxonomyDocumentResponse()


class BenchmarkStore:
    async def get_benchmarks(self):
        return DojoMeshBenchmarksResponse()


class PortfolioService:
    detail = PortfolioDetail(id="p1", name="Primary")

    async def list_summaries(self):
        return [PortfolioSummary(id="p1", name="Primary")]

    async def search(self, query):
        return PortfolioSearchResponse(query=query)

    async def get_detail(self, _portfolio_id, **_kwargs):
        return self.detail

    async def create(self, body):
        return self.detail.model_copy(update={"name": body.name})

    async def update(self, _portfolio_id, body):
        return self.detail.model_copy(update={"name": body.name or self.detail.name})

    async def delete(self, _portfolio_id):
        return True

    async def add_holding(self, _portfolio_id, _body):
        return self.detail

    async def auto_allocate(self, _portfolio_id, _body):
        return self.detail


@pytest.fixture
def financial_client(monkeypatch) -> TestClient:
    runtime = SimpleNamespace(config_store=None, agent=None, scheduler=None, extensions=None)
    app = create_app(runtime)
    stock_store = StockStore()
    sector_store = SectorStore()
    kline_store = KlineStore()
    registry = SimpleNamespace(
        stock_store=stock_store,
        stock_sector_store=SimpleNamespace(),
        sector_store=sector_store,
        kline_store=kline_store,
        benchmark_store=BenchmarkStore(),
        stock_event_store=ResourceStore("events"),
        stock_news_store=ResourceStore("news"),
        stock_fin_indicators_store=ResourceStore("fin"),
        stock_income_store=ResourceStore("income"),
        portfolio_service=PortfolioService(),
        dojo_sphere_service=SimpleNamespace(
            metrics=lambda _key, compute: compute(),
            performance=lambda _key, compute: _sphere_performance_cache(compute),
        ),
    )

    app.dependency_overrides.update(
        {
            deps.get_financial_registry: lambda: registry,
            deps.get_stock_store: lambda: stock_store,
            deps.get_stock_sector_store: lambda: SimpleNamespace(),
            deps.get_sector_store: lambda: sector_store,
            deps.get_kline_store: lambda: kline_store,
            deps.get_benchmark_store: lambda: BenchmarkStore(),
            deps.get_stock_event_store: lambda: ResourceStore("events"),
            deps.get_stock_news_store: lambda: ResourceStore("news"),
            deps.get_stock_fin_indicators_store: lambda: ResourceStore("fin"),
            deps.get_stock_income_store: lambda: ResourceStore("income"),
            deps.get_portfolio_service: lambda: PortfolioService(),
            deps.get_dojo_sphere_service: lambda: registry.dojo_sphere_service,
            deps.get_sector_precomputed_store: lambda: SimpleNamespace(),
        }
    )

    monkeypatch.setattr(dojo_core, "search_core_tickers", lambda *_args, **_kwargs: [])
    monkeypatch.setattr(
        dojo_core,
        "resolve_core_ticker_sector",
        lambda *_args, **_kwargs: CoreTickerSectorResponse(ticker="AAPL", market="us"),
    )
    monkeypatch.setattr(
        dojo_core,
        "resolve_core_ticker_quote",
        lambda *_args, **_kwargs: CoreTickerQuoteResponse(
            ticker="AAPL",
            market="us",
            last_price=100,
            change=1,
            change_percent=1,
            pre_close=99,
            open=99,
            high=101,
            low=98,
            volume=100,
            market_cap=1_000_000_001,
            pe=20,
            pb=3,
            turn_rate=1,
        ),
    )

    async def pe_band(*_args, **_kwargs):
        return CoreTickerPeBandResponse(ticker="AAPL", market="us", total_shares=10)

    monkeypatch.setattr(dojo_core, "resolve_core_ticker_pe_band", pe_band)
    monkeypatch.setattr(
        dojo_mesh,
        "compute_all_market_sector_leads",
        lambda *_args, **_kwargs: DojoMeshSectorsResponse(),
    )
    monkeypatch.setattr(
        dojo_mesh,
        "lookup_cross_market_sectors",
        lambda *_args, **_kwargs: {},
    )

    async def sphere_metrics(*_args, **_kwargs):
        return SectorScopeMetricsResponse(level1_id="1", level2_id="2", level3_id="3")

    async def sphere_constituents(*_args, **_kwargs):
        return SectorConstituentsResponse(level1_id="1", level2_id="2", level3_id="3")

    async def sphere_performance(*_args, **_kwargs):
        return SectorPerformanceResponse(level1_id="1", level2_id="2", level3_id="3")

    monkeypatch.setattr(dojo_sphere, "compute_sector_scope_metrics", sphere_metrics)
    monkeypatch.setattr(dojo_sphere, "list_sector_constituents", sphere_constituents)
    monkeypatch.setattr(dojo_sphere, "compute_sector_scope_performance", sphere_performance)

    async def utility_search(*_args, **_kwargs):
        return CompanyTickerSearchResponse(query="AAPL", items=[])

    monkeypatch.setattr(domain_api, "search_company_ticker", utility_search)
    monkeypatch.setattr(utility_router, "search_company_ticker", utility_search)
    monkeypatch.setattr(domain_api, "build_taxonomy_tree", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(utility_router, "build_taxonomy_tree", lambda *_args, **_kwargs: {})

    async def market_overview(*_args, **_kwargs):
        return MarketOverviewResponse(
            days=1,
            markets={
                "us": MarketOverviewMarket(
                    market="us",
                    stats=stock_store.market_stats("us"),
                    default_benchmark="^SPX",
                    benchmarks=[],
                )
            },
            source="computed",
            stale=False,
        )

    async def sector_movers(*_args, **_kwargs):
        return SectorMoversResponse(
            days=1,
            markets={"us": SectorMoversMarket(market="us", days=1, gainers=[], losers=[])},
            source="computed",
            stale=False,
        )

    async def sector_analysis(*_args, **_kwargs):
        return SectorAnalysisResponse(
            level1_id="1",
            level2_id="2",
            level3_id="3",
            scope="L3",
            scopes={
                "L3": SectorAnalysisScope(
                    scope="L3",
                    metrics=SectorScopeMetricsResponse(level1_id="1", level2_id="2", level3_id="3").model_dump(),
                    performance=SectorPerformanceResponse(level1_id="1", level2_id="2", level3_id="3").model_dump(),
                )
            },
            source="computed",
            stale=False,
        )

    async def sector_constituents_v1(*_args, **_kwargs):
        return SectorConstituentsResponseV1(level1_id="1", level2_id="2", level3_id="3")

    async def portfolio_list_v1(*_args, **_kwargs):
        return PortfolioListResponseV1(items=[PortfolioSummary(id="p1", name="Primary")], source="local", stale=False)

    async def portfolio_analysis_v1(*_args, **_kwargs):
        return PortfolioAnalysisResponseV1(detail=PortfolioDetail(id="p1", name="Primary"), source="local", stale=False)

    monkeypatch.setattr(domain_api, "build_market_overview", market_overview)
    monkeypatch.setattr(market_router, "build_market_overview", market_overview)
    monkeypatch.setattr(domain_api, "build_sector_movers", sector_movers)
    monkeypatch.setattr(market_router, "build_sector_movers", sector_movers)
    monkeypatch.setattr(domain_api, "build_sector_analysis", sector_analysis)
    monkeypatch.setattr(sector_router, "build_sector_analysis", sector_analysis)
    monkeypatch.setattr(domain_api, "build_sector_constituents_v1", sector_constituents_v1)
    monkeypatch.setattr(sector_router, "build_sector_constituents_v1", sector_constituents_v1)
    monkeypatch.setattr(domain_api, "build_portfolio_list_v1", portfolio_list_v1)
    monkeypatch.setattr(domain_api, "build_portfolio_analysis_v1", portfolio_analysis_v1)
    return TestClient(app)


async def _sphere_performance_cache(compute):
    payload = await compute()
    return {"payload": payload, "source": "computed", "stale": False, "as_of": None}
