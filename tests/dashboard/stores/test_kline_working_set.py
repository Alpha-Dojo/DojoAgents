from __future__ import annotations

import pytest

import dojoagents.dashboard.services.kline_store as kline_store_module
from dojoagents.dashboard.services.dojo_data_gateway import GatewayResult
from dojoagents.dashboard.services.kline_store import KlineStore
from dojoagents.dashboard.services.stock_sector_store import StockSectorStore
from dojoagents.dashboard.services.stock_store import StockStore
from tests.dashboard.fakes.fake_dojo import FakeDojo


class KlineGateway:
    def __init__(
        self,
        responses: list[list[dict]] | None = None,
        *,
        snapshot: dict[str, str] | None = None,
    ) -> None:
        self.responses = list(responses or [])
        self.snapshot = snapshot
        self.calls: list[tuple[str, list[str], dict]] = []
        self.all_klines_calls: list[dict[str, object]] = []

    async def stock_klines(self, market, symbols, **window):
        self.calls.append((market, symbols, window))
        if not self.responses:
            return GatewayResult([], None, "sdk_online", False)
        return GatewayResult(
            self.responses.pop(0),
            None,
            "sdk_snapshot" if self.snapshot else "sdk_online",
            False,
            self.snapshot,
        )


def _store(gateway, tmp_path) -> KlineStore:
    client = FakeDojo()
    return KlineStore(
        gateway,
        StockStore(client),
        StockSectorStore(client),
        data_root=tmp_path,
    )


@pytest.mark.asyncio
async def test_kline_store_uses_sdk_frame_and_does_not_create_working_set(tmp_path) -> None:
    gateway = KlineGateway(
        [
            [
                {"symbol": "AAPL", "bar_time": "2026-06-18", "close": 98},
                {"symbol": "AAPL", "bar_time": "2026-06-19", "close": 99},
                {"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100},
            ]
        ]
    )
    store = _store(gateway, tmp_path)
    await store.load()

    assert not (tmp_path / "working-set" / "dojo_stock_kline.parquet").exists()
    assert gateway.all_klines_calls == []

    result = await store.get_or_fetch_kline(
        " aapl ",
        market="US",
        kline_t="1D",
        price_adj_type="none",
        start_time="2026-06-19",
        end_time="2026-06-20",
        limit=1,
    )

    assert result is not None
    assert [bar.bar_time for bar in result.bars] == ["2026-06-20"]
    assert result.symbol == "AAPL"


@pytest.mark.asyncio
async def test_refresh_bypasses_response_cache(tmp_path) -> None:
    gateway = KlineGateway(
        [
            [
                {"symbol": "AAPL", "bar_time": "2026-06-19", "close": 99},
                {"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100},
            ],
            [
                {"symbol": "AAPL", "bar_time": "2026-06-20", "close": 101},
                {"symbol": "AAPL", "bar_time": "2026-06-21", "close": 102},
            ],
        ]
    )
    store = _store(gateway, tmp_path)

    await store.get_or_fetch_kline("AAPL", market="us")
    result = await store.get_or_fetch_kline("AAPL", market="us", refresh=True)

    assert result is not None
    assert [(bar.bar_time, bar.close) for bar in result.bars] == [
        ("2026-06-20", 101),
        ("2026-06-21", 102),
    ]
    assert len(gateway.calls) == 2


@pytest.mark.asyncio
async def test_new_store_reads_from_sdk_instead_of_local_working_set(tmp_path) -> None:
    gateway = KlineGateway([[{"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100}]])
    result = await _store(gateway, tmp_path).get_or_fetch_kline("aapl", market="us")

    assert result is not None
    assert result.bars[0].close == 100
    assert len(gateway.calls) == 1


@pytest.mark.asyncio
async def test_legacy_working_set_is_ignored(tmp_path) -> None:
    path = tmp_path / "working-set" / "dojo_stock_kline.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"broken")

    gateway = KlineGateway([[{"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100}]])

    result = await _store(gateway, tmp_path).get_or_fetch_kline("AAPL", market="us")

    assert result is not None
    assert result.bars[0].close == 100
    assert len(gateway.calls) == 1


@pytest.mark.asyncio
async def test_load_is_no_io_lifecycle_hook(tmp_path) -> None:
    gateway = KlineGateway([[{"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100}]])
    client = FakeDojo()
    stock_store = StockStore(client)
    store = KlineStore(
        gateway,
        stock_store,
        StockSectorStore(client),
        data_root=tmp_path,
    )

    await store.load(limit=252)

    assert store.initial_load_complete is True
    assert store.member_symbols == 0
    assert gateway.all_klines_calls == []
    assert gateway.calls == []

    result = await store.get_or_fetch_kline("AAPL", market="us", limit=252)

    assert result is not None
    assert result.bars[0].close == 100
    assert len(gateway.calls) == 1


@pytest.mark.asyncio
async def test_fetches_again_when_cached_window_does_not_cover_requested_start(tmp_path) -> None:
    gateway = KlineGateway(
        [
            [{"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100}],
            [
                {"symbol": "AAPL", "bar_time": "2025-01-01", "close": 80},
                {"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100},
            ],
        ]
    )
    store = _store(gateway, tmp_path)

    first = await store.get_or_fetch_kline("AAPL", market="us", limit=1)
    second = await store.get_or_fetch_kline(
        "AAPL",
        market="us",
        start_time="2025-01-01",
        end_time="2026-06-20",
        limit=0,
    )

    assert first is not None
    assert second is not None
    assert [bar.bar_time for bar in second.bars] == ["2025-01-01", "2026-06-20"]
    assert len(gateway.calls) == 2


@pytest.mark.asyncio
async def test_get_klines_batch_fetch_logic(tmp_path) -> None:
    gateway = KlineGateway(
        [
            [
                {"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100},
                {"symbol": "MSFT", "bar_time": "2026-06-20", "close": 200},
            ]
        ]
    )
    client = FakeDojo()
    stock_store = StockStore(client)
    stock_store.by_ticker = {
        "us:AAPL": type("Stock", (), {"ticker": "AAPL"})(),
        "us:MSFT": type("Stock", (), {"ticker": "MSFT"})(),
    }
    store = KlineStore(
        gateway,
        stock_store,
        StockSectorStore(client),
        data_root=tmp_path,
    )

    result = await store.get_klines(["AAPL", "MSFT"], limit=15)

    assert set(result.items.keys()) == {"AAPL", "MSFT"}
    assert gateway.calls == [(None, ["AAPL", "MSFT"], {"limit": 15})]


@pytest.mark.asyncio
async def test_get_klines_forwards_precompute_window_to_sdk_gateway(tmp_path) -> None:
    gateway = KlineGateway([[{"symbol": "AAPL", "bar_time": "2026-08-12", "close": 100}]])
    store = _store(gateway, tmp_path)

    result = await store.get_klines(
        ["AAPL"],
        limit=0,
        market="us",
        start_time="2026-07-03",
        end_time="2026-08-12",
        price_adj_type="pre",
        refresh=True,
    )

    assert list(result.items) == ["AAPL"]
    assert gateway.calls == [
        (
            "us",
            ["AAPL"],
            {
                "limit": 0,
                "start_time": "2026-07-03",
                "end_time": "2026-08-12",
                "price_adj_type": "pre",
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_klines_forwards_dynamic_fields_and_keys_cache_by_projection(tmp_path) -> None:
    gateway = KlineGateway(
        [[{"symbol": "AAPL", "bar_time": "2026-08-12", "close": 100}]]
    )
    store = _store(gateway, tmp_path)

    result = await store.get_klines(
        ["AAPL"],
        limit=1,
        fields=["close", "vol", "close"],
    )

    assert list(result.items) == ["AAPL"]
    assert gateway.calls == [
        (None, ["AAPL"], {"limit": 1, "fields": ("close", "vol")})
    ]
    assert next(iter(store._cache)).fields == ("close", "vol")


@pytest.mark.asyncio
async def test_response_cache_is_lru_bounded_and_revision_aware(tmp_path) -> None:
    rows = [
        [{"symbol": symbol, "bar_time": "2026-06-20", "close": price}]
        for symbol, price in (("AAPL", 100), ("MSFT", 200), ("NVDA", 300))
    ]
    snapshot = {
        "backend": "huggingface",
        "repo_id": "AlphaDojo/dojo_stock_kline",
        "resolved_revision": "revision-1",
        "snapshot_token": "token-1",
    }
    gateway = KlineGateway(rows, snapshot=snapshot)
    client = FakeDojo()
    store = KlineStore(
        gateway,
        StockStore(client),
        StockSectorStore(client),
        data_root=tmp_path,
        response_cache_max_entries=2,
    )

    await store.get_or_fetch_kline("AAPL", limit=1)
    await store.get_or_fetch_kline("MSFT", limit=1)
    await store.get_or_fetch_kline("AAPL", limit=1)  # promote AAPL to MRU
    await store.get_or_fetch_kline("NVDA", limit=1)

    assert len(gateway.calls) == 3
    assert len(store._cache) == 2
    assert {key.symbols for key in store._cache} == {("AAPL",), ("NVDA",)}
    assert {key.snapshot_token for key in store._cache} == {"token-1"}
    assert {key.resolved_revision for key in store._cache} == {"revision-1"}


@pytest.mark.asyncio
async def test_response_cache_ttl_expires_without_retaining_frames(tmp_path, monkeypatch) -> None:
    clock = [10.0]
    monkeypatch.setattr(kline_store_module.time, "monotonic", lambda: clock[0])
    gateway = KlineGateway(
        [
            [{"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100}],
            [{"symbol": "AAPL", "bar_time": "2026-06-21", "close": 101}],
        ]
    )
    client = FakeDojo()
    store = KlineStore(
        gateway,
        StockStore(client),
        StockSectorStore(client),
        data_root=tmp_path,
        response_cache_ttl_seconds=5,
    )

    first = await store.get_or_fetch_kline("AAPL", limit=1)
    clock[0] = 14.0
    cached = await store.get_or_fetch_kline("AAPL", limit=1)
    clock[0] = 16.0
    refreshed = await store.get_or_fetch_kline("AAPL", limit=1)

    assert first is cached
    assert refreshed is not None and refreshed.as_of == "2026-06-21"
    assert len(gateway.calls) == 2
    assert not hasattr(store, "_in_memory_updates")
    assert all(
        isinstance(entry.response, kline_store_module.StockKlineResponse)
        for entry in store._cache.values()
    )


@pytest.mark.asyncio
async def test_response_larger_than_byte_budget_is_not_cached(tmp_path) -> None:
    gateway = KlineGateway(
        [
            [{"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100}],
            [{"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100}],
        ]
    )
    client = FakeDojo()
    store = KlineStore(
        gateway,
        StockStore(client),
        StockSectorStore(client),
        data_root=tmp_path,
        response_cache_max_bytes=1,
    )

    await store.get_or_fetch_kline("AAPL", limit=1)
    await store.get_or_fetch_kline("AAPL", limit=1)

    assert len(gateway.calls) == 2
    assert not store._cache
    assert store._cache_estimated_bytes == 0


@pytest.mark.asyncio
async def test_batch_response_cache_key_covers_query_dimensions(tmp_path) -> None:
    snapshot = {
        "backend": "modelscope",
        "repo_id": "alphadojo/dojo_stock_kline",
        "resolved_revision": "revision-ms",
        "snapshot_token": "token-ms",
    }
    gateway = KlineGateway(
        [[{"symbol": "AAPL", "bar_time": "2026-06-20", "close": 100}]],
        snapshot=snapshot,
    )
    store = _store(gateway, tmp_path)

    await store.get_klines(
        ["AAPL"],
        limit=5,
        market="us",
        start_time="2026-06-01",
        end_time="2026-06-20",
        price_adj_type="post",
    )

    key = next(iter(store._cache))
    assert key.symbols == ("AAPL",)
    assert key.start_time == "2026-06-01"
    assert key.end_time == "2026-06-20"
    assert key.fields == tuple(kline_store_module.KLINE_QUERY_FIELDS)
    assert key.adjust == "post"
    assert key.limit_per_symbol == 5
    assert key.backend == "modelscope"
    assert key.repo_id == "alphadojo/dojo_stock_kline"
    assert key.resolved_revision == "revision-ms"
    assert key.snapshot_token == "token-ms"
