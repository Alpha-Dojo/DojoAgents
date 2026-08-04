"""AttributionFactor — sector-scoped factor schema."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from dojoagents.attribution.enums import (
    FactorTopic,
    FactorRole,
    Importance,
    MarketCode,
    PayloadStatus,
    PriceDirection,
    Stance,
)
from dojoagents.attribution.value_objects import EvidenceSpan, LocaleText


class AttributionFactor(BaseModel):
    """One sector-scoped attribution proposition.

    ``sector_id`` / ``market`` are job context (caller-injected).
    """

    model_config = ConfigDict(frozen=True, extra="ignore", use_enum_values=False)

    claim: LocaleText
    sector_id: str = Field(min_length=1)
    market: MarketCode
    factor_topic: FactorTopic
    event_time: str = Field(min_length=16)
    evidence: tuple[EvidenceSpan, ...] = ()
    affected_tickers: tuple[str, ...] = ()
    role: FactorRole = FactorRole.EXPLAINS_MOVE
    price_direction: PriceDirection | None = None
    importance: Importance | None = None
    mechanism: LocaleText | None = None
    payload_status: PayloadStatus = PayloadStatus.DRAFT
    stance: Stance | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None

    @field_validator("claim")
    @classmethod
    def _claim_nonempty(cls, value: LocaleText) -> LocaleText:
        if not (value.zh or value.en).strip():
            raise ValueError("claim must have zh or en text")
        return value

    @field_validator("event_time")
    @classmethod
    def _event_time_has_clock(cls, value: str) -> str:
        text = str(value or "").strip()
        if "T" not in text or len(text) < 16:
            raise ValueError("event_time must be ISO8601 datetime with time (not date-only)")
        return text
