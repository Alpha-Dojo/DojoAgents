from __future__ import annotations

import pytest

from dojoagents.dashboard.schemas.portfolio import CreatePortfolioOrderRequest
from dojoagents.dashboard.services.portfolio_order_preflight import preflight_buy_orders


def test_preflight_passes_when_budget_is_sufficient() -> None:
    result = preflight_buy_orders(
        capital_by_market={"cn": 1_000_000.0},
        prior_orders=[],
        buy_orders=[
            CreatePortfolioOrderRequest(
                ticker="688008.SS",
                market="sh",
                order_side="buy",
                price=100.0,
                qty=100,
                order_time="2026-06-18",
            ),
            CreatePortfolioOrderRequest(
                ticker="688012.SS",
                market="sh",
                order_side="buy",
                price=200.0,
                qty=100,
                order_time="2026-06-18",
            ),
        ],
    )

    assert result.ok is True
    assert result.markets == []


def test_preflight_fails_when_batch_exceeds_market_capital() -> None:
    big_orders = [
        CreatePortfolioOrderRequest(
            ticker=f"6880{i:02d}.SS",
            market="sh",
            order_side="buy",
            price=300.0,
            qty=100,
            order_time="2026-06-18",
        )
        for i in range(40)
    ]
    result = preflight_buy_orders(
        capital_by_market={"cn": 1_000_000.0},
        prior_orders=[],
        buy_orders=big_orders,
    )
    assert result.ok is False
    assert result.markets[0].shortfall > 0
    assert result.markets[0].required == pytest.approx(1_200_000.0)
    assert result.user_options
    context = result.escalation_context()
    assert context["native_market"] == "cn"
    assert context["order_count"] == 40
    assert context["uniform_qty"] == 100


def test_preflight_accounts_for_prior_filled_orders() -> None:
    result = preflight_buy_orders(
        capital_by_market={"us": 100_000.0},
        prior_orders=[
            {
                "id": "o1",
                "ticker": "AAPL",
                "market": "us",
                "order_side": "buy",
                "order_status": "filled",
                "price": 100.0,
                "qty": 900,
                "fill_price": 100.0,
                "order_time": "2026-06-18",
                "fill_time": "2026-06-18",
                "created_at": "2026-06-18T00:00:00+00:00",
            }
        ],
        buy_orders=[
            CreatePortfolioOrderRequest(
                ticker="NVDA",
                market="us",
                order_side="buy",
                price=200.0,
                qty=100,
                order_time="2026-06-18",
            )
        ],
    )

    assert result.ok is False
    assert result.markets[0].available == pytest.approx(10_000.0)
    assert result.markets[0].required == pytest.approx(20_000.0)
