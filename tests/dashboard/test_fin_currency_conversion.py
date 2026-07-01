from __future__ import annotations

import pytest

from dojoagents.dashboard.services.fin_currency_conversion import (
    chained_conversion_factor,
    required_forex_symbols,
)


def test_required_forex_symbols_fetches_cross_pairs_for_cny_to_usd() -> None:
    rows = [{"currency": "CNY", "report_date": "2026-03-31"}]
    assert required_forex_symbols(rows, market="us") == ["HKDCNY", "HKDUSD", "USDCNY"]


def test_required_forex_symbols_fetches_cross_pairs_for_cny_to_hkd() -> None:
    rows = [{"currency": "CNY", "report_date": "2026-03-31"}]
    assert required_forex_symbols(rows, market="hk") == ["HKDCNY", "HKDUSD", "USDCNY"]


def test_chained_conversion_factor_cny_to_hkd_via_hkdcny() -> None:
    factor = chained_conversion_factor("CNY", "HKD", {"HKDCNY": 0.92})
    assert factor == pytest.approx(1.0 / 0.92)


def test_chained_conversion_factor_cny_to_hkd_triangulates_when_hkdcny_missing() -> None:
    factor = chained_conversion_factor(
        "CNY",
        "HKD",
        {"USDCNY": 7.2, "HKDUSD": 0.128},
    )
    assert factor == pytest.approx((1.0 / 7.2) / 0.128)
