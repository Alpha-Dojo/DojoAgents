from __future__ import annotations

from dojoagents.dashboard.services.fin_currency_conversion import required_forex_symbols


def test_required_forex_symbols_uses_gateway_usdcny_for_cny_to_usd() -> None:
    rows = [{"currency": "CNY", "report_date": "2026-03-31"}]
    assert required_forex_symbols(rows, market="us") == ["USDCNY"]
