import asyncio
import datetime
import traceback
from pathlib import Path
from typing import Any

from dojoagents.dashboard.services.constituent_kline_refresh_state import RefreshStateStore
from dojoagents.logging import LOGGER


async def start_refresh_loop(runtime_dir: Path, registry: Any, poll_interval: int = 3600):  # 10 mins
    refresh_store = RefreshStateStore(runtime_dir)
    LOGGER.info("Starting background market refresh loop (DojoSDK preload_offline_data at 8:00 AM daily).")
    while True:
        try:
            await asyncio.sleep(poll_interval)
            now = datetime.datetime.now()
            target_time = datetime.time(8, 0)
            if now.time() >= target_time:
                target_date = now.date()
            else:
                target_date = now.date() - datetime.timedelta(days=1)

            client = getattr(registry, "client", None)
            if client is not None and hasattr(client, "preload_offline_data"):
                LOGGER.debug("Starting daily offline data preload via client.preload_offline_data()")
                if asyncio.iscoroutinefunction(client.preload_offline_data):
                    await client.preload_offline_data()
                else:
                    await asyncio.to_thread(client.preload_offline_data)
                await refresh_store.set_last_refresh_date_async("preload_offline_data", target_date)
                if hasattr(registry, "refresh_after_offline_data_update"):
                    await registry.refresh_after_offline_data_update()

        except asyncio.CancelledError:
            LOGGER.debug("Market refresh loop cancelled.")
            break
        except Exception as e:
            LOGGER.error(f"Unexpected error in refresh loop: {e}\n{traceback.format_exc()}")
            await asyncio.sleep(60)  # Sleep shortly on unexpected error
