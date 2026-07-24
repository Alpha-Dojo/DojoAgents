"""Typed request context owned by FinancialHarness."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Mapping


class FinancialContextError(ValueError):
    def __init__(self, field_path: str, message: str, *, code: str = "invalid_financial_context") -> None:
        self.field_path = field_path
        self.code = code
        self.message = message
        super().__init__(f"{field_path}: {message}")


@dataclass(frozen=True)
class FinancialContext:
    market: str
    symbols: tuple[str, ...]
    timeframe: str
    currency: str = "USD"
    freshness: str = "latest_available"

    def prompt_block(self) -> str:
        return (
            "Quant context:\n"
            f"- market: {self.market}\n"
            f"- symbols: {', '.join(self.symbols)}\n"
            f"- timeframe: {self.timeframe}\n"
            f"- currency: {self.currency}\n"
            f"- data freshness: {self.freshness}"
        )


class FinancialRequestContextCodec:
    markets = frozenset({"stock", "crypto", "us", "cn", "hk"})
    freshness_values = frozenset({"latest_available", "realtime", "delayed", "end_of_day"})
    _timeframe = re.compile(r"^(?:\d+[mhdwMy]|intraday|daily|weekly|monthly)$")
    _currency = re.compile(r"^[A-Z]{3}$")

    @staticmethod
    def _mapping(value: Any, path: str) -> Mapping[str, Any]:
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, Mapping):
            return value
        raise FinancialContextError(path, "must be an object")

    def decode(self, request_or_context: Any) -> FinancialContext | None:
        request_context = getattr(request_or_context, "context", request_or_context)
        legacy = getattr(request_or_context, "quant", None)
        payload: Any = None
        if isinstance(request_context, Mapping):
            payload = request_context.get("financial")
            if payload is None and "market" in request_context:
                payload = request_context
        if payload is None:
            payload = legacy
        if payload is None:
            return None
        raw = self._mapping(payload, "context.financial")

        market = str(raw.get("market") or "").strip().lower()
        if market not in self.markets:
            raise FinancialContextError(
                "context.financial.market",
                f"must be one of {', '.join(sorted(self.markets))}",
            )
        symbols_raw = raw.get("symbols")
        if not isinstance(symbols_raw, (list, tuple)):
            raise FinancialContextError("context.financial.symbols", "must be a list")
        symbols: list[str] = []
        for index, item in enumerate(symbols_raw):
            symbol = str(item or "").strip().upper()
            if not symbol:
                raise FinancialContextError(f"context.financial.symbols.{index}", "must not be blank")
            symbols.append(symbol)

        timeframe = str(raw.get("timeframe") or "").strip()
        if not self._timeframe.fullmatch(timeframe):
            raise FinancialContextError("context.financial.timeframe", "must be a duration such as 1d or a supported interval")
        currency = str(raw.get("currency") or "USD").strip().upper()
        if not self._currency.fullmatch(currency):
            raise FinancialContextError("context.financial.currency", "must be a three-letter code")
        freshness = str(raw.get("freshness", raw.get("data_freshness", "latest_available"))).strip().lower()
        if freshness not in self.freshness_values:
            raise FinancialContextError(
                "context.financial.freshness",
                f"must be one of {', '.join(sorted(self.freshness_values))}",
            )
        return FinancialContext(market, tuple(symbols), timeframe, currency, freshness)


__all__ = ["FinancialContext", "FinancialContextError", "FinancialRequestContextCodec"]
