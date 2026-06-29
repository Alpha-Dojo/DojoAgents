import asyncio
import logging
import datetime
import traceback
from pathlib import Path
from typing import Any

from dojoagents.dashboard.services.constituent_kline_refresh_state import RefreshStateStore

logger = logging.getLogger(__name__)


async def start_refresh_loop(runtime_dir: Path, store_registry: Any, poll_interval: int = 600):  # 10 mins
    refresh_store = RefreshStateStore(runtime_dir)

    logger.info("Starting background market refresh loop (DojoSDK preload_offline_data at 8:00 AM daily).")
    while True:
        try:
            now = datetime.datetime.now()
            target_time = datetime.time(8, 0)
            if now.time() >= target_time:
                target_date = now.date()
            else:
                target_date = now.date() - datetime.timedelta(days=1)

            last_refresh = await refresh_store.get_last_refresh_date_async("preload_offline_data")
            if last_refresh is None or last_refresh < target_date:
                client = getattr(store_registry, "client", None)
                if client is not None and hasattr(client, "preload_offline_data"):
                    logger.info("Starting daily offline data preload via client.preload_offline_data()")
                    if asyncio.iscoroutinefunction(client.preload_offline_data):
                        await client.preload_offline_data()
                    else:
                        await asyncio.to_thread(client.preload_offline_data)
                    await refresh_store.set_last_refresh_date_async("preload_offline_data", target_date)
                    logger.info(f"Daily offline data preload for {target_date} completed successfully.")
                else:
                    logger.warning("store_registry client does not have preload_offline_data method or is None.")

            await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            logger.info("Market refresh loop cancelled.")
            break
        except Exception as e:
            logger.error(f"Unexpected error in refresh loop: {e}\n{traceback.format_exc()}")
            await asyncio.sleep(60)  # Sleep shortly on unexpected error
