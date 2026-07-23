"""Financial contributions consumed by the generic Dashboard app factory."""

from __future__ import annotations

from typing import Any


class FinancialDashboardSurface:
    def __init__(self, service_container: Any) -> None:
        self.service_container = service_container

    @property
    def registry(self):
        registry = self.service_container.registry
        if registry is None:
            raise RuntimeError("financial dashboard surface requires a started Runtime")
        return registry

    def routers(self):
        from dojoagents.dashboard.routers import (
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
        )

        return (
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
