"""Dashboard-owned composition of an embedded Agent Runtime."""

from __future__ import annotations

from typing import Any

from dojoagents.agent.runtime import Runtime
from dojoagents.harnesses.built_in.financial.harness import (
    FINANCIAL_SERVICE_ID,
)
from dojoagents.harnesses.lifecycle import ExternalServiceBinding

from .financial_agent_backend import DashboardFinancialAgentBackend


async def create_embedded_runtime(config_store: Any, app_services: Any) -> Runtime:
    backend = DashboardFinancialAgentBackend(app_services)
    return await Runtime.create(
        config_store,
        host="dashboard",
        service_bindings={
            FINANCIAL_SERVICE_ID: ExternalServiceBinding(
                backend,
                runtime_owns_lifecycle=False,
            )
        },
    )


__all__ = ["create_embedded_runtime"]
