from __future__ import annotations

import inspect
import json
import logging
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

import httpx
import pandas as pd

from dojoagents.logging import LOGGER
from dojoagents.dashboard.schemas.freshness import DataSource
from dojoagents.utils.async_runtime import gather_ordered

T = TypeVar("T")

KLINE_QUERY_FIELDS = [
    "symbol",
    "kline_t",
    "bar_time",
    "open",
    "high",
    "low",
    "close",
    "vol",
    "amount",
    "change_p",
    "tr",
    "adj_factor_cum",
    "dividends",
    "splits",
]


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
    snapshot: dict[str, str] | None = None


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


def _df_result(
    df: "pd.DataFrame",
    *,
    snapshot: dict[str, str] | None = None,
) -> GatewayResult["pd.DataFrame"]:
    if not df.empty and "market" in df.columns:
        df["market"] = df["market"].replace({"cn": "sh", "zh": "sh"})
    as_of = str(df["bar_time"].max()) if not df.empty and "bar_time" in df.columns else None
    return GatewayResult(df, as_of, "sdk_snapshot", False, snapshot)


class DojoDataGateway:
    def __init__(
        self,
        client: Any,
        *,
        live_client: Any | None = None,
        kline_max_concurrent: int = 50,
    ) -> None:
        if kline_max_concurrent < 1:
            raise ValueError("kline_max_concurrent must be at least 1")
        self.client = client
        self.live_client = live_client
        self.kline_max_concurrent = kline_max_concurrent
        self._latest_kline_snapshot: dict[str, str] | None = None

    @property
    def has_live_client(self) -> bool:
        return self.live_client is not None

    async def _call_realtime(
        self,
        operation: str,
        live_factory: Any,
        snapshot_factory: Any,
    ) -> tuple[Any, bool]:
        """Prefer the live API and fall back to the offline snapshot.

        Factories are used instead of pre-created coroutine objects so a
        successful live request never leaves an un-awaited fallback coroutine.
        """
        if self.live_client is not None:
            try:
                return await self._call(operation, live_factory()), True
            except GatewayError as exc:
                LOGGER.warning(
                    "%s live request failed; falling back to the committed snapshot: %s",
                    operation,
                    exc,
                )
        return await self._call(operation, snapshot_factory()), False

    def invalidate_kline_snapshot(self) -> None:
        """Forget the last observed snapshot identity after an explicit refresh."""
        self._latest_kline_snapshot = None

    @property
    def latest_kline_snapshot(self) -> dict[str, str] | None:
        return self._latest_kline_snapshot

    async def _call(self, operation: str, awaitable: Any) -> Any:
        try:
            return await awaitable
        except (TimeoutError, httpx.TimeoutException) as exc:
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
        canonical = [_canonical_symbol(symbol) for symbol in symbols]
        body = {"symbols": ",".join(canonical)}
        payload, used_live = await self._call_realtime(
            "stock_quotes",
            lambda: self.live_client.stocks.post_quote(body=body),
            lambda: self.client.stocks.post_quote(body=body),
        )
        result = _list_result(payload, "stock_quotes", "quotes")
        if used_live:
            result = GatewayResult(result.data, result.as_of, "sdk_online", False, result.snapshot)
        elif self.live_client is not None:
            result = GatewayResult(result.data, result.as_of, "sdk_snapshot", True, result.snapshot)
        else:
            # Pure snapshot deployment: no live client is configured, so the
            # payload is served from the committed offline snapshot. It carries
            # no ``source`` field of its own, which previously fell through to
            # the ``"remote" -> "sdk_online"`` alias default and mislabelled
            # snapshot quotes as live. Consumers (e.g. the sector-movers
            # live-quote overlay) then treated a lagging quote snapshot as
            # fresher than the independently published sector precompute.
            result = GatewayResult(result.data, result.as_of, "sdk_snapshot", False, result.snapshot)
        payload_keys = list(payload)[:10] if isinstance(payload, dict) else []
        returned_symbols = [str(row.get("symbol") or row.get("ticker")) for row in result.data[:5] if isinstance(row, dict) and (row.get("symbol") or row.get("ticker"))]
        LOGGER.debug(
            "[DojoDataGateway][stock_quotes] market=%s method=POST requested=%s returned=%s payload_type=%s payload_keys=%s request_sample=%s response_symbol_sample=%s",
            market,
            len(canonical),
            len(result.data),
            type(payload).__name__,
            payload_keys,
            canonical[:5],
            returned_symbols,
        )
        return result

    async def stock_klines(
        self,
        symbols: list[str],
        **window: Any,
    ) -> GatewayResult["pd.DataFrame"]:
        canonical_symbols = [_canonical_symbol(symbol) for symbol in symbols]
        kwargs = {key: value for key, value in window.items() if value is not None}
        kwargs.pop("market", None)
        online = getattr(self.client, "_online", None)
        LOGGER.debug(
            "dojo_kline_route route=%s symbols=%d window=%s",
            "offline_batch" if online is False else "online_per_symbol",
            len(canonical_symbols),
            kwargs,
        )
        if online is not False:
            return await self._fetch_klines_per_symbol(canonical_symbols, kwargs)
        return await self._fetch_offline_kline_batch(canonical_symbols, kwargs)

    async def _fetch_offline_kline_batch(
        self,
        symbols: list[str],
        kwargs: dict[str, Any],
    ) -> GatewayResult["pd.DataFrame"]:
        limit = kwargs.get("limit")
        requested_fields = kwargs.get("fields")
        fields = (
            list(dict.fromkeys(str(field).strip() for field in requested_fields if str(field).strip())) if isinstance(requested_fields, (list, tuple)) else list(KLINE_QUERY_FIELDS)
        )
        payload = await self._call(
            "stock_klines",
            self.client.stocks.get_klines(
                symbols=symbols,
                start=kwargs.get("start_time"),
                end=kwargs.get("end_time"),
                fields=fields,
                limit_per_symbol=(None if limit in {None, 0} else int(limit)),
                adjust=kwargs.get("price_adj_type") or "pre",
                kline_t=kwargs.get("kline_t"),
                adjustment_reference_date=kwargs.get("price_adj_date"),
            ),
        )
        mapping = _payload_mapping(payload, "stock_klines")
        rows = mapping.get("rows")
        if not isinstance(rows, list):
            raise GatewayBadResponseError("stock_klines: batch rows are not a list")
        snapshot = mapping.get("snapshot")
        if not isinstance(snapshot, dict):
            raise GatewayBadResponseError("stock_klines: snapshot metadata is missing")
        normalized_snapshot = {str(key): str(value) for key, value in snapshot.items()}
        self._latest_kline_snapshot = normalized_snapshot
        normalized_rows = [row.model_dump() if hasattr(row, "model_dump") else row for row in rows]
        frame = self._normalize_kline_frame(normalized_rows)
        return _df_result(frame, snapshot=normalized_snapshot)

    async def _fetch_kline_rows(self, symbols: list[str], kwargs: dict[str, Any]) -> list[dict[str, Any]]:
        async def fetch_one(symbol: str) -> list[dict[str, Any]]:
            payload = await self._call(
                "stock_klines",
                self.client.stocks.get_kline(symbol=symbol, **kwargs),
            )
            result = _list_result(payload, "stock_klines", "klines")
            if LOGGER.isEnabledFor(logging.DEBUG) and symbol in symbols[:3]:
                sample = []
                for row in (result.data[:1] + result.data[-1:] if len(result.data) > 1 else result.data):
                    raw_time = row.get("bar_time") or row.get("date") or row.get("datetime")
                    sample.append({"bar_time": raw_time, "bar_time_type": type(raw_time).__name__, "close": row.get("close")})
                raw_times = [str(row.get("bar_time") or row.get("date") or row.get("datetime")) for row in result.data]
                LOGGER.debug(
                    "dojo_kline_raw_sample symbol=%s rows=%d raw_min=%s raw_max=%s sample=%s",
                    symbol,
                    len(result.data),
                    min(raw_times, default=None),
                    max(raw_times, default=None),
                    json.dumps(sample, default=str),
                )
            return result.data

        results = await gather_ordered(
            [lambda symbol=symbol: fetch_one(symbol) for symbol in symbols],
            max_concurrency=self.kline_max_concurrent,
            return_exceptions=True,
        )
        rows: list[dict[str, Any]] = []
        failures = 0
        failure_sample = []
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                failures += 1
                if len(failure_sample) < 3:
                    failure_sample.append({"symbol": symbol, "error_type": type(result).__name__})
                continue
            rows.extend(result)
        if failures:
            LOGGER.warning("Failed to fetch %d/%d stock K-lines", failures, len(symbols))
            LOGGER.debug("dojo_kline_failures count=%d sample=%s", failures, failure_sample)
        LOGGER.debug("dojo_kline_response requested_symbols=%d returned_rows=%d failures=%d", len(symbols), len(rows), failures)
        return rows

    async def _fetch_klines_per_symbol(
        self,
        symbols: list[str],
        kwargs: dict[str, Any],
    ) -> GatewayResult["pd.DataFrame"]:
        # The legacy online endpoint does not expose column projection. Keep
        # ``fields`` as an offline-only optimization instead of leaking an
        # unsupported parameter into get_kline().
        kwargs.pop("fields", None)
        rows = await self._fetch_kline_rows(symbols, kwargs)
        frame = pd.DataFrame(rows)
        if getattr(self.client, "_online", None) is True:
            as_of = str(frame["bar_time"].max()) if not frame.empty and "bar_time" in frame.columns else None
            return GatewayResult(frame, as_of, "sdk_online", False)
        return _df_result(frame)

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
                raise GatewayBadResponseError("stock_klines: upstream rows have no symbol")
        frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper()
        return frame[frame["symbol"] != ""].reset_index(drop=True)

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
        payload, used_live = await self._call_realtime(
            "stock_events",
            lambda: self.live_client.stocks.get_event_remind(**{key: value for key, value in kwargs.items() if value is not None}),
            lambda: self.client.stocks.get_event_remind(**{key: value for key, value in kwargs.items() if value is not None}),
        )
        result = _list_result(payload, "stock_events", "data")
        if used_live:
            return GatewayResult(result.data, result.as_of, "sdk_online", False, result.snapshot)
        if self.live_client is not None:
            return GatewayResult(result.data, result.as_of, "sdk_snapshot", True, result.snapshot)
        return result

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
        payload, used_live = await self._call_realtime(
            "stock_news",
            lambda: self.live_client.stocks.get_news(**{key: value for key, value in kwargs.items() if value is not None}),
            lambda: self.client.stocks.get_news(**{key: value for key, value in kwargs.items() if value is not None}),
        )
        result = _list_result(payload, "stock_news", "news")
        if used_live:
            return GatewayResult(result.data, result.as_of, "sdk_online", False, result.snapshot)
        if self.live_client is not None:
            return GatewayResult(result.data, result.as_of, "sdk_snapshot", True, result.snapshot)
        return result

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
