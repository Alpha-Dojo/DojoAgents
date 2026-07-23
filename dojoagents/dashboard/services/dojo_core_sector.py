from __future__ import annotations

from typing import List, Literal, Optional

from dojoagents.dashboard.services.sector_store import ResolvedSectorPath, SectorStore
from dojoagents.dashboard.services.stock_sector_store import StockSectorStore
from dojoagents.dashboard.services.stock_store import StockStore
from dojoagents.dashboard.schemas.dojo_core import CoreSectorCrumb, CoreSectorLabelPath, CoreSectorOption, CoreTickerSectorResponse
from dojoagents.dashboard.schemas.dojo_mesh import BilingualText
from dojoagents.dashboard.schemas.stock_sector import SectorLevelPath


def _bilingual(zh: str, en: str) -> BilingualText:
    return BilingualText(zh=zh.strip(), en=en.strip())


def _crumbs_from_path(path: ResolvedSectorPath) -> List[CoreSectorCrumb]:
    ids = (path.level1_id, path.level2_id, path.level3_id)
    return [
        CoreSectorCrumb(
            level="L1",
            name=_bilingual(path.level1_zh, path.level1_en),
            level1_id=ids[0],
            level2_id=ids[1],
            level3_id=ids[2],
        ),
        CoreSectorCrumb(
            level="L2",
            name=_bilingual(path.level2_zh, path.level2_en),
            level1_id=ids[0],
            level2_id=ids[1],
            level3_id=ids[2],
        ),
        CoreSectorCrumb(
            level="L3",
            name=_bilingual(path.level3_zh, path.level3_en),
            level1_id=ids[0],
            level2_id=ids[1],
            level3_id=ids[2],
        ),
    ]


def _resolve_branch_path(
    sector_store: SectorStore,
    branch: SectorLevelPath,
) -> Optional[ResolvedSectorPath]:
    l1 = branch.level_1
    l2 = branch.level_2
    l3 = branch.level_3
    return sector_store.find_resolved_path_by_labels(
        level_1_zh=l1.zh,
        level_1_en=l1.en,
        level_2_zh=l2.zh,
        level_2_en=l2.en,
        level_3_zh=l3.zh,
        level_3_en=l3.en,
    )


def _label_path_from_branch(branch: SectorLevelPath) -> CoreSectorLabelPath:
    l1 = branch.level_1
    l2 = branch.level_2
    l3 = branch.level_3
    return CoreSectorLabelPath(
        level_1=_bilingual(l1.zh, l1.en),
        level_2=_bilingual(l2.zh, l2.en),
        level_3=_bilingual(l3.zh, l3.en),
    )


def _path_has_content(branch: SectorLevelPath) -> bool:
    for level in (branch.level_1, branch.level_2, branch.level_3):
        if (level.zh or level.en).strip():
            return True
    return False


def _option_from_branch(
    branch: SectorLevelPath,
    *,
    role: Literal["primary", "secondary"],
    path: ResolvedSectorPath,
) -> CoreSectorOption:
    return CoreSectorOption(
        role=role,
        level1_id=path.level1_id,
        level2_id=path.level2_id,
        level3_id=path.level3_id,
        label=_label_path_from_branch(branch),
    )


def _build_sector_options(
    sector_store: SectorStore,
    label_primary: SectorLevelPath,
    label_secondaries: list[SectorLevelPath],
) -> List[CoreSectorOption]:
    options: List[CoreSectorOption] = []
    seen: set[tuple[str, str, str]] = set()

    primary_path = _resolve_branch_path(sector_store, label_primary)
    if primary_path is not None:
        key = (primary_path.level1_id, primary_path.level2_id, primary_path.level3_id)
        seen.add(key)
        options.append(_option_from_branch(label_primary, role="primary", path=primary_path))

    for branch in label_secondaries:
        if not _path_has_content(branch):
            continue
        resolved = _resolve_branch_path(sector_store, branch)
        if resolved is None:
            continue
        key = (resolved.level1_id, resolved.level2_id, resolved.level3_id)
        if key in seen:
            continue
        seen.add(key)
        options.append(_option_from_branch(branch, role="secondary", path=resolved))

    return options


def resolve_core_ticker_sector(
    ticker: str,
    *,
    market: Optional[str],
    stock_store: StockStore,
    stock_sector_store: StockSectorStore,
    sector_store: SectorStore,
) -> Optional[CoreTickerSectorResponse]:
    market_code = (market or stock_store.find_market(ticker) or "").lower()
    if market_code not in ("sh", "hk", "us"):
        return None

    label = stock_sector_store.get(market_code, ticker)
    if label is None:
        return None

    sector_options = _build_sector_options(sector_store, label.primary, label.secondary)
    if not sector_options:
        return None

    return CoreTickerSectorResponse(
        ticker=label.ticker,
        market=market_code,
        sector_options=sector_options,
    )
