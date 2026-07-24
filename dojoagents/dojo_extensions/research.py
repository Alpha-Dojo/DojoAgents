from __future__ import annotations

from typing import Any

from dojoagents.dojo_extensions.base import DashboardCardSpec, ExtensionHealth


class DojoResearchExtension:
    name = "dojo_research"
    version = "0.1"

    def health(self) -> ExtensionHealth:
        return ExtensionHealth(ok=True)

    def tool_specs(self) -> list:
        return []

    def dashboard_cards(self) -> list[DashboardCardSpec]:
        return [DashboardCardSpec(id="research", title="Research Artifacts")]

    def prompt_context(self, request_context: Any) -> str:
        return "Dojo research extension available for analysis artifact lookup."
