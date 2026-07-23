from __future__ import annotations

from dojoagents.harnesses.built_in.financial.services.market_trading_calendar import (
    canonical_market,
    is_trading_day,
    open_markets_on,
    trading_days_for_market,
)


def test_canonical_market_maps_sh_alias_to_cn() -> None:
    assert canonical_market("cn") == "cn"
    assert canonical_market("SH") == "cn"
    assert canonical_market("us") == "us"


def test_trading_days_accept_cn_and_sh_alias() -> None:
    cn_days = trading_days_for_market("cn", "2026-07-13", "2026-07-13")
    sh_days = trading_days_for_market("sh", "2026-07-13", "2026-07-13")
    assert cn_days == sh_days
    assert cn_days == ["2026-07-13"]


def test_is_trading_day_weekend_closed() -> None:
    # 2026-07-12 is Sunday — closed for us/cn/hk.
    assert is_trading_day("us", "2026-07-12") is False
    assert is_trading_day("cn", "2026-07-12") is False
    assert is_trading_day("hk", "2026-07-12") is False
    assert open_markets_on("2026-07-12") == []


def test_open_markets_on_weekday() -> None:
    # 2026-07-13 is Monday — at least one equity market should be open.
    open_markets = open_markets_on("2026-07-13")
    assert open_markets
    assert set(open_markets) <= {"us", "cn", "hk"}
