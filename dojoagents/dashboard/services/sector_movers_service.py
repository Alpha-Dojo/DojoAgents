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
from dojoagents.dashboard.services.domain_utils import finite_float, normalize_market_code, sanitize_mapping, to_native_market_code
from dojoagents.dashboard.services.market_window import MarketAnalysisWindow, resolve_market_analysis_window
from dojoagents.dashboard.services.sector_movers_ranking import sector_eligible_for_movers_ranking
from dojoagents.dashboard.services.sector_leader_concentration import compute_leader_concentration

MARKETS = ("sh", "hk", "us")


def _leader_fields_from_members(
    members: list,
    sector_return_pct: float,
) -> dict[str, float | str | None]:
    payload = compute_leader_concentration(
        [
            (
                str(getattr(member, "ticker", "") or ""),
                getattr(member, "market_cap", None),
                getattr(member, "change_percent", None),
            )
            for member in members
        ],
        sector_return_pct,
    )
    if payload is None:
        return {
            "leader_ticker": None,
            "leader_weight_pct": None,
            "leader_return_pct": None,
            "leader_contribution_pct": None,
            "leader_concentration_pct": None,
            "leader_concentration_tier": None,
        }
    return {
        "leader_ticker": payload.leader_ticker,
        "leader_weight_pct": round(payload.leader_weight_pct, 2),
        "leader_return_pct": round(payload.leader_return_pct, 2),
        "leader_contribution_pct": round(payload.leader_contribution_pct, 2),
        "leader_concentration_pct": round(payload.leader_concentration_pct, 2),
        "leader_concentration_tier": payload.leader_concentration_tier,
    }


def _filter_ranking_candidates(
    candidates: list["_SectorCandidate"],
    *,
    min_total_market_cap: float = 0.0,
) -> list["_SectorCandidate"]:
    return [
        candidate
        for candidate in candidates
        if sector_eligible_for_movers_ranking(
            member_count=candidate.member_count,
            total_market_cap=candidate.total_market_cap,
            min_total_market_cap=min_total_market_cap,
        )
    ]


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
        self._catalog_cache: dict[tuple, dict[str, list[_SectorCandidate]]] = {}

    def invalidate(self) -> None:
        self._catalog_cache = {}

    def build_market_movers_response(
        self,
        *,
        days: int,
        limit: int,
        market: Optional[str],
        min_cap_by_market: Optional[dict[str, float]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        as_of: Optional[str] = None,
        include_members: bool = True,
    ) -> SectorMoversResponse:
        window = self.sector_precomputed_store.resolve_window_bounds(
            resolve_market_analysis_window(
                days=days,
                as_of=as_of,
                start_date=start_date,
                end_date=end_date,
                default_days=days,
            )
        )
        min_cap_by_market = min_cap_by_market or {}
        requested_markets = [normalize_market_code(market)] if market else list(MARKETS)
        use_live_quotes = (
            days <= 1
            and not start_date
            and not end_date
            and not as_of
            # A committed quote snapshot may lag the independently published
            # sector-precomputed snapshot. Only genuinely online quotes may
            # override its returns and as-of date.
            and getattr(self.stock_store, "quote_source", None) == "sdk_online"
            and bool(getattr(self.stock_store, "quote_as_of", None))
        )
        ticker_lookup = (
            self._live_ticker_lookup()
            if use_live_quotes
            else (self._ticker_lookup(window) if include_members else {})
        )
        payload: dict[str, MarketSectorMovers] = {}
        catalog = self._live_catalog_for_latest(window) if use_live_quotes else self._catalog_for_window(window)

        for internal_market in requested_markets:
            if internal_market is None:
                continue
            threshold = float(min_cap_by_market.get(internal_market) or 0.0)
            candidates = _filter_ranking_candidates(
                list(catalog.get(internal_market) or []),
                min_total_market_cap=threshold,
            )

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
                gainers=[
                    self._build_source_sector_item(
                        candidate,
                        ticker_lookup,
                        include_members=include_members,
                    )
                    for candidate in gainers
                ],
                losers=[
                    self._build_source_sector_item(
                        candidate,
                        ticker_lookup,
                        include_members=include_members,
                    )
                    for candidate in losers
                ],
            )

        live_as_of = (
            str(getattr(self.stock_store, "quote_as_of", "") or "")[:10]
            if use_live_quotes
            else ""
        )
        return SectorMoversResponse(
            days=window.days,
            as_of=live_as_of or window.as_of or window.resolved_end,
            window_mode=window.mode,
            window_start=live_as_of or window.resolved_start,
            window_end=live_as_of or window.resolved_end,
            markets=payload,
        )

    def _live_ticker_lookup(self) -> dict[tuple[str, str], dict]:
        lookup: dict[tuple[str, str], dict] = {}
        for market in MARKETS:
            for stock in self.stock_store.list_market(market):
                quote = getattr(stock, "stock_quote", None)
                if quote is None:
                    continue
                lookup[(market, str(stock.ticker))] = {
                    "daily_return_pct": finite_float(quote.change_percent),
                }
        return lookup

    def _live_catalog_for_latest(
        self,
        window: MarketAnalysisWindow,
    ) -> dict[str, list[_SectorCandidate]]:
        """Overlay the latest online quote return onto the historical catalog."""
        base = self._catalog_for_window(window)
        markets: dict[str, list[_SectorCandidate]] = {market: [] for market in MARKETS}
        for market, candidates in base.items():
            for candidate in candidates:
                constituents = self.sector_precomputed_store.get_sector_constituents_exact(
                    candidate.level1_id,
                    candidate.level2_id,
                    candidate.level3_id,
                    market=market,
                )
                weighted_return = 0.0
                total_weight = 0.0
                member_count = 0
                for constituent in constituents:
                    stock = self.stock_store.get(market, str(constituent.get("ticker") or ""))
                    quote = getattr(stock, "stock_quote", None) if stock is not None else None
                    if quote is None:
                        continue
                    weight = finite_float(quote.market_cap) or finite_float(constituent.get("market_cap"))
                    if weight <= 0:
                        continue
                    weighted_return += weight * finite_float(quote.change_percent)
                    total_weight += weight
                    member_count += 1
                if total_weight <= 0 or member_count <= 0:
                    continue
                markets.setdefault(market, []).append(
                    _SectorCandidate(
                        market=candidate.market,
                        level1_id=candidate.level1_id,
                        level2_id=candidate.level2_id,
                        level3_id=candidate.level3_id,
                        concept_code=candidate.concept_code,
                        name=candidate.name,
                        change_percent=round(weighted_return / total_weight, 2),
                        total_market_cap=total_weight,
                        avg_market_cap=total_weight / member_count,
                        member_count=member_count,
                    )
                )
        return markets

    def build_dojo_mesh_sectors_response(
        self,
        *,
        limit: int = 5,
        days: int = 1,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        as_of: Optional[str] = None,
    ) -> DojoMeshSectorsResponse:
        window = self.sector_precomputed_store.resolve_window_bounds(
            resolve_market_analysis_window(
                days=days,
                as_of=as_of,
                start_date=start_date,
                end_date=end_date,
                default_days=days,
            )
        )
        ticker_lookup = self._ticker_lookup(window)
        markets: dict[str, MarketSectorLead] = {}
        catalog = self._catalog_for_window(window)
        for market in MARKETS:
            candidates = _filter_ranking_candidates(list(catalog.get(market) or []))
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
        ticker_lookup = self._ticker_lookup(MarketAnalysisWindow(mode="days", days=1))
        markets: dict[str, SectorItem | None] = {}
        catalog = self._catalog_for_window(MarketAnalysisWindow(mode="days", days=1))
        for market in MARKETS:
            candidate = next(
                (item for item in catalog.get(market) or [] if (link_key_from_concept_code(item.concept_code) or "").lower() == needle),
                None,
            )
            markets[market] = self._build_sector_item(candidate, ticker_lookup) if candidate is not None else None
        return CrossMarketSectorLookupResponse(link_key=link_key, markets=markets)

    def _catalog_for_window(self, window: MarketAnalysisWindow) -> dict[str, list[_SectorCandidate]]:
        cache_key = (self.sector_precomputed_store.load_generation, *window.cache_key())
        cached = self._catalog_cache.get(cache_key)
        if cached is not None:
            return cached

        sector_rows = self.sector_precomputed_store.get_sector_movers_window_frame_for_window(window)
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
                total_market_cap = finite_float(getattr(row, "total_market_cap", 0.0))
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
                        change_percent=round(finite_float(getattr(row, "daily_return_pct", 0.0)), 2),
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

    def _ticker_lookup(self, window: MarketAnalysisWindow) -> dict[tuple[str, str], dict]:
        frame = self.sector_precomputed_store.get_ticker_daily_window_frame_for_window(window)
        if frame.empty:
            return {}
        return {(str(row.market), str(row.ticker)): sanitize_mapping(row._asdict()) for row in frame.itertuples(index=False)}

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
            change_percent = finite_float(ticker_row.get("daily_return_pct"))
            last_price = finite_float(getattr(quote, "last_price", 0.0))
            members.append(
                SectorMemberItem(
                    ticker=ticker,
                    name=_stock_bilingual_name(stock),
                    last_price=last_price,
                    market_cap=finite_float(constituent.get("market_cap")),
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
        *,
        include_members: bool = True,
    ) -> SectorMoverItem:
        empty_leader = _leader_fields_from_members([], candidate.change_percent)
        if not include_members:
            return SectorMoverItem(
                level1_id=candidate.level1_id,
                level2_id=candidate.level2_id,
                level3_id=candidate.level3_id,
                concept_code=candidate.concept_code,
                name=candidate.name,
                change_percent=candidate.change_percent,
                avg_market_cap=candidate.avg_market_cap,
                total_market_cap=candidate.total_market_cap,
                member_count=candidate.member_count,
                sample_tickers=[],
                top_members=[],
                **empty_leader,
            )

        item = self._build_sector_item(candidate, ticker_lookup)
        assert item is not None
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
        leader = _leader_fields_from_members(item.members, candidate.change_percent)
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
            **leader,
        )
