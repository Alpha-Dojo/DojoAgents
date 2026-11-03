"""Optional research evidence, never an execution or price-data provider."""

import os
import re
from datetime import date

import httpx

SOURCES = {
    "reddit_stocks": "reddit/stocks/v1",
    "reddit_crypto": "reddit/crypto/v1",
    "x_stocks": "x/stocks/v1",
    "news_stocks": "news/stocks/v1",
    "polymarket_stocks": "polymarket/stocks/v1",
}
OPERATIONS = {"asset", "trending", "market", "compare"}


def register(context):
    api_key = os.environ.get("ADANOS_API_KEY", "").strip()
    if not api_key:
        return

    async def handle(args):
        try:
            if set(args) - {"source", "operation", "asset", "assets", "from", "to", "limit"}:
                raise ValueError("Unsupported argument; use from/to, not days.")
            source = args["source"]
            operation = args["operation"]
            if source not in SOURCES or operation not in OPERATIONS:
                raise ValueError("Unsupported source or operation.")
            params = {key: date.fromisoformat(args[key]).isoformat() for key in ("from", "to") if key in args}
            if params.get("from", "") > params.get("to", "9999-12-31"):
                raise ValueError("from must not be later than to.")
            path = {"trending": "trending", "market": "market-sentiment", "compare": "compare"}.get(operation)
            if operation in {"asset", "compare"}:
                assets = [args["asset"]] if operation == "asset" else args["assets"]
                if not isinstance(assets, list) or not 1 <= len(assets) <= 10:
                    raise ValueError("Provide one asset or 1-10 comparison assets.")
                if any(not isinstance(asset, str) or not re.fullmatch(r"[$A-Za-z0-9][A-Za-z0-9.$-]{0,31}", asset) for asset in assets):
                    raise ValueError("Invalid asset identifier.")
                if operation == "asset":
                    path = f"{'token' if source == 'reddit_crypto' else 'stock'}/{assets[0]}"
                else:
                    params["symbols" if source == "reddit_crypto" else "tickers"] = ",".join(assets)
            if "limit" in args:
                if operation != "trending" or type(args["limit"]) is not int or not 1 <= args["limit"] <= 100:
                    raise ValueError("limit is only supported for trending (1-100).")
                params["limit"] = args["limit"]
        except (KeyError, TypeError, ValueError):
            return {"error": "Invalid Adanos arguments; check source, operation, assets and UTC from/to dates."}

        url = f"https://api.adanos.org/{SOURCES[source]}/{path}"
        try:
            async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
                response = await client.get(url, params=params, headers={"X-API-Key": api_key})
            if response.status_code != 200:
                return {"error": f"Adanos request failed (HTTP {response.status_code}); check API access and quota.", "status": response.status_code}
            data = response.json()
        except (httpx.HTTPError, ValueError):
            return {"error": "Adanos could not return valid JSON; retry later."}
        return {"source": source, "url": url, "query": params, "data": data}

    context.register_tool(
        "adanos_sentiment",
        {
            "description": (
                "Fetch optional Adanos market sentiment evidence, not prices or buy/sell advice. "
                "Source availability, history and quotas depend on your Adanos plan. "
                "News uses company keys (e.g. BRK, not BRK.B)."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "source": {"type": "string", "enum": list(SOURCES)},
                    "operation": {"type": "string", "enum": sorted(OPERATIONS)},
                    "asset": {"type": "string", "description": "Ticker, News company key, or crypto symbol; required for asset."},
                    "assets": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 10, "description": "Required for compare."},
                    "from": {"type": "string", "format": "date", "description": "Inclusive start UTC date (YYYY-MM-DD)."},
                    "to": {"type": "string", "format": "date", "description": "Inclusive end UTC date (YYYY-MM-DD)."},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Trending result count."},
                },
                "required": ["source", "operation"],
            },
        },
        handle,
    )
