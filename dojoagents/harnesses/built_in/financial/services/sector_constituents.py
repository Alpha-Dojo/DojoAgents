from __future__ import annotations

from typing import Dict, Literal, Set, Tuple, Any

from dojoagents.harnesses.built_in.financial.services.sector_store import ResolvedSectorPath, SectorStore
from dojoagents.harnesses.built_in.financial.services.stock_sector_store import StockSectorStore, iter_classification_branches
from dojoagents.harnesses.built_in.financial.services.stock_store import StockStore
from dojoagents.harnesses.built_in.financial.contracts.stock_sector import BilingualLabel, SectorLevelPath, StockSectorLabel

MARKETS = ("sh", "hk", "us")
SectorLevel = Literal["L1", "L2", "L3"]


def _bilingual_matches(label: BilingualLabel, ref_zh: str, ref_en: str) -> bool:
    zh = str(label.zh or label.en or "").strip()
    en = str(label.en or label.zh or "").strip()
    ref_zh = ref_zh.strip()
    ref_en = ref_en.strip()
    if ref_zh and zh == ref_zh:
        return True
    if ref_en and en == ref_en:
        return True
    return False


def _branch_matches_sector_level(
    branch: SectorLevelPath,
    *,
    level1_zh: str,
    level1_en: str,
    level2_zh: str,
    level2_en: str,
    level3_zh: str,
    level3_en: str,
    max_level: SectorLevel,
) -> bool:
    if not _bilingual_matches(branch.level_1, level1_zh, level1_en):
        return False
    if max_level == "L1":
        return True
    if not _bilingual_matches(branch.level_2, level2_zh, level2_en):
        return False
    if max_level == "L2":
        return True
    return _bilingual_matches(branch.level_3, level3_zh, level3_en)


def label_matches_sector_level(
    stock_label: StockSectorLabel,
    *,
    level1_zh: str,
    level1_en: str,
    level2_zh: str,
    level2_en: str,
    level3_zh: str,
    level3_en: str,
    max_level: SectorLevel,
) -> bool:
    kwargs = {
        "level1_zh": level1_zh,
        "level1_en": level1_en,
        "level2_zh": level2_zh,
        "level2_en": level2_en,
        "level3_zh": level3_zh,
        "level3_en": level3_en,
        "max_level": max_level,
    }
    return any(_branch_matches_sector_level(branch, **kwargs) for branch in iter_classification_branches(stock_label))


def collect_sector_scope_tickers(
    sector_precomputed_store: Any,
    path: ResolvedSectorPath,
    *,
    markets: Tuple[str, ...] = MARKETS,
    market: str | None = None,
) -> Dict[SectorLevel, Set[str]]:
    """Eligible constituents (label + quote + market cap + volume) grouped by L1/L2/L3 scope."""
    if market is not None:
        if market not in MARKETS:
            return {"L1": set(), "L2": set(), "L3": set()}
        active_markets: Tuple[str, ...] = (market,)
    else:
        active_markets = markets

    scopes: Dict[SectorLevel, Set[str]] = {"L1": set(), "L2": set(), "L3": set()}

    for market_code in active_markets:
        # Load constituents from precomputed store
        rows = sector_precomputed_store.get_sector_constituents(
            level1_id=path.level1_id,
            level2_id="",  # we want all under L1 to determine scope
            level3_id="",
            market=market_code,
        )
        for row in rows:
            ticker = row["ticker"]
            # Check which scopes this belongs to
            if row.get("level1_id") == path.level1_id:
                scopes["L1"].add(ticker)
                if path.level2_id and row.get("level2_id") == path.level2_id:
                    scopes["L2"].add(ticker)
                    if path.level3_id and row.get("level3_id") == path.level3_id:
                        scopes["L3"].add(ticker)

    return scopes


def split_priority_symbol_groups(
    scopes: Dict[SectorLevel, Set[str]],
) -> Tuple[list[str], list[str], list[str]]:
    """L3 first, then L2-only additions, then L1-only additions."""
    l3 = scopes.get("L3") or set()
    l2 = scopes.get("L2") or set()
    l1 = scopes.get("L1") or set()
    return (
        sorted(l3),
        sorted(l2 - l3),
        sorted(l1 - l2),
    )


async def build_l3_sector_symbol_order(
    sector_store: SectorStore,
    stock_store: StockStore,
    stock_sector_store: StockSectorStore,
    *,
    markets: Tuple[str, ...] = MARKETS,
) -> list[str]:
    """Background preload order: iterate L3 sectors, then their constituents."""
    ordered: list[str] = []
    seen: set[str] = set()

    for path in sector_store.iter_resolved_paths():
        l3_tickers = (
            collect_sector_scope_tickers(
                sector_store.sector_precomputed_store,  # assume sector_store provides this or we fetch it
                path,
                markets=markets,
            )
        ).get("L3") or set()
        for ticker in sorted(l3_tickers):
            if ticker in seen or not stock_store.is_ticker_market_cap_eligible(ticker):
                continue
            seen.add(ticker)
            ordered.append(ticker)
    return ordered
