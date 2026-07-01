from dojoagents.logging import LOGGER
import asyncio
from datetime import date
from typing import Dict, List, Optional, Tuple

from dojo.client.async_client import AsyncDojo
from dojoagents.dashboard.services.dojo_data_gateway import DojoDataGateway

from dojoagents.dashboard.services.fin_currency_conversion import (
    convert_fin_row_amounts,
    quarter_rate_window,
    required_forex_symbols,
    rows_need_currency_conversion,
)
from dojoagents.dashboard.services.fin_indicators_utils import extract_report_date
from dojoagents.dashboard.services.kline_bar_utils import extract_bar_time, merge_rows

MAX_FOREX_FETCH_LIMIT = 600


class ForexStore:
    def __init__(
        self,
        client: AsyncDojo,
    ) -> None:
        gateway_method = getattr(type(client), "forex", None)
        self.gateway = client if callable(gateway_method) else DojoDataGateway(client)
        self._cache: Dict[str, List[dict]] = {}
        self._locks: Dict[str, asyncio.Lock] = {}

    def _lock_for(self, symbol: str) -> asyncio.Lock:
        if symbol not in self._locks:
            self._locks[symbol] = asyncio.Lock()
        return self._locks[symbol]

    @staticmethod
    def _average_close(bars: List[dict]) -> Optional[float]:
        closes: List[float] = []
        for bar in bars:
            close = bar.get("close")
            if close is None:
                continue
            try:
                value = float(close)
            except (TypeError, ValueError):
                continue
            if value > 0:
                closes.append(value)
        if not closes:
            return None
        return sum(closes) / len(closes)

    @staticmethod
    def _fetch_limit_for_start(earliest_start: str) -> int:
        try:
            start_date = date.fromisoformat(earliest_start[:10])
        except ValueError:
            return 252
        span_days = max(1, (date.today() - start_date).days + 30)
        estimated_bars = int(span_days * 5 / 7) + 30
        return min(max(estimated_bars, 90), MAX_FOREX_FETCH_LIMIT)

    async def _fetch_remote(
        self,
        symbol: str,
        limit: int,
        *,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> List[dict]:
        try:
            kwargs: dict[str, object] = {"limit": limit}
            if start_time:
                kwargs["start_time"] = start_time
            if end_time:
                kwargs["end_time"] = end_time
            payload = await self.gateway.forex(symbol, **kwargs)
        except Exception as e:
            LOGGER.info(f"[ForexStore] fetch error for {symbol}: {e}")
            payload = []
        data = payload.data if hasattr(payload, "data") else []
        if not isinstance(data, list):
            return []
        return [row for row in data if isinstance(row, dict)]

    def _has_bars_for_windows(self, symbol: str, windows: List[Tuple[str, str]]) -> bool:
        bars = self._cache.get(symbol, [])
        if not bars:
            return False
        dates = {extract_bar_time(b) for b in bars if extract_bar_time(b)}
        if not dates:
            return False
        for start, end in windows:
            if not any(start <= d <= end for d in dates):
                return False
        return True

    async def ensure_symbols_for_windows(
        self,
        symbols: List[str],
        windows: List[Tuple[str, str]],
    ) -> None:
        if not symbols or not windows:
            return

        earliest_start = min(start for start, _ in windows)
        latest_end = max(end for _, end in windows)
        limit = self._fetch_limit_for_start(earliest_start)

        async def _ensure(symbol: str):
            if self._has_bars_for_windows(symbol, windows):
                return
            remote = await self._fetch_remote(
                symbol,
                limit,
                start_time=earliest_start,
                end_time=latest_end,
            )
            if remote:
                existing = self._cache.get(symbol, [])
                self._cache[symbol] = merge_rows(existing, remote)

        await asyncio.gather(*(_ensure(symbol) for symbol in symbols))

    def average_close_for_range(self, symbol: str, start: str, end: str) -> Optional[float]:
        bars = self._cache.get(symbol, [])
        in_range = [b for b in bars if start <= extract_bar_time(b) <= end]
        return self._average_close(in_range)

    async def convert_fin_rows_to_market(self, rows: List[dict], market: str) -> List[dict]:
        if not rows or not rows_need_currency_conversion(rows, market):
            return rows

        convertible_rows: List[dict] = []
        windows: List[Tuple[str, str]] = []
        for row in rows:
            window = quarter_rate_window(row)
            if window is None:
                continue
            convertible_rows.append(row)
            windows.append(window)

        if not convertible_rows:
            return rows

        symbols = required_forex_symbols(rows, market)
        await self.ensure_symbols_for_windows(symbols, windows)

        rate_cache: Dict[Tuple[str, str, str], float] = {}
        converted_by_date: Dict[str, dict] = {}

        for row in convertible_rows:
            window = quarter_rate_window(row)
            if window is None:
                continue
            start, end = window
            row_symbols = required_forex_symbols([row], market)
            pair_closes: Dict[str, float] = {}
            for symbol in row_symbols:
                cache_key = (symbol, start, end)
                if cache_key not in rate_cache:
                    avg = self.average_close_for_range(symbol, start, end)
                    if avg is not None and avg > 0:
                        rate_cache[cache_key] = avg
                close = rate_cache.get(cache_key)
                if close is not None:
                    pair_closes[symbol] = close
            report_date = extract_report_date(row)
            if report_date:
                converted_by_date[report_date] = convert_fin_row_amounts(
                    row,
                    market=market,
                    pair_closes=pair_closes,
                )

        converted: List[dict] = []
        for row in rows:
            report_date = extract_report_date(row)
            converted.append(converted_by_date.get(report_date, row))
        return converted
