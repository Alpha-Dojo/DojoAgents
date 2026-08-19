from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from dojoagents.dashboard.schemas.stock import Stock, StockQuote
from dojoagents.dashboard.schemas.stock_kline import ConstituentKlineBatchResponse, StockKlineBar, StockKlineResponse
from dojoagents.dashboard.jobs.precompute.sector_daily import (
    CONSTITUENT_COLUMNS,
    MANIFEST_FILE,
    SECTOR_DAILY_COLUMNS,
    TICKER_DAILY_COLUMNS,
    PrecomputeInputSnapshot,
    build_sector_precomputed,
    compute_and_stage_sector_precomputed,
    validate_precompute_market_coverage,
)
from dojoagents.dashboard.services.sector_precomputed_store import SectorPrecomputedStore
from dojoagents.dashboard.services.sector_store import ResolvedSectorPath
from dojoagents.dashboard.services.stock_sector_store import SectorAssignment


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
        return self._response(symbol)

    async def get_klines(self, symbols: list[str], **kwargs):
        self.calls.append({"symbols": symbols, **kwargs})
        return ConstituentKlineBatchResponse(
            as_of="2025-01-03",
            items={symbol: self._response(symbol) for symbol in symbols},
        )

    @staticmethod
    def _response(symbol: str) -> StockKlineResponse:
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
        quote_type="EQUITY",
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
    kline_store = StubKlineStore()
    manifest = await build_sector_precomputed(
        data_root=tmp_path,
        sector_store=StubSectorStore(path),
        stock_sector_store=StubStockSectorStore(assignment),
        stock_store=StubStockStore(stock),
        kline_store=kline_store,
        start_date="2025-01-02",
        upload_client=upload_client,
    )

    out_dir = Path(manifest["published_dir"])
    assert out_dir.exists()
    saved_manifest = json.loads((out_dir / MANIFEST_FILE).read_text(encoding="utf-8"))
    assert saved_manifest["schema_version"] == "3"
    assert manifest["uploaded_dataset"] == "dojo_sector_precomputed"
    assert upload_client.uploads == [("dojo_sector_precomputed", str(out_dir))]
    assert len(kline_store.calls) == 1
    assert kline_store.calls[0]["symbols"] == ["AAA"]

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


def test_validate_precompute_market_coverage_displays_cn_alias() -> None:
    with pytest.raises(ValueError, match="Market 'cn'.*0 eligible constituents"):
        validate_precompute_market_coverage({"markets": {"sh": {"candidate_assignments": 10, "eligible_constituents": 0, "missing_quote": 10, "missing_stock": 0}}})


def test_validate_precompute_market_coverage_allows_healthy_markets() -> None:
    validate_precompute_market_coverage(
        {
            "markets": {
                "us": {"candidate_assignments": 100, "eligible_constituents": 80, "missing_quote": 10},
                "sh": {"candidate_assignments": 50, "eligible_constituents": 50, "missing_quote": 0},
            }
        }
    )


def test_market_increment_preserves_other_markets_and_earlier_dates(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    out_dir = tmp_path / "dojo_sector_precomputed"
    out_dir.mkdir()

    def constituent(market: str, ticker: str) -> dict:
        return dict.fromkeys(CONSTITUENT_COLUMNS) | {
            "level1_id": "1",
            "level2_id": "2",
            "level3_id": "3",
            "market": market,
            "ticker": ticker,
            "role": "primary",
            "market_cap": 2e9,
            "pe": 20.0,
        }

    def ticker(market: str, ticker_name: str, trade_date: str) -> dict:
        return dict.fromkeys(TICKER_DAILY_COLUMNS) | {"market": market, "ticker": ticker_name, "trade_date": trade_date, "close": 10.0}

    def sector(market: str, trade_date: str) -> dict:
        return dict.fromkeys(SECTOR_DAILY_COLUMNS) | {
            "trade_date": trade_date,
            "scope": "L3",
            "market": market,
            "level1_id": "1",
            "level2_id": "2",
            "level3_id": "3",
        }

    pd.DataFrame([constituent("us", "US"), constituent("sh", "OLD")])[CONSTITUENT_COLUMNS].to_parquet(out_dir / "constituents.parquet", index=False)
    pd.DataFrame([ticker("us", "US", "2026-08-10"), ticker("sh", "OLD", "2026-08-10")])[TICKER_DAILY_COLUMNS].to_parquet(out_dir / "ticker_daily.parquet", index=False)
    pd.DataFrame([sector("us", "2026-08-10"), sector("sh", "2026-08-10")])[SECTOR_DAILY_COLUMNS].to_parquet(out_dir / "sector_daily.parquet", index=False)

    new_frames = (
        pd.DataFrame([constituent("sh", "NEW")])[CONSTITUENT_COLUMNS],
        pd.DataFrame([ticker("sh", "NEW", "2026-08-11")])[TICKER_DAILY_COLUMNS],
        pd.DataFrame([sector("sh", "2026-08-11")])[SECTOR_DAILY_COLUMNS],
        {"files": {}},
    )
    monkeypatch.setattr("dojoagents.dashboard.jobs.precompute.sector_daily.compute_sector_precomputed_frames", lambda _snapshot: new_frames)
    snapshot = PrecomputeInputSnapshot("2026-08-11", None, "2026-08-11T00:00:00Z", [], [], {"markets": {}})

    _manifest, staging_dir = compute_and_stage_sector_precomputed(snapshot, out_dir, "sh")

    constituents = pd.read_parquet(staging_dir / "constituents.parquet")
    ticker_daily = pd.read_parquet(staging_dir / "ticker_daily.parquet")
    assert set(constituents["ticker"]) == {"US", "NEW"}
    assert set(ticker_daily["trade_date"]) == {"2026-08-10", "2026-08-11"}
