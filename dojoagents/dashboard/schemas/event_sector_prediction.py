"""Event storage base units: content + classification.

economic / earnings carry a daily surprise path P(beat/meet/miss) from T-5..T0.
ipo has no P this round (surprise_path stays None).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from dojoagents.dashboard.schemas.dojo_mesh import BilingualText

EventFamily = Literal["economic", "earnings", "ipo"]
EventAction = Literal[
    "econ_rate_policy",
    "econ_inflation",
    "econ_employment",
    "econ_growth",
    "econ_credit",
    "econ_trade",
    "econ_housing",
    "econ_other",
    "earnings",
    "ipo_listing",
]
EventStatus = Literal["open", "resolved", "expired"]
RealizedOutcome = Literal["beat", "meet", "miss"]

_PROB_SUM_TOLERANCE = 1e-6

_IPO_LISTING_BUCKET_INDUSTRIES_EN: frozenset[str] = frozenset(
    {
        "Semiconductors",
        "Software & AI Services",
        "Compute Infrastructure",
    }
)


class EventIndustryDef(BaseModel):
    """Standard industry for earnings / IPO classification. Not taxonomy L2."""

    model_config = ConfigDict(extra="forbid")

    name: BilingualText
    definition: BilingualText


EVENT_INDUSTRY_CATALOG: tuple[EventIndustryDef, ...] = (
    EventIndustryDef(
        name=BilingualText(zh="半导体", en="Semiconductors"),
        definition=BilingualText(
            zh="集成电路设计、制造、封测及半导体设备与材料等；以芯片产能、制程与 AI/算力需求为定价主轴。",
            en="IC design, fabrication, packaging/testing, and semi equipment/materials; priced on capacity, process nodes, and AI/compute demand.",
        ),
    ),
    EventIndustryDef(
        name=BilingualText(zh="软件与AI服务", en="Software & AI Services"),
        definition=BilingualText(
            zh="企业软件、云与 AI 应用/服务；关键变量多为经常性收入、云增速与 AI 变现。",
            en="Enterprise software, cloud and AI applications/services; keyed on recurring revenue, cloud growth, and AI monetization.",
        ),
    ),
    EventIndustryDef(
        name=BilingualText(zh="算力基础设施", en="Compute Infrastructure"),
        definition=BilingualText(
            zh="服务器、数据中心、算力硬件与相关基础设施；订单与资本开支指引驱动板块联动。",
            en="Servers, data centers, and compute hardware/infra; orders and capex guidance drive chain-wide spillovers.",
        ),
    ),
    EventIndustryDef(
        name=BilingualText(zh="消费电子", en="Consumer Electronics"),
        definition=BilingualText(
            zh="智能手机、PC、可穿戴等消费终端及品牌；受产品周期与出货量主导。",
            en="Smartphones, PCs, wearables, and device brands; dominated by product cycles and unit shipments.",
        ),
    ),
    EventIndustryDef(
        name=BilingualText(zh="电子元器件", en="Electronic Components"),
        definition=BilingualText(
            zh="被动元件、显示、光学与电子零部件；定价看产能利用率与价格周期。",
            en="Passives, display, optics, and electronic parts; priced on utilization and component price cycles.",
        ),
    ),
    EventIndustryDef(
        name=BilingualText(zh="银行", en="Banking"),
        definition=BilingualText(
            zh="商业银行等存款贷款机构；息差、信贷增速与资产质量是核心变量。",
            en="Deposit-taking banks; net interest margin, loan growth, and asset quality are core variables.",
        ),
    ),
    EventIndustryDef(
        name=BilingualText(zh="保险", en="Insurance"),
        definition=BilingualText(
            zh="寿险、财险等保险机构；新业务价值与投资端收益主导估值。",
            en="Life and P&C insurers; new-business value and investment returns dominate valuation.",
        ),
    ),
    EventIndustryDef(
        name=BilingualText(zh="证券与资管", en="Securities & Asset Management"),
        definition=BilingualText(
            zh="经纪、投行与资产管理；成交量、自营与管理规模驱动盈利。",
            en="Brokerage, investment banking, and asset managers; driven by volumes, trading, and AUM.",
        ),
    ),
    EventIndustryDef(
        name=BilingualText(zh="制药", en="Pharmaceuticals"),
        definition=BilingualText(
            zh="化学药/生物药研发与商业化；管线进展与研发投入决定事件冲击。",
            en="Chemical/biologic drug R&D and commercialization; pipeline and R&D intensity drive event impact.",
        ),
    ),
    EventIndustryDef(
        name=BilingualText(zh="医疗器械", en="Medical Devices"),
        definition=BilingualText(
            zh="诊疗设备与耗材等；集采、入院与海外拓展影响板块传导。",
            en="Devices and consumables; volume-based procurement, hospital access, and overseas expansion matter.",
        ),
    ),
    EventIndustryDef(
        name=BilingualText(zh="汽车", en="Automobiles"),
        definition=BilingualText(
            zh="整车及核心供应链（含新能源车）；交付量、毛利率与产能是主变量。",
            en="OEMs and core auto supply chain (incl. EV); deliveries, margins, and capacity are primary drivers.",
        ),
    ),
    EventIndustryDef(
        name=BilingualText(zh="食品饮料", en="Food & Beverage"),
        definition=BilingualText(
            zh="食品、饮料与白酒等；量价、渠道库存与毛利率主导。",
            en="Food, beverage, and spirits; volume/price, channel inventory, and margins dominate.",
        ),
    ),
    EventIndustryDef(
        name=BilingualText(zh="互联网媒体", en="Internet Media"),
        definition=BilingualText(
            zh="社交、内容与互联网平台媒体；用户、ARPU 与广告收入是关键变量。",
            en="Social/content and internet platforms; users, ARPU, and ad revenue are key variables.",
        ),
    ),
    EventIndustryDef(
        name=BilingualText(zh="传媒与游戏", en="Media & Gaming"),
        definition=BilingualText(
            zh="影视、出版与游戏等内容娱乐；产品周期与活跃用户驱动。",
            en="Film, publishing, and gaming; product cycles and active users drive performance.",
        ),
    ),
    EventIndustryDef(
        name=BilingualText(zh="能源开采", en="Energy Upstream"),
        definition=BilingualText(
            zh="油气等上游开采；油价联动与资本开支主导板块反应。",
            en="Oil and gas upstream; oil-price linkage and capex dominate sector reaction.",
        ),
    ),
    EventIndustryDef(
        name=BilingualText(zh="金属采矿", en="Metals & Mining"),
        definition=BilingualText(
            zh="金属矿产采选冶；金属价格与产量指引是定价核心。",
            en="Metals mining and processing; metal prices and production guidance are central.",
        ),
    ),
    EventIndustryDef(
        name=BilingualText(zh="房地产", en="Real Estate"),
        definition=BilingualText(
            zh="房地产开发与相关运营；销售回款、拿地与负债率主导风险与弹性。",
            en="Property development and related ops; sales collections, land acquisition, and leverage dominate.",
        ),
    ),
)

_INDUSTRY_BY_EN: dict[str, EventIndustryDef] = {item.name.en: item for item in EVENT_INDUSTRY_CATALOG}
_INDUSTRY_BY_ZH: dict[str, EventIndustryDef] = {item.name.zh: item for item in EVENT_INDUSTRY_CATALOG}


def resolve_event_industry(*, zh: str | None = None, en: str | None = None) -> EventIndustryDef:
    """Look up a catalog industry by Chinese or English name."""
    if en and en in _INDUSTRY_BY_EN:
        return _INDUSTRY_BY_EN[en]
    if zh and zh in _INDUSTRY_BY_ZH:
        return _INDUSTRY_BY_ZH[zh]
    raise ValueError(f"unknown event industry: zh={zh!r} en={en!r}")


def default_calibration_bucket(action: EventAction, industry: EventIndustryDef | None) -> str | None:
    """Derive bucket name; IPO listing only buckets the three matrix-Y industries."""
    if action.startswith("econ_"):
        return f"econ x {action.removeprefix('econ_').replace('_', ' ')}"
    if action == "earnings":
        if industry is None:
            return None
        return f"earnings x {industry.name.en}"
    if action == "ipo_listing":
        if industry is None:
            return None
        if industry.name.en not in _IPO_LISTING_BUCKET_INDUSTRIES_EN:
            return None
        return f"ipo x listing x {industry.name.en}"
    return None


class SurpriseDistribution(BaseModel):
    """One day's P(beat/meet/miss). Shared by economic and earnings."""

    model_config = ConfigDict(extra="forbid")

    p_beat: float = Field(..., ge=0.0, le=1.0)
    p_meet: float = Field(..., ge=0.0, le=1.0)
    p_miss: float = Field(..., ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _sums_to_one(self) -> SurpriseDistribution:
        total = self.p_beat + self.p_meet + self.p_miss
        if abs(total - 1.0) > _PROB_SUM_TOLERANCE:
            raise ValueError("p_beat + p_meet + p_miss must sum to 1")
        return self


class SurpriseDaySnapshot(BaseModel):
    """Surprise P for one calendar day relative to event T0 (from T-5 onward)."""

    model_config = ConfigDict(extra="forbid")

    t_offset: int = Field(..., ge=-5, le=0, description="Days relative to T0; T-5..T0")
    as_of: str = Field(..., min_length=1, description="Calendar date for this snapshot (YYYY-MM-DD)")
    distribution: SurpriseDistribution


class SurpriseRealization(BaseModel):
    """Settled surprise label after the print."""

    model_config = ConfigDict(extra="forbid")

    outcome: RealizedOutcome


class EventCategory(BaseModel):
    """One classification entry. Each event carries 1–2 of these."""

    model_config = ConfigDict(extra="forbid")

    action: EventAction
    industry: Optional[EventIndustryDef] = Field(
        None,
        description="Used for earnings/ipo; leave null for economic",
    )
    is_primary: bool = True


class EventAffectedSector(BaseModel):
    """One L3 taxonomy sector observed when the event lands."""

    model_config = ConfigDict(extra="forbid")

    market: str = Field(..., min_length=1)
    level1_id: str = Field(..., min_length=1)
    level2_id: str = Field(..., min_length=1)
    level3_id: str = Field(..., min_length=1)
    sector_name: BilingualText
    change_percent: float = Field(..., description="Sector return at observation time, in percent")


class EventRecord(BaseModel):
    """Event storage: identity + classification + optional daily surprise path."""

    model_config = ConfigDict(extra="forbid")

    event_datetime: str = Field(..., min_length=1)
    family: EventFamily
    title: str = Field(..., min_length=1)
    market: str = Field(..., min_length=1)
    symbol: Optional[str] = None

    categories: list[EventCategory] = Field(..., min_length=1, max_length=2)
    affected_sectors: list[EventAffectedSector] = Field(default_factory=list)

    surprise_path: Optional[list[SurpriseDaySnapshot]] = Field(
        None,
        description="Daily P from T-5..T0 for economic/earnings; None for ipo",
    )
    realized: Optional[SurpriseRealization] = None

    status: EventStatus = "open"
    created_at: str = Field(..., min_length=1)
    updated_at: Optional[str] = None
