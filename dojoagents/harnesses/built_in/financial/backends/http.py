"""Remote Dashboard Financial API backend for CLI and Gateway hosts."""

from __future__ import annotations

from types import MappingProxyType
from typing import Any, Mapping

import httpx

from .base import FinancialToolDefinition

_TOOL_ROUTES: dict[str, tuple[str, str]] = {
    "search_company_ticker": (
        "GET",
        "/api/v1/utility/search/company-ticker",
    ),
    "search_sector_taxonomy": (
        "GET",
        "/api/v1/utility/search/sector-taxonomy",
    ),
    "get_taxonomy_tree": ("GET", "/api/v1/utility/taxonomy/tree"),
    "get_market_overview": ("GET", "/api/v1/market/overview"),
    "get_sector_movers": ("GET", "/api/v1/market/sector-movers"),
    "screen_market_stocks": ("GET", "/api/v1/market/screener"),
    "get_sector_analysis": ("GET", "/api/v1/sector/analysis"),
    "filter_sector_constituents": (
        "GET",
        "/api/v1/sector/constituents",
    ),
    "get_ticker_realtime_quote": ("GET", "/api/v1/ticker/quote"),
    "get_ticker_financials": ("GET", "/api/v1/ticker/financials"),
    "get_ticker_news_and_events": (
        "GET",
        "/api/v1/ticker/news-events",
    ),
    "get_ticker_price_trends": (
        "GET",
        "/api/v1/ticker/price-trends",
    ),
    "portfolio_read_list": ("GET", "/api/v1/portfolio"),
    "portfolio_read_search": ("GET", "/api/v1/portfolio"),
    "portfolio_read_detail": (
        "GET",
        "/api/v1/portfolio/{portfolio_id}/analysis",
    ),
    "portfolio_write_create": ("POST", "/api/v1/portfolio/manage"),
    "portfolio_write_add_candidate": (
        "POST",
        "/api/v1/portfolio/holdings",
    ),
    "portfolio_write_add_candidates": (
        "POST",
        "/api/v1/portfolio/holdings/batch",
    ),
    "portfolio_write_add_holding": (
        "POST",
        "/api/v1/portfolio/holdings",
    ),
    "portfolio_write_add_holdings": (
        "POST",
        "/api/v1/portfolio/holdings/batch",
    ),
    "portfolio_write_auto_allocate": (
        "POST",
        "/api/v1/portfolio/allocate",
    ),
}


class HTTPFinancialToolBackend:
    def __init__(
        self,
        base_url: str,
        *,
        auth_token: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        if not str(base_url or "").strip():
            raise ValueError("financial HTTP backend requires base_url")
        self.base_url = base_url.rstrip("/")
        self.auth_token = auth_token
        self.timeout = timeout
        self._definitions = MappingProxyType(
            {
                name: FinancialToolDefinition(
                    name=name,
                    description=("Execute the financial operation through the configured " "Dashboard Financial API."),
                    parameters={
                        "type": "object",
                        "properties": {},
                        "additionalProperties": True,
                    },
                )
                for name in _TOOL_ROUTES
            }
        )

    @property
    def supported_tools(self) -> frozenset[str]:
        return frozenset(_TOOL_ROUTES)

    @property
    def tool_definitions(self) -> Mapping[str, FinancialToolDefinition]:
        return self._definitions

    async def health(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=min(self.timeout, 5.0)) as client:
                response = await client.get(f"{self.base_url}/api/health")
            return response.status_code < 500
        except httpx.HTTPError:
            return False

    async def execute(
        self,
        tool_name: str,
        arguments: Mapping[str, Any],
        *,
        principal: Any,
        session_id: str,
    ) -> Mapping[str, Any]:
        route = _TOOL_ROUTES.get(tool_name)
        if route is None:
            raise RuntimeError(f"financial tool '{tool_name}' is unsupported by HTTP backend")
        method, path = route
        payload = dict(arguments)
        for key in ("portfolio_id",):
            marker = "{" + key + "}"
            if marker in path:
                value = str(payload.pop(key, "")).strip()
                if not value:
                    raise RuntimeError(f"{tool_name} requires {key}")
                path = path.replace(marker, value)
        user_id = str(getattr(principal, "user_id", "")).strip()
        tenant_id = str(getattr(principal, "tenant_id", "default")).strip()
        if not user_id or not session_id.strip():
            raise RuntimeError("financial HTTP backend requires principal and session_id")
        headers = {
            "X-Dojo-User-ID": user_id,
            "X-Dojo-Tenant-ID": tenant_id,
            "X-Dojo-Session-ID": session_id,
        }
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.request(
                    method,
                    f"{self.base_url}{path}",
                    headers=headers,
                    params=payload if method == "GET" else None,
                    json=payload if method != "GET" else None,
                )
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            return {
                "content": f"Dashboard Financial API unavailable: {exc}",
                "data": {},
                "metadata": {
                    "backend": "dashboard-http",
                    "error_code": "backend_unavailable",
                },
            }
        if response.status_code >= 400:
            return {
                "content": str(data),
                "data": data if isinstance(data, dict) else {},
                "metadata": {
                    "backend": "dashboard-http",
                    "error_code": f"http_{response.status_code}",
                },
            }
        return {
            "content": str(data),
            "data": data,
            "metadata": {
                "backend": "dashboard-http",
                "error_code": None,
            },
        }


__all__ = ["HTTPFinancialToolBackend"]
