import anyio
import datetime
import inspect
import traceback
from pathlib import Path
from typing import Any

from dojoagents.dashboard.services.constituent_kline_refresh_state import (
    SNAPSHOT_REFRESH_STATE_KEY,
    RefreshStateStore,
)
from dojoagents.logging import LOGGER
from dojoagents.utils.async_runtime import SyncWorkload, run_sync_bounded


async def start_refresh_loop(
    runtime_dir: Path,
    registry: Any | None = None,
    poll_interval: int = 3600,
    *,
    store_registry: Any | None = None,
    paths: tuple[str, ...] | list[str] = (),
    repos: tuple[str, ...] | list[str] = (),
    hot_paths: tuple[str, ...] | list[str] = (),
    task_status: anyio.abc.TaskStatus[None] = anyio.TASK_STATUS_IGNORED,
):
    """Refresh hot snapshots on each poll and the full scope once per market date.

    ``store_registry`` remains an input alias for older callers while ownership
    moves from Dashboard stores to the FinancialHarness container.
    """
    if registry is not None and store_registry is not None and registry is not store_registry:
        raise ValueError("registry and store_registry must refer to the same instance")
    registry = registry if registry is not None else store_registry
    if registry is None:
        raise ValueError("registry is required")
    refresh_store = RefreshStateStore(runtime_dir)
    selected_paths = list(dict.fromkeys(str(path) for path in paths if str(path).strip()))
    selected_repos = list(dict.fromkeys(str(repo) for repo in repos if str(repo).strip()))
    selected_hot_paths = list(dict.fromkeys(str(path) for path in hot_paths if str(path).strip()))
    selected_hot_paths = [path for path in selected_hot_paths if path in selected_paths]
    if not selected_paths and not selected_repos:
        raise ValueError("daily snapshot refresh requires explicit paths or repos")
    LOGGER.info(
        "Starting background market refresh loop (hot snapshots every %ss; full sync at 8:00 AM daily): "
        "paths=%s repos=%s hot_paths=%s",
        poll_interval,
        selected_paths,
        selected_repos,
        selected_hot_paths,
    )
    task_status.started()
    cancelled_exc = anyio.get_cancelled_exc_class()
    while True:
        try:
            now = datetime.datetime.now()
            target_time = datetime.time(8, 0)
            if now.time() >= target_time:
                target_date = now.date()
            else:
                target_date = now.date() - datetime.timedelta(days=1)

            last_refresh = await refresh_store.get_last_refresh_date_async(SNAPSHOT_REFRESH_STATE_KEY)
            client = getattr(registry, "client", None)
            daily_sync_due = last_refresh != target_date
            if client is not None and hasattr(client, "sync_offline_snapshots") and (daily_sync_due or selected_hot_paths):
                sync_paths = selected_paths if daily_sync_due else selected_hot_paths
                sync_repos = selected_repos if daily_sync_due else []
                LOGGER.debug(
                    "Starting %s offline snapshot synchronization",
                    "daily" if daily_sync_due else "hot-path",
                )
                sync = client.sync_offline_snapshots
                kwargs = {
                    "paths": sync_paths or None,
                    "repos": sync_repos or None,
                    "check_remote": True,
                    "force": False,
                }
                if inspect.iscoroutinefunction(sync):
                    result = await sync(**kwargs)
                else:
                    result = await run_sync_bounded(sync, workload=SyncWorkload.SDK_IO, **kwargs)
                failures = tuple(getattr(result, "failures", ()) or ())
                updated_repos = tuple(getattr(result, "updated_repos", ()) or ())
                changed = bool(getattr(result, "changed", False))
                if changed and updated_repos and hasattr(registry, "refresh_after_offline_data_update"):
                    refresh = registry.refresh_after_offline_data_update
                    if inspect.iscoroutinefunction(refresh):
                        await refresh(updated_repos=updated_repos)
                    else:
                        await run_sync_bounded(
                            refresh,
                            updated_repos=updated_repos,
                            workload=SyncWorkload.SDK_IO,
                        )
                if failures:
                    LOGGER.warning(
                        "%s snapshot sync had %d failed repositories; it will be retried",
                        "Daily" if daily_sync_due else "Hot-path",
                        len(failures),
                    )
                elif daily_sync_due:
                    await refresh_store.set_last_refresh_date_async(SNAPSHOT_REFRESH_STATE_KEY, target_date)
            await anyio.sleep(poll_interval)

        except cancelled_exc:
            LOGGER.debug("Market refresh loop cancelled.")
            raise
        except Exception as e:
            LOGGER.error(f"Unexpected error in refresh loop: {e}\n{traceback.format_exc()}")
            await anyio.sleep(60)  # Sleep shortly on unexpected error
