from __future__ import annotations

import re
from typing import List, Any

from dojoagents.dashboard.schemas.stock import Stock
from dojoagents.dashboard.services.domain_utils import finite_float
from dojoagents.dashboard.services.sector_store import SectorStore
from dojoagents.dashboard.services.sector_movers_ranking import sector_eligible_for_movers_ranking
from dojoagents.dashboard.schemas.dojo_mesh import (
    BilingualText,
    DojoMeshSectorsResponse,
    MarketSectorLead,
    SectorItem,
    SectorMemberItem,
)

MAX_SECTOR_MEMBERS = 40
MARKETS = ("sh", "hk", "us")


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.lower()).strip("-")
    return slug or "unknown"


def _stock_bilingual_name(stock: Stock) -> BilingualText:
    quote = stock.stock_quote
    if quote and quote.name:
        zh = quote.name.strip()
    else:
        zh = (stock.short_name or stock.long_name or stock.ticker).strip()
    en = (stock.short_name or stock.long_name or stock.ticker).strip()
    return BilingualText(zh=zh, en=en)


def concept_code_for(market: str, name_zh: str, name_en: str, level: str) -> str:
    slug = slugify(name_en or name_zh)
    return f"{market.upper()}.{level.upper()}.{slug}"


def link_key_from_concept_code(concept_code: str) -> str | None:
    match = re.search(r"\.L3\.(.+)$", concept_code, re.IGNORECASE)
    return match.group(1) if match else None


def _sector_lead_sort_score(avg_market_cap: float, change_percent: float) -> float:
    return avg_market_cap * change_percent


def build_market_sectors(
    market: str,
    sector_store: SectorStore,
    sector_precomputed_store: Any,
) -> List[SectorItem]:
    # 1. Fetch 1-day movers for L3 sectors in this market
    movers = sector_precomputed_store.get_sector_movers_by_window(days=1)

    sectors: List[SectorItem] = []

    for row in movers:
        if row.get("market") != market or row.get("scope") != "L3":
            continue

        level1_id = row.get("level1_id")
        level2_id = row.get("level2_id")
        level3_id = row.get("level3_id")

        path = sector_store.find_resolved_path(level1_id, level2_id, level3_id)
        if not path:
            continue

        change_percent = finite_float(row.get("daily_return_pct"))
        avg_market_cap = finite_float(row.get("avg_market_cap"))
        member_count = int(row.get("member_count") or 0)

        # 2. Fetch sample members
        constituents = sector_precomputed_store.get_sector_constituents(
            level1_id=level1_id,
            level2_id=level2_id,
            level3_id=level3_id,
            market=market,
        )
        tickers = [c["ticker"] for c in constituents]

        ticker_daily = sector_precomputed_store.get_ticker_daily_by_window(days=1, tickers=tickers)
        # Create a lookup for fast access
        td_lookup = {td["ticker"]: td for td in ticker_daily}

        member_items: List[SectorMemberItem] = []
        for c in constituents:
            ticker = c["ticker"]
            td = td_lookup.get(ticker, {})

            # Use basic data
            member_items.append(
                SectorMemberItem(
                    ticker=ticker,
                    name=BilingualText(zh=ticker, en=ticker),  # Placeholder
                    last_price=finite_float(td.get("close")),
                    market_cap=finite_float(c.get("market_cap")),
                    change_percent=finite_float(td.get("daily_return_pct")),
                )
            )

        # Sort members by change_percent
        sorted_members = sorted(
            member_items,
            key=lambda m: m.change_percent,
            reverse=True,
        )

        top_by_abs = sorted(
            member_items,
            key=lambda m: abs(m.change_percent),
            reverse=True,
        )[:3]
        sample_tickers = [m.ticker for m in top_by_abs]

        item = SectorItem(
            concept_code=concept_code_for(market, path.level3_zh, path.level3_en, "L3"),
            name=BilingualText(zh=path.level3_zh, en=path.level3_en),
            change_percent=round(change_percent, 2),
            avg_market_cap=avg_market_cap,
            strength=0.0,
            sample_tickers=sample_tickers,
            member_count=member_count,
            members=sorted_members[:MAX_SECTOR_MEMBERS],
        )
        sectors.append(item)

    return sectors


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


def lookup_sector_by_link_key(
    market: str,
    link_key: str,
    sector_store: SectorStore,
    sector_precomputed_store: Any,
) -> SectorItem | None:
    needle = link_key.lower()
    for item in build_market_sectors(market, sector_store, sector_precomputed_store):
        item_key = link_key_from_concept_code(item.concept_code)
        if item_key and item_key.lower() == needle:
            return item
    return None


def lookup_cross_market_sectors(
    link_key: str,
    sector_store: SectorStore,
    sector_precomputed_store: Any,
) -> dict[str, SectorItem | None]:
    service = getattr(sector_precomputed_store, "sector_movers_service", None)
    if service is not None:
        return service.lookup_cross_market_sectors_response(link_key=link_key).markets
    return {market: lookup_sector_by_link_key(market, link_key, sector_store, sector_precomputed_store) for market in MARKETS}


def compute_market_sector_lead(
    market: str,
    sector_store: SectorStore,
    sector_precomputed_store: Any,
    *,
    limit: int = 5,
) -> MarketSectorLead:
    sectors = build_market_sectors(market, sector_store, sector_precomputed_store)
    ranked = [sector for sector in sectors if sector_eligible_for_movers_ranking(member_count=sector.member_count or 0)]

    gainers = _apply_strength(
        sorted(
            [s for s in ranked if s.change_percent > 0],
            key=lambda s: _sector_lead_sort_score(s.avg_market_cap, s.change_percent),
            reverse=True,
        )[:limit]
    )
    losers = _apply_strength(
        sorted(
            [s for s in ranked if s.change_percent < 0],
            key=lambda s: _sector_lead_sort_score(s.avg_market_cap, s.change_percent),
        )[:limit]
    )
    return MarketSectorLead(gainers=gainers, losers=losers)


def compute_all_market_sector_leads(
    sector_store: SectorStore,
    sector_precomputed_store: Any,
    *,
    limit: int = 5,
) -> DojoMeshSectorsResponse:
    service = getattr(sector_precomputed_store, "sector_movers_service", None)
    if service is not None:
        return service.build_dojo_mesh_sectors_response(limit=limit)
    markets = {market: compute_market_sector_lead(market, sector_store, sector_precomputed_store, limit=limit) for market in MARKETS}
    return DojoMeshSectorsResponse(markets=markets)
