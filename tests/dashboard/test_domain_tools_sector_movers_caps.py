from __future__ import annotations

from dojoagents.dashboard.services.sector_movers_ranking import (
    DEFAULT_SECTOR_MOVERS_MIN_TOTAL_MARKET_CAP,
)
from dojoagents.dashboard.tools.domain_tools import _resolve_sector_movers_min_cap_by_market


def test_sector_movers_min_caps_default_to_ui_200yi() -> None:
    caps = _resolve_sector_movers_min_cap_by_market({})
    assert caps == {
        "us": DEFAULT_SECTOR_MOVERS_MIN_TOTAL_MARKET_CAP,
        "sh": DEFAULT_SECTOR_MOVERS_MIN_TOTAL_MARKET_CAP,
        "hk": DEFAULT_SECTOR_MOVERS_MIN_TOTAL_MARKET_CAP,
    }


def test_sector_movers_min_caps_explicit_zero_disables_floor() -> None:
    assert _resolve_sector_movers_min_cap_by_market(
        {"min_cap_us": 0, "min_cap_cn": 0, "min_cap_hk": 0}
    ) is None


def test_sector_movers_min_caps_partial_override() -> None:
    caps = _resolve_sector_movers_min_cap_by_market({"min_cap_us": 5e10})
    assert caps == {
        "us": 5e10,
        "sh": DEFAULT_SECTOR_MOVERS_MIN_TOTAL_MARKET_CAP,
        "hk": DEFAULT_SECTOR_MOVERS_MIN_TOTAL_MARKET_CAP,
    }
