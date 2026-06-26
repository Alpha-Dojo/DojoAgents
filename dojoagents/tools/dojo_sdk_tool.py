# dojoagents/tools/dojo_sdk_tool.py
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from dojo.client.async_client import AsyncDojo
from dojo.datasource.registry import HF_REGISTRY
from dojoagents.config.models import DojoSDKConfig
from dojoagents.tools.registry import ToolSpec


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
}


class DojoSDKToolManager:
    def __init__(self, config: DojoSDKConfig | None = None) -> None:
        self.config = config
        self._client: AsyncDojo | None = None

    @property
    def client(self) -> AsyncDojo:
        """Lazily initialize the AsyncDojo client using environment variables and configuration."""
        if self._client is None:
            kwargs: dict[str, Any] = {}
            if self.config is not None:
                if self.config.api_key:
                    kwargs["api_key"] = self.config.api_key
                if self.config.base_url:
                    kwargs["base_url"] = self.config.base_url
                kwargs["timeout"] = self.config.timeout
                kwargs["max_retries"] = self.config.max_retries
            self._client = AsyncDojo(**kwargs)
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
        return specs

    async def _ok(self, res: Any) -> dict[str, Any]:
        return {"content": json.dumps(_dump_res(res), ensure_ascii=False), "metadata": {"ok": True}}

    async def _benchmark_kline(self, args: dict[str, Any]) -> dict[str, Any]:
        res = await self.client.benchmark.get_kline(
            symbol=args["symbol"],
            kline_t=_normalize_kline_t(args.get("kline_t")),
            start_time=args.get("start_time"),
            end_time=args.get("end_time"),
            price_adj_type=args.get("price_adj_type"),
            price_adj_date=args.get("price_adj_date"),
            limit=args.get("limit"),
        )
        return await self._ok(res)

    async def _benchmark_catalog(self, args: dict[str, Any]) -> dict[str, Any]:
        del args
        res = await self.client.benchmark.get_catalog()
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

    async def _sector_precomputed_manifest(self, args: dict[str, Any]) -> dict[str, Any]:
        del args
        res = await self.client.sectors.get_precomputed_manifest()
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
        res = await self.client.stocks.get_kline(
            symbol=args["symbol"],
            kline_t=_normalize_kline_t(args.get("kline_t")),
            start_time=args.get("start_time"),
            end_time=args.get("end_time"),
            price_adj_type=args.get("price_adj_type"),
            price_adj_date=args.get("price_adj_date"),
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
            start_time=args.get("start_time"),
            end_time=args.get("end_time"),
            limit=args.get("limit"),
        )
        return await self._ok(res)


def get_dojo_sdk_specs(config: DojoSDKConfig | None = None) -> list[ToolSpec]:
    """Factory helper to register specs in the runtime registry."""
    return DojoSDKToolManager(config).get_tool_specs()
