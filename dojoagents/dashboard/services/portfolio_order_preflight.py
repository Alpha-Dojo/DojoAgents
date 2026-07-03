from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from dojoagents.dashboard.schemas.portfolio import CreatePortfolioOrderRequest
from dojoagents.dashboard.services.domain_utils import to_native_market_code
from dojoagents.dashboard.services.portfolio_order_execution import replay_market_balance

MARKETS = ("us", "sh", "hk")


@dataclass(frozen=True)
class MarketBudgetSnapshot:
    market: str
    native_market: str
    available: float
    required: float
    shortfall: float
    order_count: int
    uniform_qty: float | None = None


@dataclass
class OrderPreflightResult:
    ok: bool
    markets: list[MarketBudgetSnapshot] = field(default_factory=list)
    user_options: list[str] = field(default_factory=list)

    def escalation_context(self) -> dict[str, Any]:
        by_market = [
            {
                "market": row.market,
                "native_market": row.native_market,
                "available": round(row.available, 2),
                "required": round(row.required, 2),
                "shortfall": round(row.shortfall, 2),
                "order_count": row.order_count,
                "uniform_qty": row.uniform_qty,
            }
            for row in self.markets
            if row.shortfall > 1e-9
        ]
        primary = by_market[0] if by_market else {}
        return {
            "markets": by_market,
            "user_options": list(self.user_options),
            **primary,
        }

    def escalation_message(self) -> str:
        if self.ok or not self.markets:
            return "Order preflight passed."
        parts: list[str] = []
        for row in self.markets:
            if row.shortfall <= 1e-9:
                continue
            parts.append(
                f"{row.native_market}: available {row.available:.2f}, "
                f"required {row.required:.2f}, shortfall {row.shortfall:.2f} "
                f"({row.order_count} buy orders)"
            )
        return "Capital budget exceeded — " + "; ".join(parts)


def _market_initial_capital(capital_by_market: dict[str, Any], market: str) -> float:
    if market in capital_by_market:
        return float(capital_by_market[market] or 0)
    if market == "sh" and "cn" in capital_by_market:
        return float(capital_by_market["cn"] or 0)
    return float(capital_by_market.get(market) or 0)


def _resolve_as_of_date(buy_orders: Iterable[CreatePortfolioOrderRequest], fallback: str | None) -> str:
    dates = [str(order.order_time)[:10] for order in buy_orders if order.order_time]
    if dates:
        return max(dates)
    if fallback:
        return fallback[:10]
    from datetime import date

    return date.today().isoformat()


def _uniform_qty(orders: list[CreatePortfolioOrderRequest]) -> float | None:
    quantities = {float(order.qty) for order in orders}
    if len(quantities) == 1:
        return quantities.pop()
    return None


def _build_user_options(snapshot: MarketBudgetSnapshot) -> list[str]:
    options = [
        (
            f"Raise {snapshot.native_market} initial capital to about "
            f"{snapshot.required:,.0f} in Folio settings (capital_by_market)."
        ),
        "Reduce the number of symbols in this build batch.",
    ]
    if snapshot.uniform_qty is not None and snapshot.market == "sh" and snapshot.uniform_qty >= 100:
        affordable = 0
        if snapshot.required > 0:
            affordable = max(0, int(snapshot.available // (snapshot.required / snapshot.order_count)))
        options.append(
            f"Keep {snapshot.uniform_qty:.0f} shares per symbol only if you also reduce to about "
            f"{affordable} symbols or lower for the current budget."
        )
    else:
        options.append("Ask for an explicit per-symbol share allocation if unequal sizing is acceptable.")
    options.append("Do NOT silently reduce share counts unless the user explicitly requests it.")
    return options


def preflight_buy_orders(
    *,
    capital_by_market: dict[str, Any] | None,
    prior_orders: list[dict[str, Any]],
    buy_orders: list[CreatePortfolioOrderRequest],
    as_of_date: str | None = None,
) -> OrderPreflightResult:
    if not buy_orders:
        return OrderPreflightResult(ok=True)

    capital = dict(capital_by_market or {})
    grouped: dict[str, list[CreatePortfolioOrderRequest]] = {market: [] for market in MARKETS}
    for order in buy_orders:
        market = str(order.market or "").strip().lower()
        if market not in grouped:
            continue
        grouped[market].append(order)

    snapshots: list[MarketBudgetSnapshot] = []
    user_options: list[str] = []
    for market, orders in grouped.items():
        if not orders:
            continue
        initial_capital = _market_initial_capital(capital, market)
        available, _ = replay_market_balance(
            prior_orders,
            market=market,
            initial_capital=initial_capital,
            as_of_date=_resolve_as_of_date(orders, as_of_date),
        )
        required = sum(float(order.price) * float(order.qty) for order in orders)
        shortfall = max(0.0, required - available)
        snapshot = MarketBudgetSnapshot(
            market=market,
            native_market=to_native_market_code(market) or market,
            available=available,
            required=required,
            shortfall=shortfall,
            order_count=len(orders),
            uniform_qty=_uniform_qty(orders),
        )
        snapshots.append(snapshot)
        if shortfall > 1e-9:
            user_options.extend(_build_user_options(snapshot))

    exceeded = [row for row in snapshots if row.shortfall > 1e-9]
    if not exceeded:
        return OrderPreflightResult(ok=True)

    return OrderPreflightResult(
        ok=False,
        markets=exceeded,
        user_options=user_options,
    )


def preflight_buy_orders_from_detail(
    detail: dict[str, Any],
    buy_orders: list[CreatePortfolioOrderRequest],
) -> OrderPreflightResult:
    config = detail.get("config") if isinstance(detail.get("config"), dict) else {}
    capital_by_market = config.get("capital_by_market") if isinstance(config, dict) else {}
    prior_orders = [row for row in (detail.get("orders") or []) if isinstance(row, dict)]
    as_of = str(config.get("start_date") or "")[:10] or None
    return preflight_buy_orders(
        capital_by_market=capital_by_market if isinstance(capital_by_market, dict) else {},
        prior_orders=prior_orders,
        buy_orders=buy_orders,
        as_of_date=as_of,
    )
