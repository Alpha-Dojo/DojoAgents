from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional
from dojo.client.async_client import AsyncDojo
from dojoagents.dashboard.schemas.stock_sector import BilingualLabel, SectorLevelPath, StockSectorLabel
from dojoagents.logging import LOGGER
from dojoagents.dashboard.services.dojo_data_gateway import DojoDataGateway

MARKETS = ("sh", "hk", "us")


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

    async def load(self) -> None:
        try:
            res = await self.gateway.sector_relations()
            data = res.data
            if data:
                for item in data:
                    if "ticker" not in item and "symbol" in item:
                        item["ticker"] = item["symbol"]
                    ticker = item.get("ticker")
                    market = item.get("market")
                    if not ticker or not market:
                        continue
                    if market not in self._cache:
                        self._cache[market] = {}
                    try:
                        label = StockSectorLabel.model_validate(item)
                        self._cache[market][ticker] = label
                    except Exception as e:
                        LOGGER.warning(f"Failed to parse sector label for {ticker}: {e}")
        except Exception:
            LOGGER.error("Failed to load sector relations from SDK", exc_info=True)

    def get(self, market: str, ticker: str) -> Optional[StockSectorLabel]:
        return self._cache.get(market, {}).get(ticker)

    def stats(self) -> Dict[str, int]:
        return {market: len(self._cache.get(market, {})) for market in MARKETS}
