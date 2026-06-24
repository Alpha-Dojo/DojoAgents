from __future__ import annotations

from dojoagents.dashboard.schemas.portfolio import (
    PortfolioHoldingView,
    PortfolioSummary,
    UpdatePortfolioRequest,
)
from dojoagents.dashboard.services.portfolio_store import PortfolioStore


def test_portfolio_v2_schema_exposes_new_summary_and_holding_fields() -> None:
    summary = PortfolioSummary(id="p1", name="Primary", pinned=True)
    holding = PortfolioHoldingView(
        ticker="AAPL",
        name="Apple",
        name_zh="苹果",
        name_en="Apple",
        market="us",
        shares=10,
        cost=100,
        cost_low=95,
        cost_high=105,
        uses_default_cost=False,
        cost_basis=1_000,
        shares_locked=True,
        open_date_locked=True,
        cost_locked=True,
        sector_l1="Technology",
        sector_l2="Software",
        sector_l3="Application Software",
    )

    assert summary.pinned is True
    assert holding.cost_basis == 1_000
    assert holding.sector_l3 == "Application Software"


def test_update_request_accepts_v2_lock_and_override_maps() -> None:
    request = UpdatePortfolioRequest(
        pinned=True,
        shares_locked_by_ticker={"AAPL": True},
        open_date_locked_by_ticker={"AAPL": True},
        cost_locked_by_ticker={"AAPL": True},
        cost_override_by_ticker={"AAPL": 101.5},
    )

    assert request.pinned is True
    assert request.cost_override_by_ticker == {"AAPL": 101.5}


def test_store_persists_v2_holding_defaults_and_pinned_sort(tmp_path) -> None:
    store = PortfolioStore(tmp_path)
    first = store.create("First")
    second = store.create("Pinned")
    store.add_holding(first["id"], ticker="AAPL", market="us", shares=10)

    store.update(second["id"], pinned=True)

    reloaded = PortfolioStore(tmp_path)
    rows = reloaded.list_index_rows()
    holding = reloaded.get_raw(first["id"])["holdings"][0]
    assert rows[0]["id"] == second["id"]
    assert rows[0]["pinned"] is True
    assert holding["shares_locked"] is False
    assert holding["open_date_locked"] is False
    assert holding["cost_override"] is None
    assert holding["cost_locked"] is False


def test_store_persists_lock_and_cost_override_maps(tmp_path) -> None:
    store = PortfolioStore(tmp_path)
    portfolio = store.create("Primary")
    portfolio = store.add_holding(portfolio["id"], ticker="AAPL", market="us", shares=10)

    updated = store.update(
        portfolio["id"],
        shares_locked_by_ticker={"AAPL": True},
        open_date_locked_by_ticker={"AAPL": True},
        cost_locked_by_ticker={"AAPL": True},
        cost_override_by_ticker={"AAPL": 101.5},
    )

    holding = updated["holdings"][0]
    assert holding["shares_locked"] is True
    assert holding["manual_shares"] is True
    assert holding["open_date_locked"] is True
    assert holding["cost_locked"] is True
    assert holding["cost_override"] == 101.5
