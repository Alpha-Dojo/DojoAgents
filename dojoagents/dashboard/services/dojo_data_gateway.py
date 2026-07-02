from __future__ import annotations
import asyncio
import inspect
from dataclasses import dataclass
from typing import Any, Generic, TypeVar
import pandas as pd
import httpx

from dojoagents.dashboard.schemas.freshness import DataSource

T = TypeVar("T")


class GatewayError(RuntimeError):
    pass


class GatewayBadResponseError(GatewayError):
    pass


class GatewayTimeoutError(GatewayError):
    pass


class GatewayUnavailableError(GatewayError):
    pass


@dataclass(frozen=True)
class GatewayResult(Generic[T]):
    data: T
    as_of: str | None
    source: DataSource
    stale: bool


def _canonical_symbol(symbol: str) -> str:
    return symbol.strip().upper()


def _payload_mapping(payload: Any, operation: str) -> dict[str, Any]:
    if isinstance(payload, dict):
        return payload
    model_dump = getattr(payload, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        if isinstance(dumped, dict):
            return dumped
    legacy_dict = getattr(payload, "dict", None)
    if callable(legacy_dict):
        dumped = legacy_dict()
        if isinstance(dumped, dict):
            return dumped
    raise GatewayBadResponseError(f"{operation}: upstream response is not an object")


def _metadata(payload: dict[str, Any]) -> tuple[str | None, DataSource, bool]:
    source_aliases: dict[str, DataSource] = {
        "local": "sdk_snapshot",
        "remote": "sdk_online",
        "sdk_online": "sdk_online",
        "sdk_snapshot": "sdk_snapshot",
        "dashboard_cache": "dashboard_cache",
        "computed": "computed",
    }
    source = source_aliases.get(str(payload.get("source") or "remote"), "sdk_online")
    as_of = payload.get("as_of")
    return (str(as_of) if as_of is not None else None, source, bool(payload.get("stale", False)))


def _map_market_back(data: Any) -> Any:
    if isinstance(data, list):
        for item in data:
            _map_market_back(item)
    elif isinstance(data, dict):
        if data.get("market") in ["cn", "zh"]:
            data["market"] = "sh"
        for value in data.values():
            if isinstance(value, (dict, list)):
                _map_market_back(value)
    return data


def _list_result(payload: Any, operation: str, *keys: str) -> GatewayResult[list[Any]]:
    if isinstance(payload, list):
        normalized = [row.model_dump() if hasattr(row, "model_dump") else row for row in payload]
        return GatewayResult(_map_market_back(normalized), None, "sdk_snapshot", False)
    mapping = _payload_mapping(payload, operation)
    rows: Any = None
    for key in keys:
        if key in mapping:
            rows = mapping[key]
            break
    if rows is None:
        rows = mapping.get("data")
    if not isinstance(rows, list):
        raise GatewayBadResponseError(f"{operation}: upstream rows are not a list")
    as_of, source, stale = _metadata(mapping)
    normalized = [row.model_dump() if hasattr(row, "model_dump") else row for row in rows]
    return GatewayResult(_map_market_back(normalized), as_of, source, stale)


def _df_result(df: "pd.DataFrame") -> GatewayResult["pd.DataFrame"]:
    if not df.empty and "market" in df.columns:
        df["market"] = df["market"].replace({"cn": "sh", "zh": "sh"})
    return GatewayResult(df, None, "sdk_snapshot", False)


def _filter_klines_df(df: "pd.DataFrame", symbols: list[str]) -> "pd.DataFrame":
    if df.empty or not symbols:
        return df.iloc[0:0].copy()
    canonical = [_canonical_symbol(symbol) for symbol in symbols]
    if "symbol" in df.columns:
        normalized = df.copy()
        normalized["symbol"] = normalized["symbol"].astype(str).str.strip().str.upper()
        return normalized[normalized["symbol"].isin(canonical)].copy()
    available = {_canonical_symbol(str(index)) for index in df.index}
    selected = [symbol for symbol in canonical if symbol in available]
    if not selected:
        return df.iloc[0:0].copy()
    return df.loc[selected].copy()


def _symbols_in_klines_df(df: "pd.DataFrame") -> set[str]:
    if df.empty:
        return set()
    if "symbol" in df.columns:
        return set(df["symbol"].astype(str).str.strip().str.upper())
    return {_canonical_symbol(str(index)) for index in df.index.unique()}


class DojoDataGateway:
    def __init__(self, client: Any) -> None:
        self.client = client

    async def _call(self, operation: str, awaitable: Any) -> Any:
        try:
            return await awaitable
        except (asyncio.TimeoutError, TimeoutError, httpx.TimeoutException) as exc:
            raise GatewayTimeoutError(f"{operation}: upstream request timed out") from exc
        except (ConnectionError, httpx.NetworkError) as exc:
            raise GatewayUnavailableError(f"{operation}: upstream source is unavailable") from exc
        except GatewayError:
            raise
        except Exception as exc:
            raise GatewayError(f"{operation}: upstream request failed") from exc

    async def stocks(self, *, market: str | None = None) -> GatewayResult[list[dict[str, Any]]]:
        kwargs = {"market": market} if market is not None else {}
        payload = await self._call("stocks", self.client.stocks.get_ystock_info(**kwargs))
        return _list_result(payload, "stocks", "stocks")

    async def stock_profile(self, market: str, symbol: str) -> GatewayResult[dict[str, Any] | None]:
        del market
        payload = await self._call(
            "stock_profile",
            self.client.stocks.get_info(symbol=_canonical_symbol(symbol)),
        )
        mapping = _payload_mapping(payload, "stock_profile")
        profile = mapping.get("info")
        if profile is None:
            profile = {key: value for key, value in mapping.items() if key not in {"as_of", "source", "stale"}}
        if profile is not None and not isinstance(profile, dict):
            raise GatewayBadResponseError("stock_profile: upstream profile is not an object")
        as_of, source, stale = _metadata(mapping)
        return GatewayResult(_map_market_back(profile), as_of, source, stale)

    async def stock_quotes(self, market: str, symbols: list[str]) -> GatewayResult[list[dict[str, Any]]]:
        del market
        canonical = [_canonical_symbol(symbol) for symbol in symbols]
        payload = await self._call("stock_quotes", self.client.stocks.get_quote(symbols=canonical))
        return _list_result(payload, "stock_quotes", "quotes")

    async def stock_klines(
        self,
        symbols: list[str],
        **window: Any,
    ) -> GatewayResult["pd.DataFrame"]:
        kwargs = {key: value for key, value in window.items() if value is not None}
        canonical_symbols = [_canonical_symbol(symbol) for symbol in symbols]
        if kwargs.get("start_time") or kwargs.get("end_time"):
            return await self._fetch_klines_per_symbol(canonical_symbols, kwargs)

        bulk_df = pd.DataFrame()
        try:
            payload_df = await self._call(
                "stock_klines",
                self.client.stocks.get_all_klines_with_df(),
            )
            bulk_df = _filter_klines_df(payload_df, canonical_symbols)
        except Exception:
            bulk_df = pd.DataFrame()

        found_symbols = _symbols_in_klines_df(bulk_df)
        missing_symbols = [symbol for symbol in canonical_symbols if symbol not in found_symbols]
        if not missing_symbols:
            return _df_result(bulk_df)

        extra_rows = await self._fetch_kline_rows(missing_symbols, kwargs)
        if bulk_df.empty and not extra_rows:
            return _df_result(pd.DataFrame())

        frames = [frame for frame in (bulk_df, pd.DataFrame(extra_rows)) if not frame.empty]
        merged = frames[0] if len(frames) == 1 else pd.concat(frames, ignore_index=True)
        return _df_result(merged)

    async def _fetch_kline_rows(self, symbols: list[str], kwargs: dict[str, Any]) -> list[dict[str, Any]]:
        async def fetch_one(symbol: str) -> list[dict[str, Any]]:
            payload = await self._call(
                "stock_klines",
                self.client.stocks.get_kline(symbol=symbol, **kwargs),
            )
            result = _list_result(payload, "stock_klines", "klines")
            return result.data

        results = await asyncio.gather(*(fetch_one(symbol) for symbol in symbols), return_exceptions=True)
        rows: list[dict[str, Any]] = []
        for result in results:
            if isinstance(result, Exception):
                continue
            rows.extend(result)
        return rows

    async def _fetch_klines_per_symbol(
        self,
        symbols: list[str],
        kwargs: dict[str, Any],
    ) -> GatewayResult["pd.DataFrame"]:
        rows = await self._fetch_kline_rows(symbols, kwargs)
        return _df_result(pd.DataFrame(rows))

    async def stock_all_klines(
        self,
        *,
        symbols: list[str] | None = None,
    ) -> GatewayResult["pd.DataFrame"]:
        try:
            import pandas as pd

            payload_df = await self._call(
                "stock_all_klines",
                self.client.stocks.get_all_klines_with_df(),
            )
            if symbols is not None:
                payload_df = _filter_klines_df(payload_df, symbols)
            return _df_result(payload_df)
        except Exception:
            pass

        kwargs: dict[str, Any] = {}
        if symbols is not None:
            kwargs["symbols"] = [_canonical_symbol(symbol) for symbol in symbols]
        payload = await self._call(
            "stock_all_klines",
            self.client.stocks.get_all_klines(**kwargs),
        )
        res = _list_result(payload, "stock_all_klines", "klines")

        return GatewayResult(pd.DataFrame(res.data), res.as_of, res.source, res.stale)

    async def stock_events(
        self,
        market: str,
        symbol: str,
        *,
        page: int | None = None,
        page_size: int | None = None,
    ) -> GatewayResult[list[dict[str, Any]]]:
        del market
        kwargs = {"symbol": _canonical_symbol(symbol), "page": page, "page_size": page_size}
        payload = await self._call(
            "stock_events",
            self.client.stocks.get_event_remind(**{key: value for key, value in kwargs.items() if value is not None}),
        )
        return _list_result(payload, "stock_events", "data")

    async def stock_news(
        self,
        market: str,
        symbol: str,
        *,
        page: int | None = None,
        page_size: int | None = None,
    ) -> GatewayResult[list[dict[str, Any]]]:
        del market
        kwargs = {"symbol": _canonical_symbol(symbol), "page": page, "page_size": page_size}
        payload = await self._call(
            "stock_news",
            self.client.stocks.get_news(**{key: value for key, value in kwargs.items() if value is not None}),
        )
        return _list_result(payload, "stock_news", "news")

    async def stock_financial_indicators(
        self,
        market: str,
        symbol: str,
        *,
        report_type: str | None = None,
        end_date: str | None = None,
        limit: int | None = None,
    ) -> GatewayResult[list[dict[str, Any]]]:
        del market
        kwargs = {
            "symbol": _canonical_symbol(symbol),
            "report_type": report_type,
            "end_date": end_date,
            "limit": limit,
        }
        payload = await self._call(
            "stock_financial_indicators",
            self.client.stocks.get_fin_indicators(**{key: value for key, value in kwargs.items() if value is not None}),
        )
        return _list_result(payload, "stock_financial_indicators", "data")

    async def stock_income(
        self,
        market: str,
        symbol: str,
        *,
        page: int | None = None,
        page_size: int | None = None,
    ) -> GatewayResult[list[dict[str, Any]]]:
        del market
        kwargs = {"symbol": _canonical_symbol(symbol), "page": page, "page_size": page_size}
        payload = await self._call(
            "stock_income",
            self.client.stocks.get_main_income(**{key: value for key, value in kwargs.items() if value is not None}),
        )
        return _list_result(payload, "stock_income", "data")

    async def sector_taxonomy(self, **filters: Any) -> GatewayResult[list[dict[str, Any]]]:
        payload = await self._call(
            "sector_taxonomy",
            self.client.sectors.get_info(**{key: value for key, value in filters.items() if value is not None}),
        )
        return _list_result(payload, "sector_taxonomy", "sectors")

    async def sector_relations(self, **filters: Any) -> GatewayResult[list[dict[str, Any]]]:
        payload = await self._call(
            "sector_relations",
            self.client.sectors.get_symbol_relations(**{key: value for key, value in filters.items() if value is not None}),
        )
        return _list_result(payload, "sector_relations", "relations", "data")

    async def benchmark_klines(self, symbol: str, **window: Any) -> GatewayResult[list[Any]]:
        kwargs = {"symbol": symbol.strip(), **window}
        payload = await self._call(
            "benchmark_klines",
            self.client.benchmark.get_kline(**{key: value for key, value in kwargs.items() if value is not None}),
        )
        return _list_result(payload, "benchmark_klines", "klines")

    async def benchmark_catalog(self) -> GatewayResult[list[dict[str, Any]]]:
        payload = await self._call(
            "benchmark_catalog",
            self.client.benchmark.get_catalog(),
        )
        return _list_result(payload, "benchmark_catalog", "data")

    async def forex(self, symbol: str, **window: Any) -> GatewayResult[list[Any]]:
        kwargs = {"symbol": _canonical_symbol(symbol), **window}
        resource = self.client.forex
        get_kline = getattr(resource, "get_kline", None)
        if not inspect.iscoroutinefunction(get_kline):
            get_kline = resource.kline
        payload = await self._call(
            "forex",
            get_kline(**{key: value for key, value in kwargs.items() if value is not None}),
        )
        return _list_result(payload, "forex", "klines")
