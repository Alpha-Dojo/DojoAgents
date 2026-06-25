# dojoagents/tools/dojo_sdk_tool.py
from __future__ import annotations

import json
import logging
from typing import Any
from dojoagents.tools.registry import ToolSpec
from dojoagents.config.models import DojoSDKConfig

LOGGER = logging.getLogger(__name__)

try:
    from dojo.client.async_client import AsyncDojo

    HAS_DOJO_SDK = True
except ImportError:
    LOGGER.warning("dojosdk library is not installed. DojoSDK tools will be unavailable.")
    HAS_DOJO_SDK = False


def _dump_res(res: Any) -> Any:
    if isinstance(res, (dict, list)):
        return res
    from dojo._compat import model_dump

    return model_dump(res)


class DojoSDKToolManager:
    def __init__(self, config: DojoSDKConfig | None = None) -> None:
        self.config = config
        self._client: AsyncDojo | None = None

    @property
    def client(self) -> AsyncDojo:
        """Lazily initialize the AsyncDojo client using environment variables and configuration."""
        if self._client is None:
            kwargs = {}
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
        if not HAS_DOJO_SDK:
            return []

        return [
            ToolSpec(
                name="dojo.sdk.get_kline",
                description=("Retrieve historical kline (candlestick) data for stock or crypto symbols. " "Returns timestamp, open, high, low, close, and volume."),
                parameters={
                    "type": "object",
                    "properties": {
                        "exchange": {"type": "string", "description": "Exchange name (e.g. BINANCE)"},
                        "bz_type": {"type": "string", "description": "Business type (e.g. SPOT, SWAP)"},
                        "symbol": {"type": "string", "description": "Trading pair or ticker symbol (e.g. BTCUSDT)"},
                        "kline_t": {"type": "string", "description": "Interval (e.g. 1m, 5m, 1h, 1d)", "default": "1d"},
                        "limit": {"type": "integer", "description": "Max records limit", "default": 100},
                    },
                    "required": ["exchange", "bz_type", "symbol"],
                },
                handler=self.get_kline_handler,
            ),
            ToolSpec(
                name="dojo.sdk.get_ticker",
                description="Retrieve real-time ticker data with 24-hour price and volume stats.",
                parameters={
                    "type": "object",
                    "properties": {
                        "exchange": {"type": "string", "description": "Exchange name"},
                        "bz_type": {"type": "string", "description": "Business type"},
                        "symbol": {"type": "string", "description": "Ticker symbol to query"},
                    },
                    "required": ["exchange", "bz_type", "symbol"],
                },
                handler=self.get_ticker_handler,
            ),
            ToolSpec(
                name="dojo.sdk.get_stock_quote",
                description="Retrieve current quote pricing (price, volume, etc.) for a list of stock symbols.",
                parameters={
                    "type": "object",
                    "properties": {
                        "symbols": {"type": "array", "items": {"type": "string"}, "description": "List of stock ticker symbols to query (e.g. AAPL)"},
                    },
                    "required": ["symbols"],
                },
                handler=self.get_stock_quote_handler,
            ),
            ToolSpec(
                name="dojo.sdk.get_stock_kline",
                description="Query single stock daily K-line time series with price adjustments.",
                parameters={
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Stock ticker symbol (e.g., AAPL)"},
                        "kline_t": {"type": "string", "description": "Bar interval (1m, 3m, 5m, 15m, 1H, 8H, 1D, 1W)", "default": "1D"},
                        "limit": {"type": "integer", "description": "Max records limit", "default": 100},
                        "start_time": {"type": "string", "description": "ISO-8601 start date time filter"},
                        "end_time": {"type": "string", "description": "ISO-8601 end date time filter"},
                    },
                    "required": ["symbol"],
                },
                handler=self.get_stock_kline_handler,
            ),
            ToolSpec(
                name="dojo.sdk.get_stock_news",
                description="Retrieve news articles specifically related to a target stock ticker symbol.",
                parameters={
                    "type": "object",
                    "properties": {
                        "symbol": {"type": "string", "description": "Target stock ticker symbol"},
                        "page": {"type": "integer", "description": "Page number", "default": 1},
                        "page_size": {"type": "integer", "description": "Page size", "default": 10},
                    },
                    "required": ["symbol"],
                },
                handler=self.get_stock_news_handler,
            ),
        ]

    async def get_kline_handler(self, args: dict[str, Any]) -> dict[str, Any]:
        res = await self.client.market_data.get_kline(
            exchange=args["exchange"],
            bz_type=args["bz_type"],
            symbol=args["symbol"],
            kline_t=args.get("kline_t", "1d"),
            limit=args.get("limit", 100),
        )
        return {"content": json.dumps(_dump_res(res), ensure_ascii=False), "metadata": {"ok": True}}

    async def get_ticker_handler(self, args: dict[str, Any]) -> dict[str, Any]:
        res = await self.client.market_data.get_ticker(
            exchange=args["exchange"],
            bz_type=args["bz_type"],
            symbol=args["symbol"],
        )
        return {"content": json.dumps(_dump_res(res), ensure_ascii=False), "metadata": {"ok": True}}

    async def get_stock_quote_handler(self, args: dict[str, Any]) -> dict[str, Any]:
        res = await self.client.stocks.get_quote(symbols=args["symbols"])
        return {"content": json.dumps(_dump_res(res), ensure_ascii=False), "metadata": {"ok": True}}

    async def get_stock_kline_handler(self, args: dict[str, Any]) -> dict[str, Any]:
        kline_t_raw = args.get("kline_t")
        if kline_t_raw:
            mapping = {
                "1h": "1H",
                "8h": "8H",
                "1d": "1D",
                "1w": "1W",
            }
            kline_t = mapping.get(kline_t_raw.lower(), kline_t_raw)
        else:
            kline_t = "1D"

        res = await self.client.stocks.get_kline(
            symbol=args["symbol"],
            kline_t=kline_t,
            start_time=args.get("start_time"),
            end_time=args.get("end_time"),
            limit=args.get("limit"),
        )
        return {"content": json.dumps(_dump_res(res), ensure_ascii=False), "metadata": {"ok": True}}

    async def get_stock_financials_handler(self, args: dict[str, Any]) -> dict[str, Any]:
        res = await self.client.stocks.get_financials(
            symbol=args["symbol"],
            lookback=args.get("lookback"),
        )
        return {"content": json.dumps(_dump_res(res), ensure_ascii=False), "metadata": {"ok": True}}

    async def get_stock_news_handler(self, args: dict[str, Any]) -> dict[str, Any]:
        res = await self.client.stocks.get_news(
            symbol=args["symbol"],
            page=args.get("page") or 1,
            page_size=args.get("page_size") or 10,
        )
        return {"content": json.dumps(_dump_res(res), ensure_ascii=False), "metadata": {"ok": True}}


def get_dojo_sdk_specs(config: DojoSDKConfig | None = None) -> list[ToolSpec]:
    """Factory helper to register specs in the runtime registry."""
    return DojoSDKToolManager(config).get_tool_specs()
