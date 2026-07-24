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


class DojoDataGateway:
    def __init__(self, client: Any) -> None:
        self.client = client
        self._kline_symbol_index: dict[str, pd.DataFrame] | None = None
        self._kline_index_lock = asyncio.Lock()

    def invalidate_kline_index(self) -> None:
        self._kline_symbol_index = None

    @property
    def kline_index_ready(self) -> bool:
        return self._kline_symbol_index is not None

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
        canonical_symbols = [_canonical_symbol(symbol) for symbol in symbols]
        kwargs = {key: value for key, value in window.items() if value is not None}
        if kwargs.get("start_time") or kwargs.get("end_time"):
            return await self._fetch_klines_per_symbol(canonical_symbols, kwargs)

        await self.warm_kline_index()
        index = self._kline_symbol_index or {}
        frames: list[pd.DataFrame] = []
        missing: list[str] = []
        limit = int(kwargs.get("limit") or 0)
        for symbol in canonical_symbols:
            frame = index.get(symbol)
            if frame is None or frame.empty:
                missing.append(symbol)
                continue
            frames.append(frame.tail(limit) if limit > 0 else frame)

        if missing:
            fetched = await self._fetch_klines_per_symbol(missing, kwargs)
            if not fetched.data.empty:
                frames.append(fetched.data)

        if not frames:
            return _df_result(pd.DataFrame())
        return _df_result(pd.concat(frames, ignore_index=True))

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
            payload_df = await self._call(
                "stock_all_klines",
                self.client.stocks.get_all_klines_with_df(),
            )
            payload_df = self._normalize_kline_frame(payload_df)
            if symbols is not None:
                canonical_symbols = {_canonical_symbol(symbol) for symbol in symbols}
                payload_df = payload_df[payload_df["symbol"].isin(canonical_symbols)]
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

    @staticmethod
    def _normalize_kline_frame(payload: Any) -> pd.DataFrame:
        if isinstance(payload, pd.DataFrame):
            frame = payload.copy()
        else:
            frame = pd.DataFrame(payload or [])
        if frame.empty:
            return frame
        if "symbol" not in frame.columns:
            if frame.index.name == "symbol":
                frame = frame.reset_index()
            else:
                raise GatewayBadResponseError("stock_all_klines: upstream rows have no symbol")
        frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper()
        return frame[frame["symbol"] != ""].reset_index(drop=True)

    async def warm_kline_index(self) -> None:
        if self._kline_symbol_index is not None:
            return
        async with self._kline_index_lock:
            if self._kline_symbol_index is not None:
                return
            result = await self.stock_all_klines()
            frame = self._normalize_kline_frame(result.data)
            if frame.empty:
                self._kline_symbol_index = {}
                return
            self._kline_symbol_index = {symbol: rows.reset_index(drop=True) for symbol, rows in frame.groupby("symbol", sort=False)}

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
