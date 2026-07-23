from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from dojoagents.harnesses.built_in.financial.surfaces import (
    dashboard_dependencies as deps,
)
from dojoagents.harnesses.built_in.financial.surfaces.dashboard_routers.dojo_folio import router
from dojoagents.harnesses.built_in.financial.contracts.portfolio import UpdatePortfolioRequest
from dojoagents.harnesses.built_in.financial.services.kline_store import KlineStore
from dojoagents.harnesses.built_in.financial.services.portfolio_service import (
    PortfolioService,
    PortfolioValidationError,
)
from dojoagents.harnesses.built_in.financial.services.portfolio_store import PortfolioStore
from dojoagents.harnesses.built_in.financial.services.stock_sector_store import StockSectorStore
from dojoagents.harnesses.built_in.financial.services.stock_store import StockStore
from tests.dashboard.fakes.fake_dojo import FakeDojo


def _service(tmp_path, *, with_kline: bool = True) -> tuple[PortfolioService, PortfolioStore]:
    client = FakeDojo()
    stocks = StockStore(client)
    sectors = StockSectorStore(client)
    klines = KlineStore(client, stocks, sectors)
    if with_kline:
        klines.raw_by_symbol["AAPL"] = [
            {
                "symbol": "AAPL",
                "bar_time": "2025-01-02",
                "open": 100,
                "high": 105,
                "low": 95,
                "close": 102,
            }
        ]
    store = PortfolioStore(tmp_path)
    return PortfolioService(store, stocks, sectors, klines), store


def _portfolio(store: PortfolioStore) -> str:
    portfolio = store.create("Primary")
    store.add_holding(portfolio["id"], ticker="AAPL", market="us", shares=10)
    return portfolio["id"]


@pytest.mark.asyncio
async def test_locked_fields_preserve_values_until_explicitly_unlocked(tmp_path) -> None:
    service, store = _service(tmp_path)
    portfolio_id = _portfolio(store)
    store.update(
        portfolio_id,
        shares_by_ticker={"AAPL": 10},
        open_date_by_ticker={"AAPL": "2025-01-02"},
        cost_override_by_ticker={"AAPL": 100},
        shares_locked_by_ticker={"AAPL": True},
        open_date_locked_by_ticker={"AAPL": True},
        cost_locked_by_ticker={"AAPL": True},
    )

    await service.update(
        portfolio_id,
        UpdatePortfolioRequest(
            shares_by_ticker={"AAPL": 20},
            open_date_by_ticker={"AAPL": "2025-01-03"},
            cost_override_by_ticker={"AAPL": 103},
        ),
    )

    locked = store.get_raw(portfolio_id)["holdings"][0]
    assert locked["shares"] == 10
    assert locked["open_date"] == "2025-01-02"
    assert locked["cost_override"] == 100

    await service.update(
        portfolio_id,
        UpdatePortfolioRequest(
            shares_by_ticker={"AAPL": 20},
            open_date_by_ticker={"AAPL": "2025-01-02"},
            cost_override_by_ticker={"AAPL": 103},
            shares_locked_by_ticker={"AAPL": False},
            open_date_locked_by_ticker={"AAPL": False},
            cost_locked_by_ticker={"AAPL": False},
        ),
    )

    unlocked = store.get_raw(portfolio_id)["holdings"][0]
    assert unlocked["shares"] == 20
    assert unlocked["cost_override"] == 103


@pytest.mark.asyncio
async def test_cost_override_outside_open_day_range_is_rejected(tmp_path) -> None:
    service, store = _service(tmp_path)
    portfolio_id = _portfolio(store)

    with pytest.raises(PortfolioValidationError) as error:
        await service.update(
            portfolio_id,
            UpdatePortfolioRequest(
                open_date_by_ticker={"AAPL": "2025-01-02"},
                cost_override_by_ticker={"AAPL": 110},
            ),
        )

    assert error.value.field == "cost_override_by_ticker.AAPL"
    assert error.value.context == {"low": 95.0, "high": 105.0}
    assert store.get_raw(portfolio_id)["holdings"][0]["cost_override"] is None


@pytest.mark.asyncio
async def test_cost_override_without_kline_is_rejected(tmp_path) -> None:
    service, store = _service(tmp_path, with_kline=False)
    portfolio_id = _portfolio(store)

    with pytest.raises(PortfolioValidationError, match="kline"):
        await service.update(
            portfolio_id,
            UpdatePortfolioRequest(
                open_date_by_ticker={"AAPL": "2025-01-02"},
                cost_override_by_ticker={"AAPL": 100},
            ),
        )


def test_portfolio_validation_error_maps_to_http_400() -> None:
    class InvalidService:
        async def update(self, *_args, **_kwargs):
            raise PortfolioValidationError(
                "cost outside kline range",
                field="cost_override_by_ticker.AAPL",
                context={"low": 95, "high": 105},
            )

    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.dependency_overrides[deps.get_portfolio_service] = lambda: InvalidService()

    response = TestClient(app).patch(
        "/api/v1/dojo-folio/portfolios/p1",
        json={"cost_override_by_ticker": {"AAPL": 110}},
    )

    assert response.status_code == 400
    assert response.json()["detail"]["field"] == "cost_override_by_ticker.AAPL"
