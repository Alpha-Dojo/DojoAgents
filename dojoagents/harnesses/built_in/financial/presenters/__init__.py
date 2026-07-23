"""Financial presenter public API with cycle-safe lazy exports."""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "FinancialResultPresenter": ("._adapter", "FinancialResultPresenter"),
    "EXECUTE_CODE_RESULT_KINDS": (".execute_code", "EXECUTE_CODE_RESULT_KINDS"),
    "MARKET_RESULT_KINDS": (".market", "MARKET_RESULT_KINDS"),
    "PORTFOLIO_RESULT_KINDS": (".portfolio", "PORTFOLIO_RESULT_KINDS"),
    "FinancialResultProjector": (".projector", "FinancialResultProjector"),
    "SECTOR_RESULT_KINDS": (".sector", "SECTOR_RESULT_KINDS"),
    "TICKER_RESULT_KINDS": (".ticker", "TICKER_RESULT_KINDS"),
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc
    value = getattr(import_module(module_name, __name__), attribute)
    globals()[name] = value
    return value
