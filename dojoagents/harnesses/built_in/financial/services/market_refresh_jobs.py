import asyncio
import datetime
import inspect
import traceback
from pathlib import Path
from typing import Any

from dojoagents.harnesses.built_in.financial.services.constituent_kline_refresh_state import RefreshStateStore
from dojoagents.logging import LOGGER


async def start_refresh_loop(
    runtime_dir: Path,
    registry: Any | None = None,
    poll_interval: int = 3600,
    *,
    store_registry: Any | None = None,
):
    """Refresh financial data once per target market date.

    ``store_registry`` remains an input alias for older callers while ownership
    moves from Dashboard stores to the FinancialHarness container.
    """
    if registry is not None and store_registry is not None and registry is not store_registry:
        raise ValueError("registry and store_registry must refer to the same instance")
    registry = registry if registry is not None else store_registry
    if registry is None:
        raise ValueError("registry is required")
    refresh_store = RefreshStateStore(runtime_dir)
    LOGGER.info("Starting background market refresh loop (DojoSDK preload_offline_data at 8:00 AM daily).")
    while True:
        try:
            now = datetime.datetime.now()
            target_time = datetime.time(8, 0)
            if now.time() >= target_time:
                target_date = now.date()
            else:
                target_date = now.date() - datetime.timedelta(days=1)

            last_refresh = await refresh_store.get_last_refresh_date_async("preload_offline_data")
            client = getattr(registry, "client", None)
            if last_refresh != target_date and client is not None and hasattr(client, "preload_offline_data"):
                LOGGER.debug("Starting daily offline data preload via client.preload_offline_data()")
                preload = client.preload_offline_data
                if inspect.iscoroutinefunction(preload):
                    await preload()
                else:
                    await asyncio.to_thread(preload)
                await refresh_store.set_last_refresh_date_async("preload_offline_data", target_date)
                if hasattr(registry, "refresh_after_offline_data_update"):
                    refresh = registry.refresh_after_offline_data_update
                    if inspect.iscoroutinefunction(refresh):
                        await refresh()
                    else:
                        await asyncio.to_thread(refresh)
            await asyncio.sleep(poll_interval)

        except asyncio.CancelledError:
            LOGGER.debug("Market refresh loop cancelled.")
            break
        except Exception as e:
            LOGGER.error(f"Unexpected error in refresh loop: {e}\n{traceback.format_exc()}")
            await asyncio.sleep(60)  # Sleep shortly on unexpected error
