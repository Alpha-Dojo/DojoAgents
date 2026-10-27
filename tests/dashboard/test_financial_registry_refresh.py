from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dojoagents.dashboard.services.financial_registry import FinancialDomainRegistry


@pytest.mark.asyncio
async def test_startup_preload_accepts_only_small_store_allowlist() -> None:
    registry = FinancialDomainRegistry()
    registry.sector_store = MagicMock()
    registry.sector_store.load = AsyncMock()
    registry.benchmark_store = MagicMock()
    registry.benchmark_store.load = AsyncMock()

    errors = await registry.preload_startup(("sector_store", "benchmark_store"))

    assert errors == []
    registry.sector_store.load.assert_awaited_once_with()
    registry.benchmark_store.load.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_startup_preload_rejects_heavy_stock_store() -> None:
    registry = FinancialDomainRegistry()

    with pytest.raises(ValueError, match="stock_store"):
        await registry.preload_startup(("stock_store",))


@pytest.mark.asyncio
async def test_kline_repo_update_only_invalidates_kline_dependencies() -> None:
    registry = FinancialDomainRegistry()
    registry.kline_store = MagicMock()
    registry.gateway = MagicMock()
    registry.benchmark_store = MagicMock()
    registry.stock_store = MagicMock()

    await registry.refresh_after_offline_data_update(
        updated_repos=("AlphaDojo/dojo_stock_kline",),
    )

    registry.kline_store.invalidate_repos.assert_called_once_with(
        ("AlphaDojo/dojo_stock_kline",),
    )
    registry.gateway.invalidate_kline_snapshot.assert_called_once_with()
    registry.benchmark_store.load.assert_not_called()
    registry.stock_store.load.assert_not_called()


@pytest.mark.asyncio
async def test_benchmark_repo_update_does_not_clear_kline_cache() -> None:
    registry = FinancialDomainRegistry()
    registry.kline_store = MagicMock()
    registry.gateway = MagicMock()
    registry.benchmark_store = MagicMock()
    registry.benchmark_store.load = AsyncMock()

    await registry.refresh_after_offline_data_update(
        updated_repos=("alphadojo/dojo_benchmark_kline",),
    )

    registry.benchmark_store.load.assert_awaited_once_with()
    registry.kline_store.invalidate_repos.assert_not_called()
    registry.gateway.invalidate_kline_snapshot.assert_not_called()


@pytest.mark.asyncio
async def test_empty_updated_repo_set_is_a_noop() -> None:
    registry = FinancialDomainRegistry()
    registry.kline_store = MagicMock()
    registry.gateway = MagicMock()

    await registry.refresh_after_offline_data_update(updated_repos=())

    registry.kline_store.invalidate_repos.assert_not_called()
    registry.gateway.invalidate_kline_snapshot.assert_not_called()
