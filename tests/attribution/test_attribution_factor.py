from __future__ import annotations

import pytest
from pydantic import ValidationError

from dojoagents.attribution import (
    AttributionFactor,
    FactorTopic,
    FactorRole,
    Importance,
    PayloadStatus,
    PriceDirection,
    parse_factor_role,
    parse_price_direction,
)


def test_model_validate_roundtrip():
    factor = AttributionFactor.model_validate(
        {
            "claim": {"zh": "龙头业绩不及预期拖累白酒板块"},
            "sector_id": "liquor",
            "market": "cn",
            "factor_topic": "earnings",
            "event_time": "2026-07-22T15:30:00Z",
            "affected_tickers": ["600519.SH", "000858.SZ"],
            "evidence": [
                {
                    "quote": "公司公告显示二季度营收低于此前市场预期",
                    "url": "https://example.com/a",
                }
            ],
            "role": "explains_move",
            "price_direction": "down",
            "importance": "high",
            "attrs": {
                "event_kind": "earnings_release",
                "fiscal_period": "2026Q2",
                "metrics": [{"name": "营收", "raw_text": "营收不及市场预期"}],
            },
            "payload_status": "ready",
        }
    )
    assert factor.sector_id == "liquor"
    assert factor.factor_topic == FactorTopic.EARNINGS
    assert factor.affected_tickers == ("600519.SH", "000858.SZ")
    assert len(factor.evidence) == 1
    assert factor.attrs["event_kind"] == "earnings_release"
    loaded = AttributionFactor.model_validate(factor.model_dump(mode="json"))
    assert loaded.factor_topic == FactorTopic.EARNINGS
    assert loaded.attrs["fiscal_period"] == "2026Q2"


def test_parse_factor_role_vocab():
    assert parse_factor_role("explains_move") == FactorRole.EXPLAINS_MOVE
    assert parse_factor_role(None) == FactorRole.EXPLAINS_MOVE
    with pytest.raises(ValueError, match="invalid FactorRole"):
        parse_factor_role("offsets_move")


def test_parse_price_direction_canonical_only():
    assert parse_price_direction("up") == PriceDirection.UP
    assert parse_price_direction(None) is None
    with pytest.raises(ValueError, match="invalid PriceDirection"):
        parse_price_direction("+")


def test_factor_topic_required():
    with pytest.raises(ValidationError):
        AttributionFactor.model_validate(
            {
                "claim": {"zh": "缺家族"},
                "sector_id": "ai_chips",
                "market": "us",
                "evidence": [{"quote": "quote long enough here"}],
                "payload_status": "ready",
            }
        )


def test_mechanism_and_topic():
    factor = AttributionFactor.model_validate(
        {
            "factor_topic": "exogenous_shock",
            "claim": {"zh": "工厂火灾冲击供给"},
            "sector_id": "semiconductor_equipment",
            "market": "us",
            "affected_tickers": ["ACCT"],
            "evidence": [{"quote": "A fire disrupted production at the main plant"}],
            "mechanism": {"en": "plant fire disrupted wafer supply"},
            "role": "explains_move",
            "price_direction": "down",
            "payload_status": "ready",
            "attrs": {"shock_type": "accident", "severity_hint": "high"},
        }
    )
    assert factor.factor_topic == FactorTopic.EXOGENOUS_SHOCK
    assert factor.mechanism is not None
    assert "wafer" in (factor.mechanism.zh or factor.mechanism.en)
    assert factor.attrs["shock_type"] == "accident"


def test_evidence_list():
    factor = AttributionFactor.model_validate(
        {
            "claim": {"zh": "政策落地提振板块预期"},
            "sector_id": "new_energy",
            "market": "cn",
            "factor_topic": "policy_reg",
            "evidence": [
                {"quote": "发改委发布新能源补贴细则", "url": "https://example.com/1"},
                {"quote": "多家券商同步上调行业评级至增持"},
            ],
            "payload_status": "ready",
        }
    )
    assert len(factor.evidence) == 2
    assert factor.evidence[0].url == "https://example.com/1"


def test_model_copy_updates_status():
    factor = AttributionFactor.model_validate(
        {
            "claim": {"zh": "发布财报"},
            "sector_id": "ai_chips",
            "market": "us",
            "factor_topic": "earnings",
            "evidence": [{"quote": "Apple reported fiscal third-quarter results"}],
            "payload_status": "draft",
        }
    )
    assert factor.payload_status == PayloadStatus.DRAFT
    ready = factor.model_copy(
        update={"payload_status": PayloadStatus.READY, "importance": Importance.LOW}
    )
    assert ready.payload_status == PayloadStatus.READY
    assert ready.importance == Importance.LOW


def test_empty_claim_rejected():
    with pytest.raises(ValidationError, match="claim"):
        AttributionFactor.model_validate(
            {
                "claim": {"zh": "", "en": ""},
                "sector_id": "ai_chips",
                "market": "us",
                "factor_topic": "earnings",
            }
        )
