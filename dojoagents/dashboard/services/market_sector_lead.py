from __future__ import annotations

import re
from typing import Dict, List

from dojoagents.dashboard.services.stock_quote_filter import passes_ticker_market_cap_min, stock_has_quote_volume
from dojoagents.dashboard.services.stock_sector_store import (
    SectorBucket,
    SectorBucketMeta,
    SectorMember,
    StockSectorStore,
    iter_level_3_metas,
)
from dojoagents.dashboard.services.stock_store import StockStore
from dojoagents.dashboard.schemas.stock import Stock
from dojoagents.dashboard.schemas.stock_sector import StockSectorLabel, SectorLevelPath, BilingualLabel
from dojoagents.dashboard.schemas.dojo_mesh import (
    BilingualText,
    DojoMeshSectorsResponse,
    MarketSectorLead,
    SectorItem,
    SectorMemberItem,
)

MAX_SECTOR_MEMBERS = 40

MARKETS = ("sh", "hk", "us")


def link_key_from_concept_code(concept_code: str) -> str | None:
    match = re.search(r"\.L3\.(.+)$", concept_code, re.IGNORECASE)
    return match.group(1) if match else None


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return slug or "unknown"


def concept_code_for(market: str, meta: SectorBucketMeta) -> str:
    slug = slugify(meta.en or meta.zh)
    return f"{market.upper()}.{meta.level.upper()}.{slug}"


def _bucket_key(meta: SectorBucketMeta) -> str:
    return f"{meta.level}|{meta.zh}|{meta.en}"


def _stock_bilingual_name(stock: Stock) -> BilingualText:
    en = (stock.long_name or stock.short_name or stock.ticker).strip()
    quote = stock.stock_quote
    if stock.market in ("sh", "hk") and quote and quote.name:
        zh = quote.name.strip()
    else:
        zh = (stock.short_name or stock.long_name or stock.ticker).strip()
    return BilingualText(zh=zh, en=en)


def _sector_avg_market_cap(members: List[SectorMember]) -> float:
    if not members:
        return 0.0
    return sum(m.market_cap for m in members) / len(members)


def _sector_lead_sort_score(avg_market_cap: float, change_percent: float) -> float:
    return avg_market_cap * change_percent


def _market_cap_weighted_change(members: List[SectorMember]) -> float:
    total_cap = sum(m.market_cap for m in members)
    if total_cap <= 0:
        return sum(m.change_percent for m in members) / len(members)
    return sum(m.change_percent * m.market_cap for m in members) / total_cap


def _weighting_members(market: str, members: List[SectorMember]) -> List[SectorMember]:
    return [m for m in members if passes_ticker_market_cap_min(market, m.market_cap)]


def _build_buckets(market: str, stocks: List[Stock], sector_store: StockSectorStore) -> Dict[str, SectorBucket]:
    buckets: Dict[str, SectorBucket] = {}

    for stock in stocks:
        quote = stock.stock_quote
        if quote is None or not stock_has_quote_volume(stock):
            continue

        sector_zh = stock.sector or ""
        industry_zh = stock.industry or ""
        if not sector_zh and not industry_zh:
            continue

        label = StockSectorLabel(
            ticker=stock.ticker,
            market=market,
            primary=SectorLevelPath(
                level_1=BilingualLabel(zh="Market", en="Market"), level_2=BilingualLabel(zh=sector_zh, en=sector_zh), level_3=BilingualLabel(zh=industry_zh, en=industry_zh)
            ),
            secondary=[],
        )

        names = _stock_bilingual_name(stock)
        member = SectorMember(
            ticker=stock.ticker,
            name_zh=names.zh,
            name_en=names.en,
            last_price=quote.last_price,
            change_percent=quote.change_percent,
            market_cap=quote.market_cap,
            pe=quote.pe,
        )

        for meta in iter_level_3_metas(label):
            key = _bucket_key(meta)
            bucket = buckets.get(key)
            if bucket is None:
                bucket = SectorBucket(meta=meta)
                buckets[key] = bucket
            if any(existing.ticker == member.ticker for existing in bucket.members):
                continue
            bucket.members.append(member)

    return buckets


def _aggregate_bucket(market: str, bucket: SectorBucket) -> SectorItem | None:
    if not bucket.members:
        return None

    weighted_members = _weighting_members(market, bucket.members)
    if weighted_members:
        weighted_change = _market_cap_weighted_change(weighted_members)
        avg_market_cap = _sector_avg_market_cap(weighted_members)
        display_members = weighted_members
    else:
        weighted_change = 0.0
        avg_market_cap = 0.0
        display_members = []

    sorted_members = sorted(
        display_members,
        key=lambda m: m.change_percent,
        reverse=True,
    )
    top_by_abs = sorted(
        display_members,
        key=lambda m: abs(m.change_percent),
        reverse=True,
    )[:3]
    sample_tickers = [m.ticker for m in top_by_abs]
    member_items = [
        SectorMemberItem(
            ticker=m.ticker,
            name=BilingualText(zh=m.name_zh, en=m.name_en),
            last_price=round(m.last_price, 4),
            market_cap=m.market_cap,
            change_percent=round(m.change_percent, 2),
        )
        for m in sorted_members[:MAX_SECTOR_MEMBERS]
    ]

    item = SectorItem(
        concept_code=concept_code_for(market, bucket.meta),
        name=BilingualText(zh=bucket.meta.zh, en=bucket.meta.en),
        change_percent=round(weighted_change, 2),
        avg_market_cap=avg_market_cap,
        strength=0.0,
        sample_tickers=sample_tickers,
        member_count=len(display_members),
        members=member_items,
    )
    return item


def _apply_strength(items: List[SectorItem]) -> List[SectorItem]:
    if not items:
        return items
    max_abs = max(abs(_sector_lead_sort_score(item.avg_market_cap, item.change_percent)) for item in items) or 1.0
    return [
        item.model_copy(
            update={
                "strength": round(
                    abs(_sector_lead_sort_score(item.avg_market_cap, item.change_percent)) / max_abs * 100,
                    1,
                )
            }
        )
        for item in items
    ]


def build_market_sectors(
    market: str,
    stock_store: StockStore,
    sector_store: StockSectorStore,
) -> List[SectorItem]:
    stocks = stock_store.list_market(market)
    buckets = _build_buckets(market, stocks, sector_store)
    sectors: List[SectorItem] = []
    for bucket in buckets.values():
        item = _aggregate_bucket(market, bucket)
        if item is None:
            continue
        sectors.append(item)
    return sectors


def lookup_sector_by_link_key(
    market: str,
    link_key: str,
    stock_store: StockStore,
    sector_store: StockSectorStore,
) -> SectorItem | None:
    needle = link_key.lower()
    for item in build_market_sectors(market, stock_store, sector_store):
        item_key = link_key_from_concept_code(item.concept_code)
        if item_key and item_key.lower() == needle:
            return item
    return None


def lookup_cross_market_sectors(
    link_key: str,
    stock_store: StockStore,
    sector_store: StockSectorStore,
) -> dict[str, SectorItem | None]:
    return {market: lookup_sector_by_link_key(market, link_key, stock_store, sector_store) for market in MARKETS}


def compute_market_sector_lead(
    market: str,
    stock_store: StockStore,
    sector_store: StockSectorStore,
    *,
    limit: int = 5,
) -> MarketSectorLead:
    sectors = build_market_sectors(market, stock_store, sector_store)

    gainers = _apply_strength(
        sorted(
            [s for s in sectors if s.change_percent > 0],
            key=lambda s: _sector_lead_sort_score(s.avg_market_cap, s.change_percent),
            reverse=True,
        )[:limit]
    )
    losers = _apply_strength(
        sorted(
            [s for s in sectors if s.change_percent < 0],
            key=lambda s: _sector_lead_sort_score(s.avg_market_cap, s.change_percent),
        )[:limit]
    )
    return MarketSectorLead(gainers=gainers, losers=losers)


def compute_all_market_sector_leads(
    stock_store: StockStore,
    sector_store: StockSectorStore,
    *,
    limit: int = 5,
) -> DojoMeshSectorsResponse:
    markets = {market: compute_market_sector_lead(market, stock_store, sector_store, limit=limit) for market in MARKETS}
    return DojoMeshSectorsResponse(markets=markets)


def collect_eligible_constituent_tickers(
    stock_store: StockStore,
    sector_store: StockSectorStore,
) -> set[str]:
    """Tickers eligible for L3 sector buckets (primary/secondary labels + quote + market cap)."""
    tickers: set[str] = set()
    for market in MARKETS:
        stocks = stock_store.list_market(market)
        buckets = _build_buckets(market, stocks, sector_store)
        for bucket in buckets.values():
            for member in bucket.members:
                if member.ticker and stock_store.is_ticker_market_cap_eligible(member.ticker):
                    tickers.add(member.ticker)
    return tickers
