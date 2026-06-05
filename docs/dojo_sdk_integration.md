# DojoSDK Integration Guide

This guide details how to integrate the Dojo client SDK (`/Users/kk1999/Local_Documents/code/alphadojo/DojoSDK`) into `DojoAgents`. Since DojoSDK is a standard Python library dependency of DojoAgents, it is registered directly as a core built-in tool capability without requiring user configuration file edits.

---

## 1. Installation

DojoSDK should be installed into the virtual environment of `DojoAgents`. For local development, use an editable install:

```bash
# Activate the virtual environment
source .venv/bin/activate

# Install DojoSDK in editable mode
pip install -e /Users/kk1999/Local_Documents/code/alphadojo/DojoSDK
```

Alternatively, add `dojosdk` directly to the `dependencies` list in `pyproject.toml`:

```toml
# pyproject.toml
dependencies = [
    # ... other dependencies ...
    "dojosdk",
]
```

### Authentication
The SDK client automatically authenticates requests using the following environment variable:
* `DOJO_API_KEY`: The API key (required).
* `DOJO_BASE_URL`: The Dojo API host (optional, defaults to `https://api.flowhale.ai`).

These are injected at run-time into the process environment.

---

## 2. Code Design: Direct Tool Registration

Rather than making DojoSDK optional via configuration switches, we integrate it as a built-in tool module in `dojoagents/tools/dojo_sdk_tool.py`. To ensure robust operations if the library is missing or fails to import in clean testing environments, the module handles `ImportError` gracefully.

### A. Implementing `dojoagents/tools/dojo_sdk_tool.py`

Create this new file to define the tool specifications and call handlers:

```python
# dojoagents/tools/dojo_sdk_tool.py
from __future__ import annotations

import json
import logging
from typing import Any
from dojoagents.tools.registry import ToolSpec

LOGGER = logging.getLogger(__name__)

# Try to import from the dependent dojosdk library
try:
    from dojo.client.async_client import AsyncDojo
    from dojo._compat import model_dump
    HAS_DOJO_SDK = True
except ImportError:
    LOGGER.warning("dojosdk library is not installed. DojoSDK tools will be unavailable.")
    HAS_DOJO_SDK = False


class DojoSDKToolManager:
    def __init__(self) -> None:
        self._client: AsyncDojo | None = None

    @property
    def client(self) -> AsyncDojo:
        """Lazily initialize the AsyncDojo client using environment variables."""
        if self._client is None:
            self._client = AsyncDojo()
        return self._client

    def get_tool_specs(self) -> list[ToolSpec]:
        if not HAS_DOJO_SDK:
            return []

        return [
            ToolSpec(
                name="dojo.sdk.get_kline",
                description=(
                    "Retrieve historical kline (candlestick) data for stock or crypto symbols. "
                    "Returns timestamp, open, high, low, close, and volume."
                ),
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
                name="dojo.sdk.get_news",
                description="Retrieve general financial news and event streams.",
                parameters={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Max news items", "default": 10},
                    },
                },
                handler=self.get_news_handler,
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
        # Using model_dump helper from dojo._compat to handle pydantic v1 vs v2 seamlessly
        return {
            "content": json.dumps(model_dump(res), ensure_ascii=False),
            "metadata": {"ok": True}
        }

    async def get_ticker_handler(self, args: dict[str, Any]) -> dict[str, Any]:
        res = await self.client.market_data.get_ticker(
            exchange=args["exchange"],
            bz_type=args["bz_type"],
            symbol=args["symbol"],
        )
        return {
            "content": json.dumps(model_dump(res), ensure_ascii=False),
            "metadata": {"ok": True}
        }

    async def get_news_handler(self, args: dict[str, Any]) -> dict[str, Any]:
        res = await self.client.news.get_news(
            limit=args.get("limit", 10),
        )
        return {
            "content": json.dumps(model_dump(res), ensure_ascii=False),
            "metadata": {"ok": True}
        }


def get_dojo_sdk_specs() -> list[ToolSpec]:
    """Factory helper to register specs in the runtime registry."""
    return DojoSDKToolManager().get_tool_specs()
```

### B. Wiring into Runtime Registry

Modify `dojoagents/agent/runtime.py` to register the specs directly during runtime bootstrapping. This happens alongside other built-in tools (such as the terminal tool and code execution tool):

```python
# dojoagents/agent/runtime.py
# (Locate near line 88-92)

        from dojoagents.tools.terminal_tool import get_terminal_spec
        policy = SandboxPolicy(
            allowed_roots=config.tools.sandbox.allowed_roots,
            allow_network=config.tools.sandbox.allow_network,
            allowed_commands=config.tools.sandbox.allowed_commands,
            timeout_seconds=config.tools.sandbox.timeout_seconds,
        )
        tool_registry.register(get_terminal_spec(policy))

        from dojoagents.tools.code_execution_tool import get_code_execution_spec
        tool_registry.register(get_code_execution_spec(tool_registry, policy))

        # Register DojoSDK tools directly from the library module
        from dojoagents.tools.dojo_sdk_tool import get_dojo_sdk_specs
        for spec in get_dojo_sdk_specs():
            tool_registry.register(spec)
```

---

## 3. Verification

1. **Import Fallback Check**:
   If the `dojosdk` package is uninstalled or pending installation, `get_dojo_sdk_specs()` returns an empty list `[]` instead of raising an unhandled exception, ensuring that the remaining agent systems start up properly.
2. **Execution Verification**:
   Execute the test suite to verify registry bootstrapping remains fully operational:
   ```bash
   .venv/bin/pytest tests/test_built_in_discovery.py
   ```
