from __future__ import annotations

import pytest
from pydantic import ValidationError

from dojoagents.dashboard.schemas.dojo_mesh import BilingualText
from dojoagents.dashboard.schemas.event_sector_prediction import (
    EVENT_INDUSTRY_CATALOG,
    EventAffectedSector,
    EventCategory,
    EventIndustryDef,
    EventRecord,
    SurpriseDaySnapshot,
    SurpriseDistribution,
    SurpriseRealization,
    default_calibration_bucket,
    resolve_event_industry,
)


def _industry(en: str) -> EventIndustryDef:
    return resolve_event_industry(en=en)


def _day(t_offset: int, as_of: str, *, beat: float, meet: float, miss: float) -> SurpriseDaySnapshot:
    return SurpriseDaySnapshot(
        t_offset=t_offset,
        as_of=as_of,
        distribution=SurpriseDistribution(p_beat=beat, p_meet=meet, p_miss=miss),
    )


def test_industry_catalog_has_seventeen_bilingual_entries() -> None:
    assert len(EVENT_INDUSTRY_CATALOG) == 17
    assert len({item.name.en for item in EVENT_INDUSTRY_CATALOG}) == 17
    assert len({item.name.zh for item in EVENT_INDUSTRY_CATALOG}) == 17


def test_resolve_event_industry() -> None:
    assert resolve_event_industry(en="Semiconductors").name.zh == "半导体"
    assert resolve_event_industry(zh="银行").name.en == "Banking"
    with pytest.raises(ValueError, match="unknown event industry"):
        resolve_event_industry(en="Fake")


def test_surprise_distribution_must_sum_to_one() -> None:
    ok = SurpriseDistribution(p_beat=0.4, p_meet=0.35, p_miss=0.25)
    assert ok.p_beat == pytest.approx(0.4)
    with pytest.raises(ValidationError, match="sum to 1"):
        SurpriseDistribution(p_beat=0.5, p_meet=0.5, p_miss=0.2)


def test_surprise_day_offset_from_t_minus_5() -> None:
    snap = _day(-5, "2026-07-26", beat=0.2, meet=0.5, miss=0.3)
    assert snap.t_offset == -5
    with pytest.raises(ValidationError):
        SurpriseDaySnapshot(
            t_offset=-6,
            as_of="2026-07-25",
            distribution=SurpriseDistribution(p_beat=0.3, p_meet=0.4, p_miss=0.3),
        )


def test_economic_event_with_daily_surprise_path() -> None:
    path = [
        _day(-5, "2026-07-26", beat=0.2, meet=0.5, miss=0.3),
        _day(-4, "2026-07-27", beat=0.22, meet=0.48, miss=0.3),
        _day(-3, "2026-07-28", beat=0.25, meet=0.45, miss=0.3),
    ]
    event = EventRecord(
        family="economic",
        title="China's official manufacturing PMI in July",
        market="cn",
        event_datetime="2026-07-31T01:30:00Z",
        categories=[EventCategory(action="econ_growth", is_primary=True)],
        affected_sectors=[
            EventAffectedSector(
                market="cn",
                level1_id="89",
                level2_id="105",
                level3_id="108",
                sector_name=BilingualText(zh="工业", en="Industrials"),
                change_percent=1.2,
            )
        ],
        surprise_path=path,
        created_at="2026-08-20T00:00:00Z",
    )
    assert event.surprise_path is not None
    assert len(event.surprise_path) == 3
    assert event.surprise_path[0].t_offset == -5
    assert event.affected_sectors[0].change_percent == pytest.approx(1.2)
    assert event.realized is None


def test_earnings_event_uses_same_daily_surprise_model() -> None:
    industry = _industry("Semiconductors")
    event = EventRecord(
        family="earnings",
        title="NVIDIA Q2 FY2027",
        market="us",
        event_datetime="2026-08-26T20:00:00Z",
        symbol="NVDA",
        categories=[
            EventCategory(action="earnings", industry=industry, is_primary=True),
            EventCategory(
                action="earnings",
                industry=_industry("Compute Infrastructure"),
                is_primary=False,
            ),
        ],
        surprise_path=[
            _day(-5, "2026-08-21", beat=0.5, meet=0.3, miss=0.2),
            _day(-1, "2026-08-25", beat=0.55, meet=0.25, miss=0.2),
            _day(0, "2026-08-26", beat=0.6, meet=0.25, miss=0.15),
        ],
        realized=SurpriseRealization(outcome="beat"),
        status="resolved",
        created_at="2026-08-20T00:00:00Z",
    )
    assert event.surprise_path is not None
    assert event.surprise_path[-1].t_offset == 0
    assert event.realized is not None
    assert event.realized.outcome == "beat"
    assert event.categories[0].industry is not None
    assert default_calibration_bucket("earnings", event.categories[0].industry) == "earnings x Semiconductors"


def test_ipo_has_no_surprise_path() -> None:
    industry = _industry("Automobiles")
    event = EventRecord(
        family="ipo",
        title="绿控传动新股今日上市",
        market="cn",
        event_datetime="2026-08-19T16:00:00Z",
        symbol="301655.SZ",
        categories=[EventCategory(action="ipo_listing", industry=industry, is_primary=True)],
        surprise_path=None,
        created_at="2026-08-20T00:00:00Z",
    )
    assert event.surprise_path is None
    assert event.affected_sectors == []


def test_ipo_listing_bucket_only_for_matrix_industries() -> None:
    assert (
        default_calibration_bucket("ipo_listing", _industry("Semiconductors"))
        == "ipo x listing x Semiconductors"
    )
    assert default_calibration_bucket("ipo_listing", _industry("Automobiles")) is None


def test_categories_bounded_to_one_or_two() -> None:
    with pytest.raises(ValidationError):
        EventRecord(
            family="earnings",
            title="t",
            market="us",
            event_datetime="2026-08-26T00:00:00Z",
            categories=[
                EventCategory(action="earnings", industry=_industry("Banking"), is_primary=True),
                EventCategory(action="earnings", industry=_industry("Insurance"), is_primary=False),
                EventCategory(action="earnings", industry=_industry("Automobiles"), is_primary=False),
            ],
            created_at="2026-08-20T00:00:00Z",
        )


def test_affected_sectors_record_l3_path_and_return() -> None:
    row = EventAffectedSector(
        market="us",
        level1_id="1",
        level2_id="9",
        level3_id="10",
        sector_name=BilingualText(zh="半导体", en="Semiconductors"),
        change_percent=-2.35,
    )
    assert row.market == "us"
    assert row.level3_id == "10"
    assert row.sector_name.en == "Semiconductors"
    assert row.change_percent == pytest.approx(-2.35)
