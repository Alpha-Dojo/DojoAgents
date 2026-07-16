"""Unit tests for market dynamics normalization and date windows."""

from __future__ import annotations

import json
import math

from dojoagents.dashboard.schemas.domain_api import (
    MarketDynamicsEvent,
    MarketDynamicsSummary,
)
from dojoagents.dashboard.schemas.dojo_mesh import BilingualText
from dojoagents.dashboard.services.market_dynamics_service import (
    clear_market_dynamics_cache,
    filter_events_by_date_window,
    normalize_market_dynamics_row,
)


def _event(day: str, idx: int = 0) -> MarketDynamicsEvent:
    return MarketDynamicsEvent(
        id=f"{day}__{idx}",
        event_time=f"{day}T12:00:00+08:00",
        trading_date=day,
        event_summary=MarketDynamicsSummary(
            headline=BilingualText(zh="t", en="t"),
            content=BilingualText(zh="c", en="c"),
            source=BilingualText(zh="s", en="s"),
            category="market_structure",
            surprise="expected",
        ),
        sector_impacts=[],
    )


def test_normalize_market_dynamics_row_parses_json_strings() -> None:
    row = {
        "event_time": "2025-02-25 21:00:00+00:00",
        "event_summary": json.dumps(
            {
                "headline": {"zh": "标题", "en": "Headline"},
                "content": {"zh": "内容", "en": "Body"},
                "source": {"zh": "来源", "en": "Source"},
                "category": "market_structure",
                "surprise": "significant",
            }
        ),
        "sector_impacts": json.dumps(
            [
                {
                    "sector_id": "89/105/108",
                    "sector_name": {"zh": "挖矿", "en": "Mining"},
                    "affected_markets": ["us", "CN"],
                    "direction": "Negative",
                    "reason": "down",
                }
            ]
        ),
        "sectors_without_news": "nan",
    }

    event = normalize_market_dynamics_row(row, 3)
    assert event is not None
    assert event.trading_date == "2025-02-25"
    assert event.event_summary.category == "market_structure"
    assert event.event_summary.surprise == "significant"
    assert event.event_summary.headline.en == "Headline"
    assert len(event.sector_impacts) == 1
    assert event.sector_impacts[0].sector_id == "89/105/108"
    assert event.sector_impacts[0].affected_markets == ["us", "cn"]
    assert event.id.endswith("__3")


def test_normalize_market_dynamics_row_handles_nan_impacts() -> None:
    row = {
        "event_time": "2026-07-10T14:30:00+00:00",
        "event_summary": {
            "headline": {"zh": "A", "en": "A"},
            "content": {"zh": "B", "en": "B"},
            "source": {"zh": "C", "en": "C"},
            "category": "geo_military",
            "surprise": "slight",
        },
        "sector_impacts": float("nan") if True else None,
    }
    assert math.isnan(row["sector_impacts"])
    event = normalize_market_dynamics_row(row, 0)
    assert event is not None
    assert event.sector_impacts == []
    assert event.event_summary.category == "geo_military"


def test_filter_events_by_date_window_flags() -> None:
    clear_market_dynamics_cache()
    events = [
        _event("2026-07-01"),
        _event("2026-07-05"),
        _event("2026-07-10"),
        _event("2026-07-15"),
    ]
    windowed, before, after = filter_events_by_date_window(
        events,
        start_date="2026-07-05",
        end_date="2026-07-10",
    )
    assert [e.trading_date for e in windowed] == ["2026-07-05", "2026-07-10"]
    assert before is True
    assert after is True

    all_events, before2, after2 = filter_events_by_date_window(events)
    assert len(all_events) == 4
    assert before2 is False
    assert after2 is False
