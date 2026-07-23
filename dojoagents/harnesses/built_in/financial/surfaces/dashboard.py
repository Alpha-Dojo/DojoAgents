"""Financial contributions consumed by the generic Dashboard app factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

from ..context import FinancialRequestContextCodec


class FinancialDashboardSurface:
    def __init__(self, service_container: Any) -> None:
        self.service_container = service_container
        self.context_codec = FinancialRequestContextCodec()

    @classmethod
    def from_registry(cls, registry: Any) -> "FinancialDashboardSurface":
        """Adapt the deprecated Dashboard-managed registry lifecycle."""

        return cls(
            type(
                "_RegistryContainer",
                (),
                {"registry": registry, "market_data_revision": {}},
            )()
        )

    @property
    def registry(self):
        registry = self.service_container.registry
        if registry is None:
            raise RuntimeError("financial dashboard surface requires a started Runtime")
        return registry

    def decode_request_context(self, value: Any) -> Any:
        return self.context_codec.decode(value)

    def configure_runtime(self, runtime: Any) -> None:
        """Canonical Runtime already registered tools through capabilities."""

    @asynccontextmanager
    async def lifespan(self, app: Any, runtime: Any):
        app.state.financial_registry = self.registry
        app.state.market_data_revision = dict(self.service_container.market_data_revision)
        yield

    def routers(self):
        from .dashboard_routers import (
            dojo_core,
            dojo_folio,
            dojo_mesh,
            dojo_sphere,
            market,
            markets,
            portfolio,
            sector,
            sectors,
            ticker,
            utility,
        )

        return (
            utility.router,
            market.router,
            sector.router,
            ticker.router,
            portfolio.router,
            dojo_core.router,
            dojo_folio.router,
            dojo_mesh.router,
            dojo_sphere.router,
            markets.router,
            sectors.router,
        )


__all__ = ["FinancialDashboardSurface"]
