from .legacy.portfolio import PortfolioTaskHarness

from ..state import _legacy_state


class PortfolioToolRepairPolicy:
    def __init__(self) -> None:
        self._legacy = PortfolioTaskHarness()

    async def transform_calls(self, calls, context):
        return tuple(self._legacy.repair_tool_calls(list(calls), _legacy_state(context)))


__all__ = ["PortfolioToolRepairPolicy"]
