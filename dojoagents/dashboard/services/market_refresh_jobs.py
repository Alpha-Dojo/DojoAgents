import asyncio
import logging
import datetime
import traceback
from pathlib import Path

from dojoagents.dashboard.services.market_close_schedule import MarketCloseSchedule
from dojoagents.dashboard.services.constituent_kline_refresh_state import RefreshStateStore
from dojoagents.dashboard.services.domain_api import build_sector_movers

# Need to import stores for the refresh
from typing import Any

logger = logging.getLogger(__name__)


async def _precompute_sector_performance(store_registry: Any) -> None:
    from dojoagents.dashboard.services.precompute_sector_daily import build_sector_precomputed

    data_root = getattr(store_registry, "data_root", None)
    if data_root is None:
        raise RuntimeError("store_registry.data_root is required for sector precompute")

    logger.info("Executing build_sector_precomputed.")
    manifest = await build_sector_precomputed(
        data_root=data_root,
        sector_store=store_registry.sector_store,
        stock_sector_store=store_registry.stock_sector_store,
        stock_store=store_registry.stock_store,
        kline_store=store_registry.kline_store,
        # upload_client=getattr(store_registry, "client", None),
    )
    logger.info("Sector precompute completed: %s", manifest.get("published_dir"))

    if store_registry.sector_precomputed_store is not None:
        await store_registry.sector_precomputed_store.reload_async(Path(manifest["published_dir"]))
    sector_movers_service = getattr(store_registry, "sector_movers_service", None)
    if sector_movers_service is not None:
        sector_movers_service.invalidate()


async def _snapshot_market_leads(store_registry: Any, market: str) -> None:
    await build_sector_movers(
        store_registry,
        days=1,
        limit=10,
        market=market,
    )


async def run_market_refresh(market_group: str, target_date: datetime.date, store_registry: Any, refresh_store: RefreshStateStore):
    try:
        logger.info(f"Starting post-close refresh for {market_group} on {target_date}")

        markets = ["sh", "hk"] if market_group == "cn_hk" else ["us"]

        logger.info("Precomputing sector performance cache for %s", market_group)
        await _precompute_sector_performance(store_registry)

        for mkt in markets:
            logger.info("Refreshing market leads snapshot for %s", mkt)
            await _snapshot_market_leads(store_registry, mkt)

        await refresh_store.set_last_refresh_date_async(market_group, target_date)
        logger.info(f"Successfully completed refresh for {market_group} on {target_date}")

    except Exception as e:
        logger.error(f"Error during {market_group} refresh: {e}\n{traceback.format_exc()}")
        # Do NOT update refresh state so it retries


async def start_refresh_loop(runtime_dir: Path, schedule: MarketCloseSchedule, store_registry: Any, poll_interval: int = 600):  # 10 mins
    refresh_store = RefreshStateStore(runtime_dir)

    logger.info("Starting background market refresh loop.")
    while True:
        try:
            for group in ["cn_hk", "us"]:
                target_date = schedule.get_target_refresh_date(group)
                if not target_date:
                    continue

                last_refresh = await refresh_store.get_last_refresh_date_async(group)
                if last_refresh is None or last_refresh < target_date:
                    # Time to refresh
                    await run_market_refresh(market_group=group, target_date=target_date, store_registry=store_registry, refresh_store=refresh_store)

            await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            logger.info("Market refresh loop cancelled.")
            break
        except Exception as e:
            logger.error(f"Unexpected error in refresh loop: {e}\n{traceback.format_exc()}")
            await asyncio.sleep(60)  # Sleep shortly on unexpected error
