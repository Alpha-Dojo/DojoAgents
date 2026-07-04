from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from dojoagents.agent.escalation import AgentEscalationError
from dojoagents.agent.harnesses.portfolio_eval import _position_rows_from_detail
from dojoagents.agent.harnesses.portfolio_task_intent import is_liquidation_intent
from dojoagents.dashboard.schemas.portfolio import CreatePortfolioOrderRequest, ResolvedOrderBar
from dojoagents.dashboard.services.ticker_symbol_resolution import resolve_ticker_symbol
from dojoagents.dashboard.services.kline_bar_utils import extract_bar_time, price_within_daily_range
from dojoagents.dashboard.services.kline_store import KlineStore
from dojoagents.dashboard.services.portfolio_allocation import normalize_shares
from dojoagents.dashboard.services.portfolio_kline_fetch import fetch_kline_bars_with_symbol_fallback
from dojoagents.dashboard.services.portfolio_order_execution import (
    _parse_date,
    replay_market_balance,
    resolve_market_initial_capital,
)

DEFAULT_POSITION_PCT = 0.10


def _resolved_bar_from_meta(meta: ResolvedOrderMeta) -> ResolvedOrderBar | None:
    if not meta.bar_date or meta.bar_low is None or meta.bar_high is None or meta.bar_open is None:
        return None
    try:
        low = float(meta.bar_low)
        high = float(meta.bar_high)
        open_price = float(meta.bar_open)
    except (TypeError, ValueError):
        return None
    if low <= 0 or high <= 0 or open_price <= 0:
        return None
    return ResolvedOrderBar(
        date=str(meta.bar_date)[:10],
        open=open_price,
        low=low,
        high=high,
    )


@dataclass
class ResolvedOrderMeta:
    kline_symbol: str
    market: str
    price_source: str
    time_source: str
    qty_source: str
    bar_date: str | None = None
    bar_low: float | None = None
    bar_high: float | None = None
    bar_open: float | None = None
    bar_close: float | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "kline_symbol": self.kline_symbol,
            "market": self.market,
            "price_source": self.price_source,
            "time_source": self.time_source,
            "qty_source": self.qty_source,
            "bar_date": self.bar_date,
            "bar_low": self.bar_low,
            "bar_high": self.bar_high,
            "bar_open": self.bar_open,
            "bar_close": self.bar_close,
            "notes": list(self.notes),
        }


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


def _bar_payload(row: Any) -> dict[str, float] | None:
    payload = _row_dict(row)
    bar_time = extract_bar_time(payload)[:10]
    if not bar_time:
        return None
    try:
        open_price = float(payload.get("open") or 0)
        low = float(payload.get("low") or 0)
        high = float(payload.get("high") or 0)
        close = float(payload.get("close") or open_price)
    except (TypeError, ValueError):
        return None
    if open_price <= 0 or low <= 0 or high <= 0:
        return None
    return {
        "date": bar_time,
        "open": open_price,
        "low": low,
        "high": high,
        "close": close,
    }


def _sorted_bars(bars: list[Any]) -> list[dict[str, float]]:
    parsed = [item for row in bars if (item := _bar_payload(row)) is not None]
    parsed.sort(key=lambda item: item["date"])
    return parsed


def _latest_bar(bars: list[dict[str, float]]) -> dict[str, float] | None:
    return bars[-1] if bars else None


def _find_bar_for_price(bars: list[dict[str, float]], price: float) -> dict[str, float] | None:
    matches = [
        bar
        for bar in bars
        if price_within_daily_range(price, float(bar["low"]), float(bar["high"]))
    ]
    if not matches:
        return None
    return matches[-1]


def validate_share_quantity(market: str, qty: float) -> str | None:
    if not math.isfinite(qty) or qty <= 0:
        return "share quantity must be positive"
    if market == "us":
        if abs(qty - round(qty)) > 1e-9:
            return "US share quantity must be a whole number (integer shares)"
        if qty < 1:
            return "US share quantity must be at least 1"
        return None
    rounded = int(round(qty))
    if abs(qty - rounded) > 1e-9 or rounded % 100 != 0:
        return f"{market} share quantity must be a multiple of 100"
    if qty < 100:
        return f"{market} share quantity must be at least 100"
    return None


def _default_buy_quantity(market: str, available_cash: float, price: float) -> int:
    if price <= 0 or available_cash <= 0:
        return 0
    target_value = available_cash * DEFAULT_POSITION_PCT
    return normalize_shares(market, target_value / price)


def _normalize_market_code(market: str | None) -> str:
    normalized = str(market or "").strip().lower()
    if normalized == "cn":
        return "sh"
    return normalized


def held_shares_from_detail(detail: Any, *, ticker: str, market: str | None) -> float:
    payload: dict[str, Any]
    if hasattr(detail, "model_dump"):
        payload = detail.model_dump()
    elif isinstance(detail, dict):
        payload = detail
    else:
        return 0.0
    target_ticker = ticker.strip().upper()
    target_market = _normalize_market_code(market)
    for row in _position_rows_from_detail(payload):
        row_ticker = str(row.get("ticker") or "").strip().upper()
        row_market = _normalize_market_code(str(row.get("market") or ""))
        if row_ticker != target_ticker:
            continue
        if target_market and row_market and row_market != target_market:
            continue
        return float(row.get("shares") or 0)
    return 0.0


def _sell_qty_options(*, ticker: str, market: str, held: float) -> list[str]:
    if held <= 0:
        return ["Specify exact share count (no shares currently held)"]
    if market == "us":
        half = max(1, int(round(held * 0.5)))
        three_quarter = max(1, int(round(held * 0.75)))
        full = int(round(held))
    else:
        half = normalize_shares(market, held * 0.5)
        three_quarter = normalize_shares(market, held * 0.75)
        full = normalize_shares(market, held)
    return [
        f"Sell 50% ({half:.0f} shares) of {ticker}",
        f"Sell 75% ({three_quarter:.0f} shares) of {ticker}",
        f"Sell 100% ({full:.0f} shares) of {ticker}",
        "Specify exact share count",
    ]


def _resolve_sell_quantity(
    *,
    internal_market: str,
    canonical_ticker: str,
    held: float,
    user_qty: float | None,
    raw_qty_pct: Any,
    liquidate_all: bool,
    user_message: str,
    meta: ResolvedOrderMeta,
) -> float:
    if user_qty is not None:
        qty_error = validate_share_quantity(internal_market, user_qty)
        if qty_error:
            _raise_escalation(
                "invalid_order_quantity",
                f"{qty_error} for {canonical_ticker}",
                context={
                    "ticker": canonical_ticker,
                    "market": internal_market,
                    "qty": user_qty,
                },
            )
        meta.qty_source = "user"
        return float(int(round(user_qty)) if internal_market == "us" else int(round(user_qty)))

    if raw_qty_pct is not None:
        try:
            pct = float(raw_qty_pct)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("qty_pct must be a number between 0 and 1") from exc
        if not 0 < pct <= 1:
            raise RuntimeError("qty_pct must be greater than 0 and at most 1")
        if held <= 0:
            raise RuntimeError(f"No held shares to sell for {canonical_ticker}")
        resolved = float(normalize_shares(internal_market, held * pct))
        if resolved <= 0:
            _raise_escalation(
                "invalid_order_quantity",
                f"qty_pct {pct:.0%} of held shares for {canonical_ticker} is below the minimum tradable lot",
                context={
                    "ticker": canonical_ticker,
                    "market": internal_market,
                    "held_shares": held,
                    "qty_pct": pct,
                },
            )
        meta.qty_source = "qty_pct"
        meta.notes.append(f"Defaulted quantity to {resolved:.0f} shares ({pct:.0%} of held position).")
        return resolved

    if liquidate_all or is_liquidation_intent(user_message):
        if held <= 0:
            raise RuntimeError(f"No held shares to sell for {canonical_ticker}")
        resolved = float(normalize_shares(internal_market, held) if internal_market != "us" else int(round(held)))
        meta.qty_source = "held_shares"
        meta.notes.append(f"Defaulted quantity to all held shares ({resolved:.0f}).")
        return resolved

    _raise_escalation(
        "sell_qty_unspecified",
        (
            f"Sell quantity not specified for {canonical_ticker}. "
            "Ask the user what portion to sell before placing the order."
        ),
        context={
            "ticker": canonical_ticker,
            "market": internal_market,
            "held_shares": held,
            "user_options": _sell_qty_options(
                ticker=canonical_ticker,
                market=internal_market,
                held=held,
            ),
        },
    )


def _raise_escalation(code: str, message: str, *, context: dict[str, Any] | None = None) -> None:
    user_input_codes = {
        "capital_budget_exceeded",
        "invalid_order_quantity",
        "price_not_fillable",
        "sell_qty_unspecified",
    }
    raise AgentEscalationError(
        code,
        message,
        context=context or {},
        recoverable_by_agent=code not in user_input_codes,
    )


async def _fetch_resolution_bars(
    kline_store: KlineStore,
    *,
    symbol: str,
    market: str,
    order_time: str | None,
    user_price: float | None = None,
) -> tuple[list[Any], str]:
    return await fetch_kline_bars_with_symbol_fallback(
        kline_store,
        symbol=symbol,
        market=market,
        order_time=order_time,
        user_price=user_price,
    )


def _parsed_bar_for_date(bars: list[dict[str, float]], target: str) -> dict[str, float] | None:
    for bar in bars:
        if bar["date"] == target:
            return bar
    return None


def _resolve_price_and_time(
    *,
    bars: list[dict[str, float]],
    order_time: str | None,
    price: float | None,
    ticker: str,
) -> tuple[float, str, ResolvedOrderMeta]:
    meta = ResolvedOrderMeta(
        kline_symbol="",
        market="",
        price_source="user",
        time_source="user",
        qty_source="user",
    )

    if order_time and price is not None:
        bar = _parsed_bar_for_date(bars, order_time)
        if bar is None:
            _raise_escalation(
                "no_trading_bar",
                f"no trading bar for {ticker} on {order_time}",
                context={"ticker": ticker, "date": order_time},
            )
        low = float(bar["low"])
        high = float(bar["high"])
        if not price_within_daily_range(price, low, high):
            _raise_escalation(
                "price_not_fillable",
                (
                    f"limit price {price:.4f} is outside the {order_time} range "
                    f"[{low:.4f}, {high:.4f}] (open {bar['open']:.4f})"
                ),
                context={
                    "ticker": ticker,
                    "date": order_time,
                    "price": price,
                    "low": low,
                    "high": high,
                    "open": bar["open"],
                },
            )
        meta.price_source = "user"
        meta.time_source = "user"
        meta.bar_date = order_time
        meta.bar_low = low
        meta.bar_high = high
        meta.bar_open = float(bar["open"])
        return price, order_time, meta

    if order_time and price is None:
        bar = _parsed_bar_for_date(bars, order_time)
        if bar is None:
            _raise_escalation(
                "no_trading_bar",
                f"no trading bar for {ticker} on {order_time}",
                context={"ticker": ticker, "date": order_time},
            )
        meta.price_source = "open"
        meta.time_source = "user"
        meta.bar_date = order_time
        meta.bar_low = float(bar["low"])
        meta.bar_high = float(bar["high"])
        meta.bar_open = float(bar["open"])
        meta.notes.append("Used opening price for the specified trade date.")
        return float(bar["open"]), order_time, meta

    if price is not None and not order_time:
        latest = _latest_bar(bars)
        if latest is not None and price_within_daily_range(
            price,
            float(latest["low"]),
            float(latest["high"]),
        ):
            meta.price_source = "user"
            meta.time_source = "inferred_from_latest_bar"
            meta.bar_date = latest["date"]
            meta.bar_low = float(latest["low"])
            meta.bar_high = float(latest["high"])
            meta.bar_open = float(latest["open"])
            meta.bar_close = float(latest["close"])
            meta.notes.append(
                f"Matched limit price to the latest trading day {latest['date']} (current-price semantics)."
            )
            return price, latest["date"], meta

        bar = _find_bar_for_price(bars, price)
        if bar is None:
            context: dict[str, Any] = {"ticker": ticker, "price": price}
            if latest is not None:
                context.update(
                    {
                        "latest_date": latest["date"],
                        "latest_low": latest["low"],
                        "latest_high": latest["high"],
                    }
                )
            _raise_escalation(
                "price_not_fillable",
                (
                    f"no trading day found where {ticker} traded between the limit price "
                    f"{price:.4f} and daily high/low"
                ),
                context=context,
            )
        meta.price_source = "user"
        meta.time_source = "inferred_from_price"
        meta.bar_date = bar["date"]
        meta.bar_low = bar["low"]
        meta.bar_high = bar["high"]
        meta.bar_open = bar["open"]
        meta.bar_close = bar["close"]
        meta.notes.append(f"Inferred trade date {bar['date']} from a historical daily bar.")
        return price, bar["date"], meta

    latest = _latest_bar(bars)
    if latest is None:
        _raise_escalation(
            "no_kline_data",
            f"no kline data available for {ticker}",
            context={"ticker": ticker},
        )
    meta.price_source = "close"
    meta.time_source = "latest_bar"
    meta.bar_date = latest["date"]
    meta.bar_low = latest["low"]
    meta.bar_high = latest["high"]
    meta.bar_open = latest["open"]
    meta.bar_close = latest["close"]
    meta.notes.append("Used latest daily close because no trade date or limit price was provided.")
    return float(latest["close"]), latest["date"], meta


async def resolve_portfolio_order_request(
    registry,
    service,
    portfolio_id: str,
    args: dict[str, Any],
) -> tuple[CreatePortfolioOrderRequest, ResolvedOrderMeta]:
    ticker = str(args.get("ticker") or "").strip()
    if not ticker:
        raise RuntimeError("ticker is required")

    order_side = str(args.get("order_side") or "buy").strip().lower()
    if order_side not in {"buy", "sell"}:
        raise RuntimeError("order_side must be buy or sell")

    market = str(args.get("market") or "").strip().lower() or None
    if market == "cn":
        market = "sh"

    stock_store = registry.stock_store
    kline_store = registry.kline_store
    if stock_store is None or kline_store is None:
        raise RuntimeError("financial stores are not ready")

    symbol, resolved_market = resolve_ticker_symbol(stock_store, ticker, market)
    internal_market = resolved_market or market
    if not internal_market:
        internal_market = stock_store.find_market(symbol) or stock_store.find_market(ticker)
    if not internal_market:
        raise RuntimeError(f"market not found for ticker {ticker}")

    canonical_ticker = symbol or ticker.strip().upper()
    order_time = _parse_date(args.get("order_time"))
    raw_price = args.get("price")
    raw_qty = args.get("qty")
    user_price = float(raw_price) if raw_price is not None else None
    user_qty = float(raw_qty) if raw_qty is not None else None

    bars_raw, kline_symbol = await _fetch_resolution_bars(
        kline_store,
        symbol=canonical_ticker,
        market=internal_market,
        order_time=order_time,
        user_price=user_price,
    )
    if kline_symbol:
        canonical_ticker = kline_symbol
    bars = _sorted_bars(bars_raw)
    if order_time and not bars:
        _raise_escalation(
            "no_kline_data",
            f"no kline data available for {canonical_ticker} on {order_time}",
            context={"ticker": canonical_ticker, "date": order_time},
        )
    if not order_time and not bars:
        _raise_escalation(
            "no_kline_data",
            f"no kline data available for {canonical_ticker}",
            context={"ticker": canonical_ticker},
        )

    price, trade_date, meta = _resolve_price_and_time(
        bars=bars,
        order_time=order_time,
        price=user_price,
        ticker=canonical_ticker,
    )
    meta.kline_symbol = canonical_ticker
    meta.market = internal_market

    if user_qty is not None:
        qty_error = validate_share_quantity(internal_market, user_qty)
        if qty_error:
            _raise_escalation(
                "invalid_order_quantity",
                f"{qty_error} for {canonical_ticker}",
                context={
                    "ticker": canonical_ticker,
                    "market": internal_market,
                    "qty": user_qty,
                },
            )
        resolved_qty = float(int(round(user_qty)) if internal_market == "us" else int(round(user_qty)))
        meta.qty_source = "user"
    elif order_side == "buy":
        detail = await service.get_detail(portfolio_id, include_performance=False)
        if detail is None:
            raise RuntimeError("portfolio not found")
        config = detail.config.model_dump() if detail.config is not None else {}
        capital_by_market = config.get("capital_by_market") if isinstance(config, dict) else {}
        prior_orders = [row.model_dump() for row in detail.orders]
        available, _ = replay_market_balance(
            prior_orders,
            market=internal_market,
            initial_capital=resolve_market_initial_capital(
                capital_by_market if isinstance(capital_by_market, dict) else {},
                internal_market,
            ),
            as_of_date=trade_date,
        )
        resolved_qty = float(_default_buy_quantity(internal_market, available, price))
        if resolved_qty <= 0:
            _raise_escalation(
                "invalid_order_quantity",
                (
                    f"default 10% position size for {canonical_ticker} is below the minimum tradable lot "
                    f"for market {internal_market}"
                ),
                context={
                    "ticker": canonical_ticker,
                    "market": internal_market,
                    "available_cash": available,
                    "price": price,
                    "default_position_pct": DEFAULT_POSITION_PCT,
                },
            )
        meta.qty_source = "default_10pct"
        meta.notes.append(
            f"Defaulted quantity to {resolved_qty:.0f} shares ({DEFAULT_POSITION_PCT:.0%} of available cash)."
        )
    else:
        from dojoagents.tools.process_registry import active_user_message

        detail = await service.get_detail(portfolio_id, include_performance=False)
        if detail is None:
            raise RuntimeError("portfolio not found")
        held = held_shares_from_detail(
            detail,
            ticker=canonical_ticker,
            market=internal_market,
        )
        resolved_qty = _resolve_sell_quantity(
            internal_market=internal_market,
            canonical_ticker=canonical_ticker,
            held=held,
            user_qty=None,
            raw_qty_pct=args.get("qty_pct"),
            liquidate_all=bool(args.get("liquidate_all")),
            user_message=str(args.get("user_message") or active_user_message.get() or ""),
            meta=meta,
        )

    body = CreatePortfolioOrderRequest(
        ticker=canonical_ticker,
        market=internal_market,
        order_side=order_side,
        price=price,
        qty=resolved_qty,
        order_time=trade_date,
        resolved_bar=_resolved_bar_from_meta(meta),
    )
    return body, meta
