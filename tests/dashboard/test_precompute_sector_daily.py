from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from dojoagents.harnesses.built_in.financial.contracts.stock import Stock, StockQuote
from dojoagents.harnesses.built_in.financial.contracts.stock_kline import StockKlineBar, StockKlineResponse
from dojoagents.harnesses.built_in.financial.pipelines.precompute_sector_daily import (
    MANIFEST_FILE,
    build_sector_precomputed,
    validate_precompute_market_coverage,
)
from dojoagents.harnesses.built_in.financial.services.sector_precomputed_store import SectorPrecomputedStore
from dojoagents.harnesses.built_in.financial.services.sector_store import ResolvedSectorPath
from dojoagents.harnesses.built_in.financial.services.stock_sector_store import SectorAssignment


class StubSectorStore:
    def __init__(self, path: ResolvedSectorPath) -> None:
        self._path = path

    def iter_resolved_paths(self):
        yield self._path


class StubStockSectorStore:
    def __init__(self, assignment: SectorAssignment) -> None:
        self._assignment = assignment

    def unresolved_assignments(self, sector_store) -> list[dict[str, str]]:
        return []

    def assignments_for_path(self, path, *, sector_store, market=None, scope="L3"):
        if market and market != self._assignment.market:
            return []
        return [self._assignment]


class StubStockStore:
    def __init__(self, stock: Stock) -> None:
        self.stock = stock

    def get(self, market: str, ticker: str) -> Stock | None:
        if market == self.stock.market and ticker == self.stock.ticker:
            return self.stock
        return None


class StubKlineStore:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def get_or_fetch_kline(self, symbol: str, **kwargs):
        self.calls.append({"symbol": symbol, **kwargs})
        return StockKlineResponse(
            symbol=symbol,
            as_of="2025-01-03",
            bars=[
                StockKlineBar(symbol=symbol, bar_time="2024-12-31", close=100, open=100, high=100, low=100, vol=10),
                StockKlineBar(symbol=symbol, bar_time="2025-01-02", close=110, open=110, high=110, low=110, vol=12),
                StockKlineBar(symbol=symbol, bar_time="2025-01-03", close=121, open=121, high=121, low=121, vol=13),
            ],
        )


class StubDojoClient:
    class Sectors:
        def get_precomputed_constituents(self):
            return type("Resp", (), {"data": []})()

        def get_precomputed_sector_daily(self):
            return type("Resp", (), {"data": []})()

        def get_precomputed_ticker_daily(self):
            return type("Resp", (), {"data": []})()

    def __init__(self) -> None:
        self.sectors = self.Sectors()
        self.uploads: list[tuple[str, str]] = []

    async def upload_dataset(self, dataset_name: str, path: str) -> None:
        self.uploads.append((dataset_name, path))


@pytest.mark.asyncio
async def test_build_sector_precomputed_publishes_market_aware_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DOJO_HF_OFFLINE", "true")
    path = ResolvedSectorPath(
        level1_id="L1",
        level2_id="L2",
        level3_id="L3",
        level1_zh="一级",
        level1_en="Level1",
        level2_zh="二级",
        level2_en="Level2",
        level3_zh="三级",
        level3_en="Level3",
    )
    assignment = SectorAssignment(ticker="AAA", market="sh", role="primary", path=path)
    stock = Stock(
        ticker="AAA",
        market="sh",
        short_name="AAA",
        stock_quote=StockQuote(
            ticker="AAA",
            name="AAA",
            last_price=121,
            pre_close=110,
            open=121,
            high=121,
            low=121,
            change=11,
            change_percent=10,
            volume=10,
            amount=10,
            avg_price=121,
            market_cap=2e9,
            total_shares=10,
            turn_rate=1,
            pe=20,
            pb=2,
            dividend_yield=0,
        ),
    )
    upload_client = StubDojoClient()
    manifest = await build_sector_precomputed(
        data_root=tmp_path,
        sector_store=StubSectorStore(path),
        stock_sector_store=StubStockSectorStore(assignment),
        stock_store=StubStockStore(stock),
        kline_store=StubKlineStore(),
        start_date="2025-01-02",
        upload_client=upload_client,
    )

    out_dir = Path(manifest["published_dir"])
    assert out_dir.exists()
    saved_manifest = json.loads((out_dir / MANIFEST_FILE).read_text(encoding="utf-8"))
    assert saved_manifest["schema_version"] == "3"
    assert manifest["uploaded_dataset"] == "dojo_sector_precomputed"
    assert upload_client.uploads == [("dojo_sector_precomputed", str(out_dir))]

    ticker_daily = pd.read_parquet(out_dir / "ticker_daily.parquet")
    assert list(ticker_daily["market"].unique()) == ["sh"]
    assert list(ticker_daily["trade_date"]) == ["2025-01-02", "2025-01-03"]
    assert ticker_daily.iloc[0]["daily_return_pct"] == pytest.approx(10.0)

    constituents = pd.read_parquet(out_dir / "constituents.parquet")
    assert constituents.iloc[0]["role"] == "primary"
    assert constituents.iloc[0]["market"] == "sh"

    store = SectorPrecomputedStore(tmp_path)
    store.reload(out_dir)
    assert store.available() is True
    assert store.get_sector_constituents("L1", "L2", "L3", market="cn")[0]["market"] == "sh"


@pytest.mark.asyncio
async def test_build_sector_precomputed_excludes_below_ticker_cap_floor(tmp_path: Path) -> None:
    path = ResolvedSectorPath(
        level1_id="L1",
        level2_id="L2",
        level3_id="L3",
        level1_zh="一级",
        level1_en="Level1",
        level2_zh="二级",
        level2_en="Level2",
        level3_zh="三级",
        level3_en="Level3",
    )
    assignment = SectorAssignment(ticker="TINY", market="us", role="primary", path=path)
    stock = Stock(
        ticker="TINY",
        market="us",
        short_name="TINY",
        stock_quote=StockQuote(
            ticker="TINY",
            name="TINY",
            last_price=10,
            pre_close=9,
            open=10,
            high=10,
            low=10,
            change=1,
            change_percent=10,
            volume=10,
            amount=10,
            avg_price=10,
            market_cap=5e8,  # below ~10亿 ticker floor
            total_shares=10,
            turn_rate=1,
            pe=20,
            pb=2,
            dividend_yield=0,
        ),
    )

    with pytest.raises(ValueError, match="0 eligible constituents"):
        await build_sector_precomputed(
            data_root=tmp_path,
            sector_store=StubSectorStore(path),
            stock_sector_store=StubStockSectorStore(assignment),
            stock_store=StubStockStore(stock),
            kline_store=StubKlineStore(),
            start_date="2025-01-02",
            upload_client=StubDojoClient(),
        )


def test_validate_precompute_market_coverage_rejects_dropped_market() -> None:
    with pytest.raises(ValueError, match="Market 'us'.*0 eligible constituents"):
        validate_precompute_market_coverage(
            {
                "markets": {
                    "us": {
                        "candidate_assignments": 100,
                        "eligible_constituents": 0,
                        "missing_quote": 99,
                        "missing_stock": 1,
                    },
                    "sh": {
                        "candidate_assignments": 50,
                        "eligible_constituents": 40,
                        "missing_quote": 0,
                        "missing_stock": 0,
                    },
                }
            }
        )


def test_validate_precompute_market_coverage_allows_healthy_markets() -> None:
    validate_precompute_market_coverage(
        {
            "markets": {
                "us": {"candidate_assignments": 100, "eligible_constituents": 80, "missing_quote": 10},
                "sh": {"candidate_assignments": 50, "eligible_constituents": 50, "missing_quote": 0},
            }
        }
    )
