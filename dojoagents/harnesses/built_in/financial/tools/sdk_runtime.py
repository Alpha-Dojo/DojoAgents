"""Financial DojoSDK ToolSpec implementation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from dojo.client.async_client import AsyncDojo
from dojo.datasource.registry import HF_REGISTRY
from dojo.resources.base import normalize_naive_iso_datetime
from dojoagents.config.models import AgentsConfig, DojoSDKConfig
from dojoagents.dojo_sdk import create_async_dojo, create_async_dojo_from_settings
from dojoagents.tools.registry import ToolSpec

from ..config import FinancialSDKConfig


def _dump_res(res: Any) -> Any:
    if isinstance(res, (dict, list)):
        return res
    from dojo._compat import model_dump

    return model_dump(res)


def _normalize_kline_t(raw: str | None, *, default: str = "1D") -> str | None:
    if raw is None:
        return default
    mapping = {"1h": "1H", "8h": "8H", "1d": "1D", "1w": "1W"}
    return mapping.get(raw.lower(), raw)


def _object_schema(*, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


@dataclass(frozen=True)
class OfflineToolBinding:
    name: str
    description: str
    parameters: dict[str, Any]
    handler_name: str


OFFLINE_TOOL_BINDINGS: dict[str, OfflineToolBinding] = {
    "/api/qdata/v1/benchmark/kline": OfflineToolBinding(
        name="dojo.sdk.benchmark.kline",
        description="Retrieve benchmark index kline (candlestick) data from offline HuggingFace datasets.",
        parameters=_object_schema(
            properties={
                "symbol": {"type": "string", "description": "Benchmark symbol"},
                "kline_t": {"type": "string", "description": "Bar interval (e.g. 1m, 1h, 1d)"},
                "start_time": {"type": "string", "description": "ISO-8601 start time filter"},
                "end_time": {"type": "string", "description": "ISO-8601 end time filter"},
                "price_adj_type": {"type": "string", "description": "Price adjustment type"},
                "price_adj_date": {"type": "string", "description": "Price adjustment reference date"},
                "limit": {"type": "integer", "description": "Max records to return"},
            },
            required=["symbol"],
        ),
        handler_name="_benchmark_kline",
    ),
    "/api/qdata/v1/sector/info": OfflineToolBinding(
        name="dojo.sdk.sector.info",
        description="Retrieve sector taxonomy information from offline HuggingFace datasets.",
        parameters=_object_schema(
            properties={
                "name": {"type": "string", "description": "Sector name"},
                "name_alias": {"type": "string", "description": "Sector name alias"},
                "description_alias": {"type": "string", "description": "Sector description alias"},
                "level": {"type": "integer", "description": "Sector hierarchy level"},
                "parent_id": {"type": "integer", "description": "Parent sector ID"},
                "sensitivity": {"type": "string", "description": "Sector sensitivity"},
                "tree": {"type": "boolean", "description": "Return results as a tree"},
            },
        ),
        handler_name="_sector_info",
    ),
    "/api/qdata/v1/sector/symbol_relations": OfflineToolBinding(
        name="dojo.sdk.sector.symbol_relations",
        description="Retrieve sector-to-symbol mapping relations from offline HuggingFace datasets.",
        parameters=_object_schema(
            properties={
                "sector_name": {"type": "string", "description": "Sector name filter"},
                "symbol": {"type": "string", "description": "Symbol filter"},
                "relation_priority": {"type": "string", "description": "Relation priority filter"},
            },
        ),
        handler_name="_sector_symbol_relations",
    ),
    "/api/qdata/v1/stock/ystock_info": OfflineToolBinding(
        name="dojo.sdk.stock.ystock_info",
        description="Retrieve stock profile metadata from offline HuggingFace datasets.",
        parameters=_object_schema(
            properties={
                "symbols": {"type": "string", "description": "Comma-separated ticker symbols"},
                "market": {"type": "string", "description": "Market filter (cn/us/hk)"},
                "full_exchange_name": {"type": "string", "description": "Full exchange name filter"},
                "sector": {"type": "string", "description": "Sector filter"},
                "industry": {"type": "string", "description": "Industry filter"},
                "only_simple_fields": {"type": "boolean", "description": "Return only basic fields"},
                "return_field_list": {"type": "string", "description": "Comma-separated fields to return"},
            },
        ),
        handler_name="_stock_ystock_info",
    ),
    "/api/qdata/v1/stocks/current_quote": OfflineToolBinding(
        name="dojo.sdk.stock.current_quote",
        description="Retrieve current stock quote pricing from offline HuggingFace datasets.",
        parameters=_object_schema(
            properties={
                "symbols": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Stock ticker symbols to query (e.g. AAPL)",
                },
            },
            required=["symbols"],
        ),
        handler_name="_stock_current_quote",
    ),
    "/api/qdata/v1/stock/kline": OfflineToolBinding(
        name="dojo.sdk.stock.kline",
        description="Retrieve stock kline time series from offline HuggingFace datasets.",
        parameters=_object_schema(
            properties={
                "symbol": {"type": "string", "description": "Stock ticker symbol (e.g. AAPL)"},
                "kline_t": {"type": "string", "description": "Bar interval (1m, 3m, 5m, 15m, 1H, 8H, 1D, 1W)"},
                "start_time": {"type": "string", "description": "ISO-8601 start time filter"},
                "end_time": {"type": "string", "description": "ISO-8601 end time filter"},
                "price_adj_type": {"type": "string", "description": "Price adjustment type (pre/post/none)"},
                "price_adj_date": {"type": "string", "description": "Price adjustment reference date"},
                "limit": {"type": "integer", "description": "Max records to return"},
            },
            required=["symbol"],
        ),
        handler_name="_stock_kline",
    ),
    "/api/qdata/v1/stock/fin_indicators": OfflineToolBinding(
        name="dojo.sdk.stock.fin_indicators",
        description="Retrieve stock financial indicators from offline HuggingFace datasets.",
        parameters=_object_schema(
            properties={
                "symbol": {"type": "string", "description": "Stock ticker symbol"},
                "report_type": {"type": "string", "description": "Financial report type filter"},
                "end_date": {"type": "string", "description": "ISO-8601 end date filter"},
                "limit": {"type": "integer", "description": "Max records to return"},
            },
            required=["symbol"],
        ),
        handler_name="_stock_fin_indicators",
    ),
    "/api/qdata/v1/stock/event_remind": OfflineToolBinding(
        name="dojo.sdk.stock.event_remind",
        description="Retrieve stock event reminders from offline HuggingFace datasets.",
        parameters=_object_schema(
            properties={
                "symbol": {"type": "string", "description": "Stock ticker symbol"},
                "page": {"type": "integer", "description": "Page number"},
                "page_size": {"type": "integer", "description": "Page size"},
            },
            required=["symbol"],
        ),
        handler_name="_stock_event_remind",
    ),
    "/api/qdata/v1/stock/main_income": OfflineToolBinding(
        name="dojo.sdk.stock.main_income",
        description="Retrieve stock main business income breakdown from offline HuggingFace datasets.",
        parameters=_object_schema(
            properties={
                "symbol": {"type": "string", "description": "Stock ticker symbol"},
                "page": {"type": "integer", "description": "Page number"},
                "page_size": {"type": "integer", "description": "Page size"},
            },
            required=["symbol"],
        ),
        handler_name="_stock_main_income",
    ),
    "/api/qdata/v1/stocks/news": OfflineToolBinding(
        name="dojo.sdk.stock.news",
        description="Retrieve stock-related news articles from offline HuggingFace datasets.",
        parameters=_object_schema(
            properties={
                "symbol": {"type": "string", "description": "Stock ticker symbol"},
                "page": {"type": "integer", "description": "Page number"},
                "page_size": {"type": "integer", "description": "Page size"},
            },
            required=["symbol"],
        ),
        handler_name="_stock_news",
    ),
    "/api/qdata/v1/forex/kline": OfflineToolBinding(
        name="dojo.sdk.forex.kline",
        description="Retrieve forex kline time series from offline HuggingFace datasets.",
        parameters=_object_schema(
            properties={
                "symbol": {"type": "string", "description": "Forex pair symbol (e.g. EURUSD)"},
                "kline_t": {"type": "string", "description": "Bar interval (e.g. 1m, 1h, 1d)"},
                "start_time": {"type": "string", "description": "ISO-8601 start time filter"},
                "end_time": {"type": "string", "description": "ISO-8601 end time filter"},
                "limit": {"type": "integer", "description": "Max records to return"},
            },
            required=["symbol"],
        ),
        handler_name="_forex_kline",
    ),
    "/api/qdata/v1/benchmark/catalog": OfflineToolBinding(
        "dojo.sdk.benchmark.catalog",
        "Retrieve the offline benchmark catalog.",
        _object_schema(properties={}),
        "_benchmark_catalog",
    ),
    **{
        f"/api/qdata/v1/sector/precomputed/{endpoint}": OfflineToolBinding(
            name=f"dojo.sdk.sector.precomputed.{endpoint}",
            description=f"Retrieve precomputed sector {endpoint.replace('_', ' ')} data.",
            parameters=_object_schema(properties={}),
            handler_name=f"_sector_precomputed_{endpoint}",
        )
        for endpoint in (
            "constituents",
            "sector_daily",
            "ticker_daily",
        )
    },
    "/api/qdata/v1/analysis/market_dynamics": OfflineToolBinding(
        name="dojo.sdk.analysis.market_dynamics",
        description="Retrieve market dynamics analysis records from offline HuggingFace datasets.",
        parameters=_object_schema(
            properties={
                "market": {"type": "string", "description": "Market filter"},
                "category": {"type": "string", "description": "Category filter"},
                "start_time": {"type": "string", "description": "ISO-8601 start time"},
                "end_time": {"type": "string", "description": "ISO-8601 end time"},
                "limit": {"type": "integer", "description": "Max records to return"},
            },
        ),
        handler_name="_analysis_market_dynamics",
    ),
}

OFFLINE_TOOL_ALIASES: tuple[OfflineToolBinding, ...] = ()


class DojoSDKToolManager:
    def __init__(self, config: DojoSDKConfig | FinancialSDKConfig | None = None) -> None:
        self.config = config
        self._client: AsyncDojo | None = None

    @property
    def client(self) -> AsyncDojo:
        """Lazily initialize the AsyncDojo client using environment variables and configuration."""
        if self._client is None:
            if isinstance(self.config, FinancialSDKConfig):
                self._client = create_async_dojo_from_settings(
                    api_key=self.config.api_key,
                    base_url=self.config.base_url,
                    timeout=self.config.timeout,
                    max_retries=self.config.max_retries,
                    offline_enabled=self.config.offline_mode,
                    cache_dir=self.config.cache_dir,
                    backend=self.config.backend,
                    local_files_only=self.config.local_files_only,
                )
            else:
                self._client = create_async_dojo(self.config or AgentsConfig())
        return self._client

    def get_tool_specs(self) -> list[ToolSpec]:
        specs: list[ToolSpec] = []
        for path in sorted(HF_REGISTRY):
            if path in OFFLINE_TOOL_BINDINGS:
                binding = OFFLINE_TOOL_BINDINGS[path]
                handler = getattr(self, binding.handler_name)
                specs.append(
                    ToolSpec(
                        name=binding.name,
                        description=binding.description,
                        parameters=binding.parameters,
                        handler=handler,
                    )
                )
        for binding in OFFLINE_TOOL_ALIASES:
            specs.append(
                ToolSpec(
                    name=binding.name,
                    description=binding.description,
                    parameters=binding.parameters,
                    handler=getattr(self, binding.handler_name),
                )
            )
        return specs

    async def _ok(self, res: Any) -> dict[str, Any]:
        payload = _dump_res(res)
        return {
            "content": json.dumps(payload, ensure_ascii=False),
            "data": payload,
            "metadata": {"ok": True},
        }

    async def _benchmark_kline(self, args: dict[str, Any]) -> dict[str, Any]:
        res = await self.client.benchmark.get_kline(
            symbol=args["symbol"],
            kline_t=_normalize_kline_t(args.get("kline_t")),
            start_time=normalize_naive_iso_datetime(args["start_time"]) if args.get("start_time") else None,
            end_time=normalize_naive_iso_datetime(args["end_time"]) if args.get("end_time") else None,
            price_adj_type=args.get("price_adj_type"),
            price_adj_date=normalize_naive_iso_datetime(args["price_adj_date"]) if args.get("price_adj_date") else None,
            limit=args.get("limit"),
        )
        return await self._ok(res)

    async def _benchmark_catalog(self, args: dict[str, Any]) -> dict[str, Any]:
        del args
        res = await self.client.benchmark.get_catalog()
        return await self._ok(res)

    async def _analysis_market_dynamics(self, args: dict[str, Any]) -> dict[str, Any]:
        res = await self.client.analysis.get_market_dynamics(
            market=args.get("market"),
            category=args.get("category"),
            start_time=args.get("start_time"),
            end_time=args.get("end_time"),
            limit=args.get("limit"),
        )
        return await self._ok(res)

    async def _sector_info(self, args: dict[str, Any]) -> dict[str, Any]:
        res = await self.client.sectors.get_info(
            name=args.get("name"),
            name_alias=args.get("name_alias"),
            description_alias=args.get("description_alias"),
            level=args.get("level"),
            parent_id=args.get("parent_id"),
            sensitivity=args.get("sensitivity"),
            tree=args.get("tree"),
        )
        return await self._ok(res)

    async def _sector_symbol_relations(self, args: dict[str, Any]) -> dict[str, Any]:
        res = await self.client.sectors.get_symbol_relations(
            sector_name=args.get("sector_name"),
            symbol=args.get("symbol"),
            relation_priority=args.get("relation_priority"),
        )
        return await self._ok(res)

    async def _sector_precomputed_constituents(self, args: dict[str, Any]) -> dict[str, Any]:
        del args
        res = await self.client.sectors.get_precomputed_constituents()
        return await self._ok(res)

    async def _sector_precomputed_sector_daily(self, args: dict[str, Any]) -> dict[str, Any]:
        del args
        res = await self.client.sectors.get_precomputed_sector_daily()
        return await self._ok(res)

    async def _sector_precomputed_ticker_daily(self, args: dict[str, Any]) -> dict[str, Any]:
        del args
        res = await self.client.sectors.get_precomputed_ticker_daily()
        return await self._ok(res)

    async def _stock_ystock_info(self, args: dict[str, Any]) -> dict[str, Any]:
        market = args.get("market")
        if market == "sh":
            market = "cn"
        res = await self.client.stocks.get_ystock_info(
            symbols=args.get("symbols"),
            market=market,
            full_exchange_name=args.get("full_exchange_name"),
            sector=args.get("sector"),
            industry=args.get("industry"),
            only_simple_fields=args.get("only_simple_fields"),
            return_field_list=args.get("return_field_list"),
        )
        return await self._ok(res)

    async def _stock_current_quote(self, args: dict[str, Any]) -> dict[str, Any]:
        res = await self.client.stocks.get_quote(symbols=args["symbols"])
        return await self._ok(res)

    async def _stock_kline(self, args: dict[str, Any]) -> dict[str, Any]:
        start = normalize_naive_iso_datetime(args["start_time"]) if args.get("start_time") else None
        end = normalize_naive_iso_datetime(args["end_time"]) if args.get("end_time") else None
        reference_date = (
            normalize_naive_iso_datetime(args["price_adj_date"])
            if args.get("price_adj_date")
            else None
        )
        if getattr(self.client, "_online", None) is False:
            batch = await self.client.stocks.get_klines(
                symbols=[args["symbol"]],
                kline_t=_normalize_kline_t(args.get("kline_t")),
                start=start,
                end=end,
                adjust=args.get("price_adj_type"),
                adjustment_reference_date=reference_date,
                limit_per_symbol=args.get("limit"),
            )
            dumped = _dump_res(batch)
            rows = dumped.get("rows", []) if isinstance(dumped, dict) else []
            return await self._ok(
                {
                    "total_num": len(rows),
                    "data": rows,
                    "snapshot": dumped.get("snapshot") if isinstance(dumped, dict) else None,
                }
            )
        res = await self.client.stocks.get_kline(
            symbol=args["symbol"],
            kline_t=_normalize_kline_t(args.get("kline_t")),
            start_time=start,
            end_time=end,
            price_adj_type=args.get("price_adj_type"),
            price_adj_date=reference_date,
            limit=args.get("limit"),
        )
        return await self._ok(res)

    async def _stock_fin_indicators(self, args: dict[str, Any]) -> dict[str, Any]:
        res = await self.client.stocks.get_fin_indicators(
            symbol=args["symbol"],
            report_type=args.get("report_type"),
            end_date=args.get("end_date"),
            limit=args.get("limit"),
        )
        return await self._ok(res)

    async def _stock_event_remind(self, args: dict[str, Any]) -> dict[str, Any]:
        res = await self.client.stocks.get_event_remind(
            symbol=args["symbol"],
            page=args.get("page"),
            page_size=args.get("page_size"),
        )
        return await self._ok(res)

    async def _stock_main_income(self, args: dict[str, Any]) -> dict[str, Any]:
        res = await self.client.stocks.get_main_income(
            symbol=args["symbol"],
            page=args.get("page"),
            page_size=args.get("page_size"),
        )
        return await self._ok(res)

    async def _stock_news(self, args: dict[str, Any]) -> dict[str, Any]:
        res = await self.client.stocks.get_news(
            symbol=args["symbol"],
            page=args.get("page"),
            page_size=args.get("page_size"),
        )
        return await self._ok(res)

    async def _forex_kline(self, args: dict[str, Any]) -> dict[str, Any]:
        res = await self.client.forex.get_kline(
            symbol=args["symbol"],
            kline_t=_normalize_kline_t(args.get("kline_t"), default=None),
            start_time=normalize_naive_iso_datetime(args["start_time"]) if args.get("start_time") else None,
            end_time=normalize_naive_iso_datetime(args["end_time"]) if args.get("end_time") else None,
            limit=args.get("limit"),
        )
        return await self._ok(res)


def get_dojo_sdk_specs(config: DojoSDKConfig | None = None) -> list[ToolSpec]:
    """Factory helper to register specs in the runtime registry."""
    return DojoSDKToolManager(config).get_tool_specs()
