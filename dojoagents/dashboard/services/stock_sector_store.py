from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Literal, Optional
from dojo.client.async_client import AsyncDojo
from dojoagents.dashboard.schemas.stock_sector import BilingualLabel, SectorLevelPath, StockSectorLabel
from dojoagents.logging import LOGGER
from dojoagents.dashboard.services.dojo_data_gateway import DojoDataGateway
from dojoagents.dashboard.services.domain_utils import normalize_market_code
from dojoagents.dashboard.services.sector_store import ResolvedSectorPath, SectorStore

MARKETS = ("sh", "hk", "us")


@dataclass(frozen=True)
class SectorAssignment:
    ticker: str
    market: str
    role: Literal["primary", "secondary"]
    path: ResolvedSectorPath


@dataclass
class SectorBucketMeta:
    zh: str
    en: str
    level: str = "L2"


Level2SectorMeta = SectorBucketMeta


@dataclass
class SectorMember:
    ticker: str
    name_zh: str
    name_en: str
    last_price: float
    change_percent: float
    market_cap: float
    pe: float = 0.0


@dataclass
class SectorBucket:
    meta: SectorBucketMeta
    members: List[SectorMember] = field(default_factory=list)


def _label_text(label: BilingualLabel) -> tuple[str, str]:
    zh = str(label.zh or label.en or "").strip()
    en = str(label.en or label.zh or "").strip()
    return zh, en


def iter_classification_branches(label: StockSectorLabel) -> Iterable[SectorLevelPath]:
    yield label.primary
    yield from label.secondary


def _level_3_meta_from_branch(branch: SectorLevelPath) -> Optional[SectorBucketMeta]:
    zh, en = _label_text(branch.level_3)
    if not zh and not en:
        return None
    return SectorBucketMeta(zh=zh, en=en, level="L3")


def iter_level_3_metas(label: StockSectorLabel) -> Iterable[SectorBucketMeta]:
    seen: set[str] = set()
    for branch in iter_classification_branches(label):
        meta = _level_3_meta_from_branch(branch)
        if meta is None:
            continue
        key = f"{meta.zh}|{meta.en}"
        if key in seen:
            continue
        seen.add(key)
        yield meta


def primary_level_2_meta(label: StockSectorLabel) -> Optional[SectorBucketMeta]:
    branch = label.primary
    zh, en = _label_text(branch.level_2)
    if not zh and not en:
        return None
    return SectorBucketMeta(zh=zh, en=en, level="L2")


def primary_level_3_meta(label: StockSectorLabel) -> Optional[SectorBucketMeta]:
    branch = label.primary
    zh, en = _label_text(branch.level_3)
    if not zh and not en:
        return None
    return SectorBucketMeta(zh=zh, en=en, level="L3")


def iter_level_2_paths(label: StockSectorLabel) -> Iterable[SectorBucketMeta]:
    meta = primary_level_2_meta(label)
    if meta is not None:
        yield meta


class StockSectorStore:
    def __init__(self, client: AsyncDojo) -> None:
        self.client = client
        gateway_method = getattr(type(client), "sector_relations", None)
        self.gateway = client if callable(gateway_method) else DojoDataGateway(client)
        self._cache: Dict[str, Dict[str, StockSectorLabel]] = {m: {} for m in MARKETS}
        self._assignments_by_path: Dict[tuple[str, str, str, str], List[SectorAssignment]] = {}
        self._assignments_by_ticker: Dict[tuple[str, str], List[SectorAssignment]] = {}
        self._unresolved_labels: list[dict[str, str]] = []
        self._resolved_with_sector_store_id: int | None = None

    async def load(self) -> None:
        try:
            res = await self.gateway.sector_relations()
            data = res.data
            self._cache = {m: {} for m in MARKETS}
            self._assignments_by_path = {}
            self._assignments_by_ticker = {}
            self._unresolved_labels = []
            self._resolved_with_sector_store_id = None
            if data:
                for item in data:
                    if "ticker" not in item and "symbol" in item:
                        item["ticker"] = item["symbol"]
                    ticker = str(item.get("ticker") or "").strip().upper()
                    market = normalize_market_code(item.get("market"))
                    if not ticker or not market:
                        continue
                    if market not in self._cache:
                        self._cache[market] = {}
                    try:
                        label = StockSectorLabel.model_validate(item)
                        self._cache[market][ticker] = label.model_copy(update={"ticker": ticker, "market": market})
                    except Exception as e:
                        LOGGER.warning(f"Failed to parse sector label for {ticker}: {e}")
        except Exception:
            LOGGER.error("Failed to load sector relations from SDK", exc_info=True)

    def get(self, market: str, ticker: str) -> Optional[StockSectorLabel]:
        normalized_market = normalize_market_code(market) or market.strip().lower()
        normalized_ticker = ticker.strip().upper()
        return self._cache.get(normalized_market, {}).get(normalized_ticker)

    def iter_labels(self, market: str | None = None) -> Iterable[tuple[str, str, StockSectorLabel]]:
        markets = [normalize_market_code(market)] if market else list(self._cache.keys())
        for market_code in markets:
            if not market_code:
                continue
            for ticker, label in self._cache.get(market_code, {}).items():
                yield market_code, ticker, label

    def _resolve_path(self, sector_store: SectorStore, branch: SectorLevelPath) -> Optional[ResolvedSectorPath]:
        return sector_store.find_resolved_path_by_labels(
            level_1_zh=branch.level_1.zh or "",
            level_1_en=branch.level_1.en or "",
            level_2_zh=branch.level_2.zh or "",
            level_2_en=branch.level_2.en or "",
            level_3_zh=branch.level_3.zh or "",
            level_3_en=branch.level_3.en or "",
        )

    def _ensure_assignment_index(self, sector_store: SectorStore) -> None:
        if self._resolved_with_sector_store_id == id(sector_store):
            return
        self._assignments_by_path = {}
        self._assignments_by_ticker = {}
        self._unresolved_labels = []
        for market, ticker, label in self.iter_labels():
            branches = [("primary", label.primary), *[("secondary", branch) for branch in label.secondary]]
            for role, branch in branches:
                path = self._resolve_path(sector_store, branch)
                if path is None:
                    self._unresolved_labels.append(
                        {
                            "market": market,
                            "ticker": ticker,
                            "role": role,
                            "level_1_zh": branch.level_1.zh or "",
                            "level_2_zh": branch.level_2.zh or "",
                            "level_3_zh": branch.level_3.zh or "",
                        }
                    )
                    continue
                assignment = SectorAssignment(
                    ticker=ticker,
                    market=market,
                    role=role,
                    path=path,
                )
                self._assignments_by_path.setdefault((market, path.level1_id, path.level2_id, path.level3_id), []).append(assignment)
                self._assignments_by_ticker.setdefault((market, ticker), []).append(assignment)
        self._resolved_with_sector_store_id = id(sector_store)

    def assignments_for_path(
        self,
        path: ResolvedSectorPath,
        *,
        sector_store: SectorStore,
        market: str | None = None,
        scope: str = "L3",
    ) -> List[SectorAssignment]:
        self._ensure_assignment_index(sector_store)
        markets = [normalize_market_code(market)] if market else list(self._cache.keys())
        results: list[SectorAssignment] = []
        for market_code in markets:
            if not market_code:
                continue
            if scope == "L1":
                for key, items in self._assignments_by_path.items():
                    if key[0] == market_code and key[1] == path.level1_id:
                        results.extend(items)
            elif scope == "L2":
                for key, items in self._assignments_by_path.items():
                    if key[0] == market_code and key[1] == path.level1_id and key[2] == path.level2_id:
                        results.extend(items)
            else:
                results.extend(
                    self._assignments_by_path.get(
                        (market_code, path.level1_id, path.level2_id, path.level3_id),
                        [],
                    )
                )
        deduped: dict[tuple[str, str, str, str, str, str], SectorAssignment] = {}
        for item in results:
            deduped[
                (
                    item.market,
                    item.ticker,
                    item.role,
                    item.path.level1_id,
                    item.path.level2_id,
                    item.path.level3_id,
                )
            ] = item
        return list(deduped.values())

    def assignments_for_ticker(
        self,
        market: str,
        ticker: str,
        *,
        sector_store: SectorStore,
    ) -> List[SectorAssignment]:
        self._ensure_assignment_index(sector_store)
        normalized_market = normalize_market_code(market) or market.strip().lower()
        normalized_ticker = ticker.strip().upper()
        return list(self._assignments_by_ticker.get((normalized_market, normalized_ticker), []))

    def stats(self) -> Dict[str, int]:
        return {market: len(self._cache.get(market, {})) for market in MARKETS}

    def assignment_stats(self, sector_store: SectorStore) -> Dict[str, int]:
        self._ensure_assignment_index(sector_store)
        return {
            "markets": len(self._cache),
            "labels": sum(len(items) for items in self._cache.values()),
            "resolved_assignments": sum(len(items) for items in self._assignments_by_ticker.values()),
            "unresolved_assignments": len(self._unresolved_labels),
        }

    def unresolved_assignments(self, sector_store: SectorStore) -> List[dict[str, str]]:
        self._ensure_assignment_index(sector_store)
        return list(self._unresolved_labels)
