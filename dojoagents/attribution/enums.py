"""Small enums for AttributionFactor."""

from __future__ import annotations

from enum import Enum


class FactorTopic(str, Enum):
    """Required topic label for an AttributionFactor.

    Topics are mutually exclusive *subjects*. Do not use a topic as a synonym for
    "risk" or "catalyst" — that belongs in FactorRole. Topic-specific payload goes
    in ``attrs``.
    """

    EARNINGS = "earnings"
    CORPORATE_ACTION = "corporate_action"
    POLICY_REG = "policy_reg"
    DEMAND_SUPPLY = "demand_supply"
    PRODUCT_TECH = "product_tech"
    CAPITAL_MARKET = "capital_market"
    MARKET_STRUCTURE = "market_structure"
    ANALYST_REVISION = "analyst_revision"
    EXOGENOUS_SHOCK = "exogenous_shock"
    MACRO = "macro"


class FactorRole(str, Enum):
    """How this factor is used in attribution (orthogonal to FactorTopic).

    Absolute price of the asset is the direction benchmark (not short-PnL view).

    - explains_move: causal contribution to the observed move (same OR opposite
      sign vs the print — use price_direction for the factor's own prior;
      counteracting forces are still explains_move with opposite price_direction)
    - open_risk: not-fully-priced downside scenario (may later promote to explains_move)
    - open_catalyst: not-fully-priced upside scenario (may later promote)
    - context: background only; not a primary cause
    """

    EXPLAINS_MOVE = "explains_move"
    OPEN_RISK = "open_risk"
    OPEN_CATALYST = "open_catalyst"
    CONTEXT = "context"


def parse_factor_role(value: object, default: FactorRole | None = None) -> FactorRole:
    """Parse role."""

    if value is None or value == "":
        return default if default is not None else FactorRole.EXPLAINS_MOVE
    if isinstance(value, FactorRole):
        return value
    key = str(value).strip().lower()
    try:
        return FactorRole(key)
    except ValueError as exc:
        allowed = ", ".join(r.value for r in FactorRole)
        raise ValueError(f"invalid FactorRole={value!r}; allowed: {allowed}") from exc


class PriceDirection(str, Enum):
    """Prior on *asset price* impact for the factor's entity.

    NOT the tone of the event itself — that is Stance.
    Canonical values only: up | down | mixed.
    Omit the field (None) when unknown.
    """

    UP = "up"
    DOWN = "down"
    MIXED = "mixed"


def parse_price_direction(
    value: object, default: PriceDirection | None = None
) -> PriceDirection | None:
    """Parse price direction. Missing/empty → default (usually None). Bad labels raise."""

    if value is None or value == "":
        return default
    if isinstance(value, PriceDirection):
        return value
    key = str(value).strip().lower()
    try:
        return PriceDirection(key)
    except ValueError as exc:
        allowed = ", ".join(d.value for d in PriceDirection)
        raise ValueError(f"invalid PriceDirection={value!r}; allowed: {allowed}") from exc


class Importance(str, Enum):
    """How material this factor is for explaining / ranking the move."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PayloadStatus(str, Enum):
    """Lifecycle after extraction / enrichment.

    - draft: incomplete (not persistable as product record)
    - ready: usable for attribution / UI
    - rejected: hallucination / false positive / failed review — terminal discard
    """

    DRAFT = "draft"
    READY = "ready"
    REJECTED = "rejected"


class MarketCode(str, Enum):
    """Job / factor market scope (caller-injected)."""

    US = "us"
    CN = "cn"
    HK = "hk"


class Stance(str, Enum):
    """Qualitative tone of the *event / fundamental itself* — not price impact."""

    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    MIXED = "mixed"
