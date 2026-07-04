from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Optional

from dojoagents.dashboard.services.domain_utils import normalize_market_code
from dojoagents.dashboard.services.kline_bar_utils import extract_bar_time, price_within_daily_range
from dojoagents.dashboard.services.kline_store import KlineStore
from dojoagents.dashboard.services.portfolio_kline_fetch import fetch_kline_bars_with_symbol_fallback

OrderSide = str  # "buy" | "sell"
OrderStatus = str  # "pending" | "filled" | "cancelled" | "rejected"


@dataclass(frozen=True)
class OrderFillFailure:
    code: str
    message: str
    context: dict[str, Any] = field(default_factory=dict)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_date(value: Any) -> Optional[str]:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if "T" in text:
        text = text.split("T", 1)[0]
    return text[:10]


def _row_dict(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return row
    if hasattr(row, "model_dump"):
        return row.model_dump()
    return {
        key: getattr(row, key)
        for key in ("bar_time", "datetime", "date", "open", "high", "low", "close")
        if hasattr(row, key)
    }


def _bar_for_date(bars: list[Any], target: str) -> Optional[dict[str, float]]:
    for row in bars:
        payload = _row_dict(row)
        bar_time = extract_bar_time(payload)[:10]
        if bar_time != target:
            continue
        try:
            open_price = float(payload.get("open") or 0)
            low = float(payload.get("low") or 0)
            high = float(payload.get("high") or 0)
        except (TypeError, ValueError):
            continue
        if open_price <= 0 or low <= 0 or high <= 0:
            continue
        return {"open": open_price, "low": low, "high": high, "date": bar_time}
    return None


def _next_trading_day(bars: list[Any], after_date: str) -> Optional[dict[str, float]]:
    candidates: list[tuple[str, dict[str, float]]] = []
    for row in bars:
        payload = _row_dict(row)
        bar_time = extract_bar_time(payload)[:10]
        if not bar_time or bar_time <= after_date:
            continue
        try:
            open_price = float(payload.get("open") or 0)
            low = float(payload.get("low") or 0)
            high = float(payload.get("high") or 0)
        except (TypeError, ValueError):
            continue
        if open_price <= 0 or low <= 0 or high <= 0:
            continue
        candidates.append((bar_time, {"open": open_price, "low": low, "high": high, "date": bar_time}))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0])
    return candidates[0][1]


def available_shares(orders: list[dict[str, Any]], *, market: str, ticker: str) -> float:
    shares = 0.0
    for order in orders:
        if str(order.get("order_status")) != "filled":
            continue
        if str(order.get("market")) != market or str(order.get("ticker")) != ticker:
            continue
        qty = float(order.get("qty") or 0)
        if str(order.get("order_side")) == "buy":
            shares += qty
        elif str(order.get("order_side")) == "sell":
            shares -= qty
    return max(shares, 0.0)


def resolve_market_initial_capital(capital_by_market: dict[str, Any] | None, market: str) -> float:
    capital = capital_by_market if isinstance(capital_by_market, dict) else {}
    if market in capital:
        return float(capital[market] or 0)
    if market == "sh" and "cn" in capital:
        return float(capital["cn"] or 0)
    if market == "cn" and "sh" in capital:
        return float(capital["sh"] or 0)
    return float(capital.get(market) or 0)


def _bar_dict_from_resolved(order: dict[str, Any]) -> Optional[dict[str, float]]:
    raw = order.get("resolved_bar")
    if not isinstance(raw, dict):
        return None
    bar_date = _parse_date(raw.get("date"))
    if not bar_date:
        return None
    try:
        open_price = float(raw.get("open") or 0)
        low = float(raw.get("low") or 0)
        high = float(raw.get("high") or 0)
    except (TypeError, ValueError):
        return None
    if open_price <= 0 or low <= 0 or high <= 0:
        return None
    return {"date": bar_date, "open": open_price, "low": low, "high": high}


async def _fetch_order_kline_bars(
    kline_store: KlineStore,
    *,
    ticker: str,
    market: str,
    scheduled_date: str | None = None,
    after_date: str | None = None,
    user_price: float | None = None,
) -> list[Any]:
    bars, _ = await fetch_kline_bars_with_symbol_fallback(
        kline_store,
        symbol=ticker,
        market=market,
        order_time=scheduled_date,
        user_price=user_price if scheduled_date is None else None,
        after_date=after_date if scheduled_date is None else None,
    )
    return bars


async def _resolve_scheduled_fill_bar(
    order: dict[str, Any],
    *,
    kline_store: KlineStore,
    ticker: str,
    market: str,
    scheduled: str,
) -> tuple[Optional[dict[str, float]], list[Any]]:
    resolved = _bar_dict_from_resolved(order)
    if resolved is not None and resolved["date"] == scheduled:
        return resolved, []

    bars = await _fetch_order_kline_bars(
        kline_store,
        ticker=ticker,
        market=market,
        scheduled_date=scheduled,
    )
    if not bars:
        return None, []
    return _bar_for_date(bars, scheduled), bars


async def evaluate_order_fill_failure(
    order: dict[str, Any],
    *,
    kline_store: KlineStore,
    prior_orders: list[dict[str, Any]],
    initial_capital: float = 0.0,
) -> Optional[OrderFillFailure]:
    ticker = str(order.get("ticker") or "")
    market = str(order.get("market") or "")
    side = str(order.get("order_side") or "buy").lower()
    try:
        limit_price = float(order.get("price") or 0)
        qty = float(order.get("qty") or 0)
    except (TypeError, ValueError):
        return OrderFillFailure("invalid_order", "invalid order price or quantity", {})

    if limit_price <= 0 or qty <= 0:
        return OrderFillFailure("invalid_order", "invalid order price or quantity", {})

    if side == "sell":
        held = available_shares(prior_orders, market=market, ticker=ticker)
        if held + 1e-9 < qty:
            return OrderFillFailure(
                "insufficient_shares",
                f"insufficient shares to sell (held {held:.4g}, requested {qty:.4g})",
                {"held": held, "requested": qty, "ticker": ticker},
            )

    scheduled = _parse_date(order.get("order_time"))
    created = _parse_date(order.get("created_at")) or date.today().isoformat()
    if scheduled:
        bar, bars = await _resolve_scheduled_fill_bar(
            order,
            kline_store=kline_store,
            ticker=ticker,
            market=market,
            scheduled=scheduled,
        )
        if not bars and bar is None:
            return OrderFillFailure(
                "no_kline_data",
                f"no kline data available for {ticker}",
                {"ticker": ticker},
            )
        if bar is None:
            return OrderFillFailure(
                "no_trading_bar",
                f"no trading bar for {ticker} on {scheduled}",
                {"ticker": ticker, "date": scheduled},
            )
        if not price_within_daily_range(limit_price, bar["low"], bar["high"]):
            return OrderFillFailure(
                "price_out_of_range",
                (
                    f"limit price {limit_price:.4f} is outside the {scheduled} range "
                    f"[{bar['low']:.4f}, {bar['high']:.4f}] (open {bar['open']:.4f})"
                ),
                {
                    "price": limit_price,
                    "date": scheduled,
                    "low": bar["low"],
                    "high": bar["high"],
                    "open": bar["open"],
                    "ticker": ticker,
                },
            )
        if side == "buy":
            cash_failure = _buy_cash_failure(
                prior_orders=prior_orders,
                market=market,
                initial_capital=initial_capital,
                fill_price=limit_price,
                qty=qty,
                fill_date=bar["date"],
            )
            if cash_failure is not None:
                return cash_failure
        return None

    bars = await _fetch_order_kline_bars(
        kline_store,
        ticker=ticker,
        market=market,
        after_date=created,
    )
    if not bars:
        return OrderFillFailure(
            "no_kline_data",
            f"no kline data available for {ticker}",
            {"ticker": ticker},
        )

    bar = _next_trading_day(bars, created)
    if bar is None:
        return OrderFillFailure(
            "no_trading_day",
            f"no trading day after {created} for {ticker}",
            {"ticker": ticker, "date": created},
        )
    if side == "buy":
        cash_failure = _buy_cash_failure(
            prior_orders=prior_orders,
            market=market,
            initial_capital=initial_capital,
            fill_price=bar["open"],
            qty=qty,
            fill_date=bar["date"],
        )
        if cash_failure is not None:
            return cash_failure
    return None


async def explain_order_fill_failure(
    order: dict[str, Any],
    *,
    kline_store: KlineStore,
    prior_orders: list[dict[str, Any]],
    initial_capital: float = 0.0,
) -> Optional[str]:
    status = str(order.get("order_status") or "")
    if status not in {"pending", "rejected"}:
        return None
    failure = await evaluate_order_fill_failure(
        order,
        kline_store=kline_store,
        prior_orders=prior_orders,
        initial_capital=initial_capital,
    )
    return failure.message if failure is not None else None


async def try_fill_order(
    order: dict[str, Any],
    *,
    kline_store: KlineStore,
    prior_orders: list[dict[str, Any]],
    initial_capital: float = 0.0,
) -> dict[str, Any]:
    if str(order.get("order_status")) != "pending":
        return order

    ticker = str(order.get("ticker") or "")
    market = str(order.get("market") or "")
    side = str(order.get("order_side") or "buy").lower()
    try:
        limit_price = float(order.get("price") or 0)
        qty = float(order.get("qty") or 0)
    except (TypeError, ValueError):
        return {**order, "order_status": "rejected", "updated_at": _utc_now_iso()}

    if limit_price <= 0 or qty <= 0:
        return {**order, "order_status": "rejected", "updated_at": _utc_now_iso()}

    if side == "sell" and available_shares(prior_orders, market=market, ticker=ticker) + 1e-9 < qty:
        return {**order, "order_status": "rejected", "updated_at": _utc_now_iso()}

    scheduled = _parse_date(order.get("order_time"))
    created = _parse_date(order.get("created_at")) or date.today().isoformat()
    if scheduled:
        bar, bars = await _resolve_scheduled_fill_bar(
            order,
            kline_store=kline_store,
            ticker=ticker,
            market=market,
            scheduled=scheduled,
        )
        if bar is None:
            return order
        if not price_within_daily_range(limit_price, bar["low"], bar["high"]):
            return order
        fill_price = limit_price
        fill_date = bar["date"]
    else:
        bars = await _fetch_order_kline_bars(
            kline_store,
            ticker=ticker,
            market=market,
            after_date=created,
        )
        if not bars:
            return order
        bar = _next_trading_day(bars, created)
        if bar is None:
            return order
        fill_price = bar["open"]
        fill_date = bar["date"]

    if side == "buy":
        cash_failure = _buy_cash_failure(
            prior_orders=prior_orders,
            market=market,
            initial_capital=initial_capital,
            fill_price=fill_price,
            qty=qty,
            fill_date=fill_date,
        )
        if cash_failure is not None:
            return {**order, "order_status": "rejected", "updated_at": _utc_now_iso()}

    return {
        **order,
        "order_status": "filled",
        "fill_price": fill_price,
        "fill_time": f"{fill_date}T00:00:00+00:00",
        "updated_at": _utc_now_iso(),
    }


async def process_pending_orders(
    orders: list[dict[str, Any]],
    *,
    kline_store: KlineStore,
    initial_capital_by_market: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    for index, order in enumerate(sorted(orders, key=lambda row: str(row.get("created_at") or ""))):
        if str(order.get("order_status")) != "pending":
            updated.append(order)
            continue
        market = str(order.get("market") or "")
        filled = await try_fill_order(
            order,
            kline_store=kline_store,
            prior_orders=updated,
            initial_capital=resolve_market_initial_capital(initial_capital_by_market, market),
        )
        updated.append(filled)
    return updated


def aggregate_positions(orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple[str, str], dict[str, Any]] = {}
    for order in sorted(orders, key=lambda row: str(row.get("fill_time") or row.get("created_at") or "")):
        if str(order.get("order_status")) != "filled":
            continue
        market = str(order.get("market") or "")
        ticker = str(order.get("ticker") or "")
        if not market or not ticker:
            continue
        key = (market, ticker)
        bucket = buckets.setdefault(
            key,
            {
                "ticker": ticker,
                "market": market,
                "shares": 0.0,
                "cost_basis": 0.0,
                "open_date": None,
            },
        )
        qty = float(order.get("qty") or 0)
        fill_price = float(order.get("fill_price") or order.get("price") or 0)
        fill_date = _parse_date(order.get("fill_time") or order.get("order_time") or order.get("created_at"))
        side = str(order.get("order_side") or "buy").lower()
        if side == "buy":
            if bucket["shares"] <= 0 and fill_date:
                bucket["open_date"] = fill_date
            bucket["cost_basis"] += fill_price * qty
            bucket["shares"] += qty
        elif side == "sell":
            if bucket["shares"] <= 0:
                continue
            avg_cost = bucket["cost_basis"] / bucket["shares"] if bucket["shares"] > 0 else 0.0
            sell_qty = min(qty, bucket["shares"])
            bucket["shares"] -= sell_qty
            bucket["cost_basis"] -= avg_cost * sell_qty
            if bucket["shares"] <= 1e-9:
                bucket["shares"] = 0.0
                bucket["cost_basis"] = 0.0
                bucket["open_date"] = None

    positions: list[dict[str, Any]] = []
    for bucket in buckets.values():
        shares = float(bucket["shares"])
        if shares <= 0:
            continue
        cost_basis = float(bucket["cost_basis"])
        positions.append(
            {
                "ticker": bucket["ticker"],
                "market": bucket["market"],
                "shares": shares,
                "cost": cost_basis / shares if shares > 0 else 0.0,
                "cost_basis": cost_basis,
                "open_date": bucket.get("open_date"),
            }
        )
    return positions


def _normalized_order_market(order: dict[str, Any]) -> str:
    raw = str(order.get("market") or "").strip().lower()
    return normalize_market_code(raw) or raw


def market_filled_orders(orders: list[dict[str, Any]], *, market: str) -> list[dict[str, Any]]:
    target = normalize_market_code(market) or market
    filled: list[tuple[str, str, dict[str, Any]]] = []
    for order in orders:
        if str(order.get("order_status")) != "filled":
            continue
        if _normalized_order_market(order) != target:
            continue
        fill_date = _parse_date(order.get("fill_time") or order.get("order_time") or order.get("created_at"))
        if not fill_date:
            continue
        filled.append((fill_date, str(order.get("created_at") or ""), order))
    filled.sort(key=lambda item: (item[0], item[1]))
    return [order for _, _, order in filled]


def market_tickers_from_orders(orders: list[dict[str, Any]], *, market: str) -> set[str]:
    tickers: set[str] = set()
    for order in market_filled_orders(orders, market=market):
        ticker = str(order.get("ticker") or "").strip()
        if ticker:
            tickers.add(ticker)
    return tickers


def aggregate_positions_bounded(
    orders: list[dict[str, Any]],
    *,
    capital_by_market: dict[str, Any] | None,
    as_of_date: str | None = None,
) -> list[dict[str, Any]]:
    as_of = as_of_date or date.today().isoformat()
    markets = sorted(
        {
            _normalized_order_market(order)
            for order in orders
            if str(order.get("order_status")) == "filled" and order.get("market")
        }
    )
    positions: list[dict[str, Any]] = []
    for market in markets:
        if not market:
            continue
        initial_capital = resolve_market_initial_capital(capital_by_market, market)
        cash = float(initial_capital)
        buckets: dict[str, dict[str, Any]] = {}
        for order in market_filled_orders(orders, market=market):
            fill_date = _parse_date(order.get("fill_time") or order.get("order_time") or order.get("created_at"))
            if not fill_date or fill_date > as_of:
                break
            ticker = str(order.get("ticker") or "")
            qty = float(order.get("qty") or 0)
            fill_price = float(order.get("fill_price") or order.get("price") or 0)
            side = str(order.get("order_side") or "buy").lower()
            if not ticker or qty <= 0 or fill_price <= 0:
                continue
            if side == "buy":
                cost = fill_price * qty
                if cost > cash + 1e-9:
                    continue
                cash -= cost
                bucket = buckets.setdefault(
                    ticker,
                    {
                        "ticker": ticker,
                        "market": market,
                        "shares": 0.0,
                        "cost_basis": 0.0,
                        "open_date": None,
                    },
                )
                if bucket["shares"] <= 0 and fill_date:
                    bucket["open_date"] = fill_date
                bucket["cost_basis"] += cost
                bucket["shares"] += qty
            elif side == "sell":
                bucket = buckets.get(ticker)
                if bucket is None or float(bucket["shares"]) <= 0:
                    continue
                avg_cost = float(bucket["cost_basis"]) / float(bucket["shares"])
                sell_qty = min(qty, float(bucket["shares"]))
                bucket["shares"] = float(bucket["shares"]) - sell_qty
                bucket["cost_basis"] = float(bucket["cost_basis"]) - avg_cost * sell_qty
                cash += fill_price * sell_qty
                if float(bucket["shares"]) <= 1e-9:
                    buckets.pop(ticker, None)
        for bucket in buckets.values():
            shares = float(bucket["shares"])
            if shares <= 0:
                continue
            cost_basis = float(bucket["cost_basis"])
            positions.append(
                {
                    "ticker": bucket["ticker"],
                    "market": bucket["market"],
                    "shares": shares,
                    "cost": cost_basis / shares if shares > 0 else 0.0,
                    "cost_basis": cost_basis,
                    "open_date": bucket.get("open_date"),
                }
            )
    return positions


def _apply_filled_order(
    cash: float,
    positions: dict[str, float],
    order: dict[str, Any],
) -> tuple[float, dict[str, float]]:
    ticker = str(order.get("ticker") or "")
    qty = float(order.get("qty") or 0)
    fill_price = float(order.get("fill_price") or order.get("price") or 0)
    side = str(order.get("order_side") or "buy").lower()
    if not ticker or qty <= 0 or fill_price <= 0:
        return cash, positions
    if side == "buy":
        cost = fill_price * qty
        if cost > cash + 1e-9:
            return cash, positions
        cash -= cost
        positions[ticker] = positions.get(ticker, 0.0) + qty
    elif side == "sell":
        held = positions.get(ticker, 0.0)
        sell_qty = min(qty, held)
        if sell_qty <= 0:
            return cash, positions
        cash += fill_price * sell_qty
        remaining = held - sell_qty
        if remaining <= 1e-9:
            positions.pop(ticker, None)
        else:
            positions[ticker] = remaining
    return cash, positions


def sanitize_invalid_filled_orders(
    orders: list[dict[str, Any]],
    *,
    capital_by_market: dict[str, Any] | None,
) -> tuple[list[dict[str, Any]], bool]:
    if not orders:
        return orders, False

    by_id: dict[str, dict[str, Any]] = {}
    for order in orders:
        if not isinstance(order, dict):
            continue
        order_id = str(order.get("id") or "")
        if not order_id:
            continue
        by_id[order_id] = dict(order)

    market_state: dict[str, tuple[float, dict[str, float]]] = {}
    filled_candidates: list[tuple[str, str, str, str]] = []
    for order_id, order in by_id.items():
        if str(order.get("order_status")) != "filled":
            continue
        fill_date = _parse_date(order.get("fill_time") or order.get("order_time") or order.get("created_at"))
        if not fill_date:
            continue
        filled_candidates.append(
            (fill_date, str(order.get("created_at") or ""), _normalized_order_market(order), order_id)
        )
    filled_candidates.sort()

    changed = False
    removed_ids: set[str] = set()
    for _fill_date, _created, market, order_id in filled_candidates:
        order = by_id[order_id]
        if str(order.get("order_status")) != "filled":
            continue

        cash, positions = market_state.setdefault(
            market,
            (float(resolve_market_initial_capital(capital_by_market, market)), {}),
        )
        ticker = str(order.get("ticker") or "")
        try:
            qty = float(order.get("qty") or 0)
            fill_price = float(order.get("fill_price") or order.get("price") or 0)
        except (TypeError, ValueError):
            qty = 0.0
            fill_price = 0.0
        side = str(order.get("order_side") or "buy").lower()
        invalid = False

        if not ticker or qty <= 0 or fill_price <= 0:
            invalid = True
        elif side == "buy":
            cost = fill_price * qty
            if cost > cash + 1e-9:
                invalid = True
            else:
                cash -= cost
                positions[ticker] = positions.get(ticker, 0.0) + qty
        elif side == "sell":
            held = positions.get(ticker, 0.0)
            sell_qty = min(qty, held)
            if sell_qty + 1e-9 < qty or sell_qty <= 0:
                invalid = True
            else:
                remaining = held - sell_qty
                if remaining <= 1e-9:
                    positions.pop(ticker, None)
                else:
                    positions[ticker] = remaining
                cash += fill_price * sell_qty
        else:
            invalid = True

        if invalid:
            removed_ids.add(order_id)
            changed = True
            continue

        market_state[market] = (cash, positions)

    if not changed:
        return orders, False

    rebuilt: list[dict[str, Any]] = []
    for order in orders:
        if not isinstance(order, dict):
            rebuilt.append(order)
            continue
        order_id = str(order.get("id") or "")
        if str(order.get("order_status") or "") == "rejected":
            changed = True
            continue
        if order_id and order_id in removed_ids:
            continue
        rebuilt.append(order)
    return rebuilt, changed


def _buy_cash_failure(
    *,
    prior_orders: list[dict[str, Any]],
    market: str,
    initial_capital: float,
    fill_price: float,
    qty: float,
    fill_date: str,
) -> Optional[OrderFillFailure]:
    required = fill_price * qty
    if required <= 0:
        return None
    cash, _ = replay_market_balance(
        prior_orders,
        market=market,
        initial_capital=initial_capital,
        as_of_date=fill_date,
    )
    if required <= cash + 1e-9:
        return None
    return OrderFillFailure(
        "insufficient_cash",
        f"insufficient cash (available {cash:.4g}, required {required:.4g})",
        {"available": cash, "required": required, "market": market},
    )


def replay_market_balance(
    orders: list[dict[str, Any]],
    *,
    market: str,
    initial_capital: float,
    as_of_date: str,
) -> tuple[float, dict[str, float]]:
    cash = float(initial_capital)
    positions: dict[str, float] = {}
    for order in market_filled_orders(orders, market=market):
        fill_date = _parse_date(order.get("fill_time") or order.get("order_time") or order.get("created_at"))
        if not fill_date or fill_date > as_of_date:
            break
        cash, positions = _apply_filled_order(cash, positions, order)
    return cash, positions
