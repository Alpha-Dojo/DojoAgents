"""Unit tests for attribution factor local filters and locale projection."""

from __future__ import annotations

import json

from dojoagents.dashboard.services.attribution_factor_service import (
    filter_attribution_factor_rows,
    normalize_attribution_factor_row,
)


def _row(**overrides: object) -> dict:
    base: dict = {
        "event_time": "2026-07-22T15:30:00+08:00",
        "claim": {"zh": "中文主张", "en": "EN claim"},
        "mechanism": {"zh": "中文机制", "en": "EN mech"},
        "sector_id": "1/9/10",
        "market": "cn",
        "factor_topic": "policy_reg",
        "role": "explains_move",
        "price_direction": "up",
        "importance": "high",
        "affected_tickers": ["600000"],
        "evidence": [{"quote": "q", "url": "https://x", "title": "t"}],
    }
    base.update(overrides)
    return base


def test_normalize_projects_locale_and_parses_json_strings() -> None:
    row = _row(
        claim=json.dumps({"zh": "中", "en": "EN"}),
        mechanism=json.dumps({"zh": "机", "en": "M"}),
        evidence=json.dumps([{"quote": "quote-only"}]),
    )
    item = normalize_attribution_factor_row(row, locale="en")
    assert item is not None
    assert item.claim == "EN"
    assert item.mechanism == "M"
    assert item.evidence[0].quote == "quote-only"


def test_normalize_drops_missing_event_time() -> None:
    assert normalize_attribution_factor_row(_row(event_time=""), locale="zh") is None
    assert normalize_attribution_factor_row(_row(event_time="NaT"), locale="zh") is None


def test_filter_exact_sector_and_date_window() -> None:
    rows = [
        _row(sector_id="1/9/10", event_time="2026-07-20T10:00:00+08:00", claim={"zh": "a", "en": "a"}),
        _row(sector_id="1/9/10", event_time="2026-07-22T10:00:00+08:00", claim={"zh": "b", "en": "b"}),
        _row(sector_id="1/18/19", event_time="2026-07-22T10:00:00+08:00", claim={"zh": "c", "en": "c"}),
        _row(sector_id="1/9/10", event_time="2026-07-25T10:00:00+08:00", claim={"zh": "d", "en": "d"}),
        _row(sector_id="1/9/10", event_time="", claim={"zh": "e", "en": "e"}),
    ]
    items = filter_attribution_factor_rows(
        rows,
        sector_id="1/9/10",
        start_date="2026-07-21",
        end_date="2026-07-23",
        locale="zh",
    )
    assert [item.claim for item in items] == ["b"]
