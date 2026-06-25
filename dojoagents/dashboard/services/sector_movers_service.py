from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from dojoagents.dashboard.schemas.dojo_mesh import (
    BilingualText,
    CrossMarketSectorLookupResponse,
    DojoMeshSectorsResponse,
    MarketSectorLead,
    SectorItem,
    SectorMemberItem,
)
from dojoagents.dashboard.schemas.domain_api import (
    MarketSectorMovers,
    SectorMoverItem,
    SectorMoverMember,
    SectorMoversResponse,
)
from dojoagents.dashboard.services.market_sector_lead import (
    MAX_SECTOR_MEMBERS,
    _apply_strength,
    _stock_bilingual_name,
    concept_code_for,
    link_key_from_concept_code,
)
from dojoagents.dashboard.services.domain_utils import normalize_market_code, to_native_market_code

MARKETS = ("sh", "hk", "us")


@dataclass(frozen=True)
class _SectorCandidate:
    market: str
    level1_id: str
    level2_id: str
    level3_id: str
    concept_code: str
    name: BilingualText
    change_percent: float
    total_market_cap: float
    avg_market_cap: float
    member_count: int


def _sector_lead_sort_score(avg_market_cap: float, change_percent: float) -> float:
    return avg_market_cap * change_percent


class SectorMoversService:
    def __init__(self, *, sector_store, stock_store, sector_precomputed_store) -> None:
        self.sector_store = sector_store
        self.stock_store = stock_store
        self.sector_precomputed_store = sector_precomputed_store
        self._catalog_cache: dict[tuple[int, int], dict[str, list[_SectorCandidate]]] = {}

    def invalidate(self) -> None:
        self._catalog_cache = {}

    def build_market_movers_response(
        self,
        *,
        days: int,
        limit: int,
        market: Optional[str],
        min_cap_by_market: Optional[dict[str, float]] = None,
    ) -> SectorMoversResponse:
        min_cap_by_market = min_cap_by_market or {}
        requested_markets = [normalize_market_code(market)] if market else list(MARKETS)
        ticker_lookup = self._ticker_lookup(days)
        payload: dict[str, MarketSectorMovers] = {}

        for internal_market in requested_markets:
            if internal_market is None:
                continue
            threshold = float(min_cap_by_market.get(internal_market) or 0.0)
            candidates = list(self._catalog_for_days(days).get(internal_market) or [])
            if threshold > 0:
                candidates = [candidate for candidate in candidates if candidate.total_market_cap >= threshold]

            gainers = sorted(
                [candidate for candidate in candidates if candidate.change_percent > 0],
                key=lambda candidate: candidate.change_percent,
                reverse=True,
            )[:limit]
            losers = sorted(
                [candidate for candidate in candidates if candidate.change_percent < 0],
                key=lambda candidate: candidate.change_percent,
            )[:limit]

            payload[to_native_market_code(internal_market) or internal_market] = MarketSectorMovers(
                gainers=[self._build_source_sector_item(candidate, ticker_lookup) for candidate in gainers],
                losers=[self._build_source_sector_item(candidate, ticker_lookup) for candidate in losers],
            )

        return SectorMoversResponse(days=days, markets=payload)

    def build_dojo_mesh_sectors_response(self, *, limit: int = 5) -> DojoMeshSectorsResponse:
        ticker_lookup = self._ticker_lookup(days=1)
        markets: dict[str, MarketSectorLead] = {}
        catalog = self._catalog_for_days(1)
        for market in MARKETS:
            candidates = list(catalog.get(market) or [])
            gainers = sorted(
                [candidate for candidate in candidates if candidate.change_percent > 0],
                key=lambda candidate: _sector_lead_sort_score(candidate.avg_market_cap, candidate.change_percent),
                reverse=True,
            )[:limit]
            losers = sorted(
                [candidate for candidate in candidates if candidate.change_percent < 0],
                key=lambda candidate: _sector_lead_sort_score(candidate.avg_market_cap, candidate.change_percent),
            )[:limit]
            markets[market] = MarketSectorLead(
                gainers=_apply_strength([self._build_sector_item(candidate, ticker_lookup) for candidate in gainers]),
                losers=_apply_strength([self._build_sector_item(candidate, ticker_lookup) for candidate in losers]),
            )
        return DojoMeshSectorsResponse(markets=markets)

    def lookup_cross_market_sectors_response(self, *, link_key: str) -> CrossMarketSectorLookupResponse:
        needle = link_key.lower()
        ticker_lookup = self._ticker_lookup(days=1)
        markets: dict[str, SectorItem | None] = {}
        catalog = self._catalog_for_days(1)
        for market in MARKETS:
            candidate = next(
                (item for item in catalog.get(market) or [] if (link_key_from_concept_code(item.concept_code) or "").lower() == needle),
                None,
            )
            markets[market] = self._build_sector_item(candidate, ticker_lookup) if candidate is not None else None
        return CrossMarketSectorLookupResponse(link_key=link_key, markets=markets)

    def _catalog_for_days(self, days: int) -> dict[str, list[_SectorCandidate]]:
        cache_key = (self.sector_precomputed_store.load_generation, days)
        cached = self._catalog_cache.get(cache_key)
        if cached is not None:
            return cached

        sector_rows = self.sector_precomputed_store.get_sector_movers_window_frame(days)
        markets: dict[str, list[_SectorCandidate]] = {market: [] for market in MARKETS}
        if not sector_rows.empty:
            for row in sector_rows.itertuples(index=False):
                if getattr(row, "scope", None) != "L3":
                    continue
                path = self.sector_store.find_resolved_path(row.level1_id, row.level2_id, row.level3_id)
                if path is None:
                    continue
                market = str(row.market)
                if market not in markets:
                    markets[market] = []
                total_market_cap = float(getattr(row, "total_market_cap", 0.0) or 0.0)
                member_count = int(getattr(row, "member_count", 0) or 0)
                avg_market_cap = total_market_cap / member_count if member_count else 0.0
                markets[market].append(
                    _SectorCandidate(
                        market=market,
                        level1_id=str(row.level1_id),
                        level2_id=str(row.level2_id),
                        level3_id=str(row.level3_id),
                        concept_code=concept_code_for(market, path.level3_zh, path.level3_en, "L3"),
                        name=BilingualText(zh=path.level3_zh, en=path.level3_en),
                        change_percent=round(float(getattr(row, "daily_return_pct", 0.0) or 0.0), 2),
                        total_market_cap=total_market_cap,
                        avg_market_cap=avg_market_cap,
                        member_count=member_count,
                    )
                )

        existing = self._catalog_cache.get(cache_key)
        if existing is not None:
            return existing
        self._catalog_cache[cache_key] = markets
        return markets

    def _ticker_lookup(self, days: int) -> dict[tuple[str, str], dict]:
        frame = self.sector_precomputed_store.get_ticker_daily_window_frame(days)
        if frame.empty:
            return {}
        return {(str(row.market), str(row.ticker)): row._asdict() for row in frame.itertuples(index=False)}

    def _build_sector_item(
        self,
        candidate: _SectorCandidate | None,
        ticker_lookup: dict[tuple[str, str], dict],
    ) -> SectorItem | None:
        if candidate is None:
            return None
        constituents = self.sector_precomputed_store.get_sector_constituents_exact(
            candidate.level1_id,
            candidate.level2_id,
            candidate.level3_id,
            market=candidate.market,
        )
        members: list[SectorMemberItem] = []
        for constituent in constituents:
            ticker = str(constituent.get("ticker") or "")
            if not ticker:
                continue
            stock = self.stock_store.get(candidate.market, ticker)
            if stock is None:
                continue
            ticker_row = ticker_lookup.get((candidate.market, ticker), {})
            quote = getattr(stock, "stock_quote", None)
            change_percent = float(ticker_row.get("daily_return_pct") or 0.0)
            last_price = float(getattr(quote, "last_price", 0.0) or 0.0)
            members.append(
                SectorMemberItem(
                    ticker=ticker,
                    name=_stock_bilingual_name(stock),
                    last_price=last_price,
                    market_cap=float(constituent.get("market_cap") or 0.0),
                    change_percent=round(change_percent, 2),
                )
            )

        sorted_members = sorted(members, key=lambda item: item.change_percent, reverse=True)
        top_by_abs = sorted(members, key=lambda item: abs(item.change_percent), reverse=True)[:3]
        return SectorItem(
            concept_code=candidate.concept_code,
            name=candidate.name,
            change_percent=candidate.change_percent,
            avg_market_cap=candidate.avg_market_cap,
            strength=0.0,
            sample_tickers=[item.ticker for item in top_by_abs],
            member_count=candidate.member_count,
            members=sorted_members[:MAX_SECTOR_MEMBERS],
        )

    def _build_source_sector_item(
        self,
        candidate: _SectorCandidate,
        ticker_lookup: dict[tuple[str, str], dict],
    ) -> SectorMoverItem:
        item = self._build_sector_item(candidate, ticker_lookup)
        top_members = [
            SectorMoverMember(
                ticker=member.ticker,
                name=member.name,
                last_price=member.last_price,
                market_cap=member.market_cap,
                change_percent=member.change_percent,
            )
            for member in item.members
        ]
        return SectorMoverItem(
            level1_id=candidate.level1_id,
            level2_id=candidate.level2_id,
            level3_id=candidate.level3_id,
            concept_code=item.concept_code,
            name=item.name,
            change_percent=item.change_percent,
            avg_market_cap=item.avg_market_cap,
            total_market_cap=candidate.total_market_cap,
            member_count=item.member_count,
            sample_tickers=item.sample_tickers,
            top_members=top_members,
        )
