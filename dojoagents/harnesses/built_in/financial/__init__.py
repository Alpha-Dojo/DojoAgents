"""Built-in financial Harness public API.

Exports are resolved lazily so importing one financial component does not
eagerly construct the complete Harness dependency graph.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_EXPORTS = {
    "FINANCIAL_SERVICE_ID": (".harness", "FINANCIAL_SERVICE_ID"),
    "FinancialHarness": (".harness", "FinancialHarness"),
    "create_harness": (".harness", "create_harness"),
    "FinancialHarnessConfig": (".config", "FinancialHarnessConfig"),
    "FinancialSDKConfig": (".config", "FinancialSDKConfig"),
    "FinancialTasksConfig": (".config", "FinancialTasksConfig"),
    "FinancialToolBackend": (".backends", "FinancialToolBackend"),
    "SDKFinancialToolBackend": (".backends", "SDKFinancialToolBackend"),
    "HTTPFinancialToolBackend": (".backends", "HTTPFinancialToolBackend"),
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
