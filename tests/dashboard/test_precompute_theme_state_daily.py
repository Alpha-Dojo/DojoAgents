from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from dojoagents.harnesses.built_in.financial.pipelines.precompute_sector_daily import (
    CONSTITUENTS_FILE,
    MANIFEST_FILE as PHASE_A_MANIFEST,
    PRECOMPUTE_DIR,
    SECTOR_DAILY_FILE,
    TICKER_DAILY_FILE,
)
from dojoagents.harnesses.built_in.financial.pipelines.precompute_sector_horizon import SECTOR_HORIZON_METRICS_FILE
from dojoagents.harnesses.built_in.financial.pipelines.precompute_sector_radar_advice import (
    SECTOR_ADVICE_DAILY_FILE,
    SECTOR_HEALTH_RADAR_FILE,
)
from dojoagents.harnesses.built_in.financial.pipelines.precompute_theme_state_daily import (
    FUNDAMENTALS_PERIOD_FILE,
    MANIFEST_FILE,
    MARKET_BENCHMARK_DAILY_FILE,
    THEME_STATE_DAILY_FILE,
    build_theme_state_precomputed,
    compute_theme_state_frames,
)
from dojoagents.harnesses.built_in.financial.services.theme_state_precomputed_store import ThemeStatePrecomputedStore


def _write_phase_a(tmp_path: Path) -> Path:
    out = tmp_path / PRECOMPUTE_DIR
    out.mkdir(parents=True, exist_ok=True)

    constituents = pd.DataFrame(
        [
            {
                "level1_id": "L1",
                "level2_id": "L2",
                "level3_id": "L3A",
                "market": "us",
                "ticker": "AAA",
                "role": "primary",
                "market_cap": 2e9,
                "pe": 20.0,
            },
            {
                "level1_id": "L1",
                "level2_id": "L2",
                "level3_id": "L3A",
                "market": "us",
                "ticker": "BBB",
                "role": "secondary",
                "market_cap": 3e9,
                "pe": 15.0,
            },
            {
                "level1_id": "L1",
                "level2_id": "L2",
                "level3_id": "L3A",
                "market": "us",
                "ticker": "CCC",
                "role": "primary",
                "market_cap": 4e9,
                "pe": 18.0,
            },
            {
                "level1_id": "L1",
                "level2_id": "L2",
                "level3_id": "L3A",
                "market": "us",
                "ticker": "DDD",
                "role": "primary",
                "market_cap": 5e9,
                "pe": 12.0,
            },
            {
                "level1_id": "L1",
                "level2_id": "L2",
                "level3_id": "L3A",
                "market": "us",
                "ticker": "EEE",
                "role": "primary",
                "market_cap": 6e9,
                "pe": 10.0,
            },
            {
                "level1_id": "L1",
                "level2_id": "L2",
                "level3_id": "L3B",
                "market": "us",
                "ticker": "FFF",
                "role": "primary",
                "market_cap": 2e9,
                "pe": 22.0,
            },
            {
                "level1_id": "L1",
                "level2_id": "L2",
                "level3_id": "L3B",
                "market": "us",
                "ticker": "GGG",
                "role": "primary",
                "market_cap": 2e9,
                "pe": 22.0,
            },
            {
                "level1_id": "L1",
                "level2_id": "L2",
                "level3_id": "L3B",
                "market": "us",
                "ticker": "HHH",
                "role": "primary",
                "market_cap": 2e9,
                "pe": 22.0,
            },
            {
                "level1_id": "L1",
                "level2_id": "L2",
                "level3_id": "L3B",
                "market": "us",
                "ticker": "III",
                "role": "primary",
                "market_cap": 2e9,
                "pe": 22.0,
            },
            {
                "level1_id": "L1",
                "level2_id": "L2",
                "level3_id": "L3B",
                "market": "us",
                "ticker": "JJJ",
                "role": "secondary",
                "market_cap": 2e9,
                "pe": 22.0,
            },
        ]
    )

    dates = pd.bdate_range("2025-01-02", periods=25).strftime("%Y-%m-%d").tolist()
    ticker_rows = []
    for ticker, base in [
        ("AAA", 100),
        ("BBB", 100),
        ("CCC", 100),
        ("DDD", 100),
        ("EEE", 100),
        ("FFF", 100),
        ("GGG", 100),
        ("HHH", 100),
        ("III", 100),
        ("JJJ", 100),
    ]:
        close = float(base)
        for i, trade_date in enumerate(dates):
            prev = close
            close = close * (1.02 if ticker.startswith(("A", "B", "C", "D", "E")) else 0.99)
            daily_ret = ((close / prev) - 1.0) * 100.0 if i else 0.0
            ticker_rows.append(
                {
                    "market": "us",
                    "ticker": ticker,
                    "trade_date": trade_date,
                    "close": close,
                    "daily_return_pct": daily_ret,
                    "cumulative_return_pct": ((close / base) - 1.0) * 100.0,
                    "volume": 100.0 + i * 10.0 if ticker != "AAA" else 100.0 + i * 50.0,
                }
            )
    ticker_daily = pd.DataFrame(ticker_rows)

    sector_rows = []
    for level3_id, growth in (("L3A", 1.02), ("L3B", 0.99)):
        level = 100.0
        for i, trade_date in enumerate(dates):
            prev = level
            if i:
                level *= growth
            sector_rows.append(
                {
                    "trade_date": trade_date,
                    "scope": "L3",
                    "market": "us",
                    "level1_id": "L1",
                    "level2_id": "L2",
                    "level3_id": level3_id,
                    "member_count": 5,
                    "member_count_with_return": 5,
                    "total_market_cap": 1e10,
                    "effective_weight_sum": 1.0,
                    "weighted_pe": 15.0,
                    "index_level": level,
                    "daily_return_pct": ((level / prev) - 1.0) * 100.0 if i else 0.0,
                }
            )
    sector_daily = pd.DataFrame(sector_rows)

    constituents.to_parquet(out / CONSTITUENTS_FILE, index=False)
    ticker_daily.to_parquet(out / TICKER_DAILY_FILE, index=False)
    sector_daily.to_parquet(out / SECTOR_DAILY_FILE, index=False)
    (out / PHASE_A_MANIFEST).write_text(
        json.dumps(
            {
                "schema_version": "3",
                "build_id": "test",
                "generated_at": f"{dates[-1]}T00:00:00Z",
                "window_start": dates[0],
                "window_end": dates[-1],
                "latest_trade_date_by_market": {"us": dates[-1]},
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return out


def test_compute_theme_state_frames_includes_primary_and_secondary() -> None:
    constituents = pd.DataFrame(
        [
            {
                "level1_id": "L1",
                "level2_id": "L2",
                "level3_id": "L3A",
                "market": "us",
                "ticker": "AAA",
                "role": "primary",
                "market_cap": 2e9,
                "pe": 20.0,
            },
            {
                "level1_id": "L1",
                "level2_id": "L2",
                "level3_id": "L3A",
                "market": "us",
                "ticker": "BBB",
                "role": "secondary",
                "market_cap": 3e9,
                "pe": 15.0,
            },
            {
                "level1_id": "L1",
                "level2_id": "L2",
                "level3_id": "L3A",
                "market": "us",
                "ticker": "CCC",
                "role": "primary",
                "market_cap": 4e9,
                "pe": 18.0,
            },
            {
                "level1_id": "L1",
                "level2_id": "L2",
                "level3_id": "L3A",
                "market": "us",
                "ticker": "DDD",
                "role": "primary",
                "market_cap": 5e9,
                "pe": 12.0,
            },
            {
                "level1_id": "L1",
                "level2_id": "L2",
                "level3_id": "L3A",
                "market": "us",
                "ticker": "EEE",
                "role": "primary",
                "market_cap": 6e9,
                "pe": 10.0,
            },
        ]
    )
    dates = [f"2025-01-{day:02d}" for day in range(2, 12)]
    ticker_rows = []
    for ticker in ["AAA", "BBB", "CCC", "DDD", "EEE"]:
        close = 100.0
        for i, trade_date in enumerate(dates):
            prev = close
            close *= 1.01
            ticker_rows.append(
                {
                    "market": "us",
                    "ticker": ticker,
                    "trade_date": trade_date,
                    "close": close,
                    "daily_return_pct": ((close / prev) - 1.0) * 100.0 if i else 1.0,
                    "cumulative_return_pct": ((close / 100.0) - 1.0) * 100.0,
                    "volume": 200.0 if ticker == "AAA" else 100.0,
                }
            )
    ticker_daily = pd.DataFrame(ticker_rows)
    sector_rows = []
    level = 100.0
    for i, trade_date in enumerate(dates):
        prev = level
        if i:
            level *= 1.01
        sector_rows.append(
            {
                "trade_date": trade_date,
                "scope": "L3",
                "market": "us",
                "level1_id": "L1",
                "level2_id": "L2",
                "level3_id": "L3A",
                "member_count": 5,
                "member_count_with_return": 5,
                "total_market_cap": 2e10,
                "effective_weight_sum": 1.0,
                "weighted_pe": 15.0,
                "index_level": level,
                "daily_return_pct": ((level / prev) - 1.0) * 100.0 if i else 0.0,
            }
        )
    sector_daily = pd.DataFrame(sector_rows)

    fin = {
        ("us", "L1", "L2", "L3A"): {
            "fin_status": "ok",
            "fin_report_period": "2026:q1",
            "fin_prior_year_period": "2025:q1",
            "fin_sample_count": 5,
            "fin_coverage_ratio": 1.0,
            "industry_revenue": 500.0,
            "industry_revenue_prior_year": 400.0,
            "industry_revenue_yoy_pct": 25.0,
            "industry_revenue_yoy_prior_pct": 10.0,
            "industry_revenue_accel_pp": 15.0,
            "revenue_improvers_count": 5,
            "revenue_improvers_pct": 100.0,
            "industry_net_profit": 50.0,
            "industry_net_profit_yoy_pct": 20.0,
            "profit_improvers_count": 4,
            "profit_improvers_pct": 80.0,
            "industry_net_margin_pct": 10.0,
            "industry_net_margin_change_pp": 1.0,
            "stage_hint": "expanding",
            "stage_hint_rule": "revenue_lite_v1",
            "report_period_key": "2026:q1",
        }
    }

    theme_df, bench_df, fin_df = compute_theme_state_frames(
        constituents=constituents,
        ticker_daily=ticker_daily,
        sector_daily=sector_daily,
        link_key_by_level3={"L3A": "theme-a"},
        fundamentals_by_theme=fin,
    )
    assert not theme_df.empty
    latest = theme_df.sort_values("trade_date").iloc[-1]
    assert latest["eligible_count"] == 5
    assert latest["primary_count"] == 4
    assert latest["secondary_count"] == 1
    assert latest["role_filter"] == "primary+secondary"
    assert latest["link_key"] == "theme-a"
    assert latest["stage_hint"] == "expanding"
    assert latest["return_5d_pct"] == pytest.approx(((1.01**4) - 1.0) * 100.0, rel=1e-3)
    assert not bench_df.empty
    assert not fin_df.empty
    assert fin_df.iloc[0]["stage_hint"] == "expanding"


@pytest.mark.asyncio
async def test_build_theme_state_precomputed_publishes_snapshot(tmp_path: Path) -> None:
    _write_phase_a(tmp_path)
    manifest = await build_theme_state_precomputed(
        data_root=tmp_path,
        sector_store=None,
        kline_store=None,
        benchmark_store=None,
        fin_store=None,
        skip_fundamentals=True,
        skip_volume_enrich=True,
    )
    out_dir = Path(manifest["published_dir"])
    assert out_dir == tmp_path / PRECOMPUTE_DIR
    saved = json.loads((out_dir / MANIFEST_FILE).read_text(encoding="utf-8"))
    assert saved["schema_version"] == "5"
    assert saved["phase"] == "sector_unified"
    assert saved["phase_a"]["schema_version"] == "3"
    assert saved["rules"]["rotation_rank_rule"] == "rs_z_blend_20d_dominant_x_breadth_v1"
    assert saved["rules"]["horizon_windows"] == [60, 120, 252]
    assert saved["scoring"]["radar_rule"] == "radar_v1"
    assert saved["scoring"]["short_advice_rule"] == "short_advice_v1"
    assert saved["scoring"]["mid_advice_rule"] == "mid_advice_v1"

    # Unified bundle keeps Phase A files alongside theme/horizon/radar/advice tables.
    assert (out_dir / CONSTITUENTS_FILE).exists()
    assert (out_dir / SECTOR_DAILY_FILE).exists()
    assert (out_dir / TICKER_DAILY_FILE).exists()
    assert (out_dir / THEME_STATE_DAILY_FILE).exists()
    assert (out_dir / MARKET_BENCHMARK_DAILY_FILE).exists()
    assert (out_dir / FUNDAMENTALS_PERIOD_FILE).exists()
    assert (out_dir / SECTOR_HORIZON_METRICS_FILE).exists()
    assert (out_dir / SECTOR_HEALTH_RADAR_FILE).exists()
    assert (out_dir / SECTOR_ADVICE_DAILY_FILE).exists()

    theme_df = pd.read_parquet(out_dir / THEME_STATE_DAILY_FILE)
    assert set(theme_df["level3_id"].unique()) == {"L3A", "L3B"}
    # L3A should rank ahead of L3B on default rotation score (stronger multi-window RS).
    last_date = theme_df["trade_date"].max()
    day = theme_df[theme_df["trade_date"] == last_date].set_index("level3_id")
    assert int(day.loc["L3A", "rotation_rank"]) == 1
    assert int(day.loc["L3B", "rotation_rank"]) == 2
    assert int(day.loc["L3A", "rs_rank_5d"]) == 1
    assert int(day.loc["L3B", "rs_rank_5d"]) == 2
    assert float(day.loc["L3A", "rotation_score"]) > float(day.loc["L3B", "rotation_score"])

    horizon_df = pd.read_parquet(out_dir / SECTOR_HORIZON_METRICS_FILE)
    assert not horizon_df.empty
    assert "return_60d_pct" in horizon_df.columns
    assert set(horizon_df["level3_id"].unique()) == {"L3A", "L3B"}

    store = ThemeStatePrecomputedStore(tmp_path)
    store.reload()
    assert store.available() is True
    assert store.dataset_dir == out_dir
    row = store.get_theme_state(level1_id="L1", level2_id="L2", level3_id="L3A", market="us")
    assert row is not None
    assert row["eligible_count"] == 5
    assert row["primary_count"] == 4
    assert row["secondary_count"] == 1
    rotation = store.list_rotation(market="us", limit=10)
    assert rotation[0]["level3_id"] == "L3A"
    horizon = store.get_horizon_metrics(level1_id="L1", level2_id="L2", level3_id="L3A", market="us")
    assert horizon is not None
    assert horizon["row_status"] in {"ok", "partial", "insufficient_history"}
    radar = store.get_health_radar(level1_id="L1", level2_id="L2", level3_id="L3A", market="us")
    assert radar is not None
    assert "overall_score" in radar
    assert "score_capital_heat" in radar
    advice = store.get_advice(level1_id="L1", level2_id="L2", level3_id="L3A", market="us")
    assert advice is not None
    assert "short_score" in advice and "mid_score" in advice
    board = store.list_advice_board(market="us", horizon="short", limit=10)
    assert board
    assert board[0]["short_rank"] == 1


@pytest.mark.asyncio
async def test_build_theme_state_reads_phase_a_from_explicit_dir_and_uploads_output(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "phase-a"
    source_dir = _write_phase_a(source_root)
    output_dir = tmp_path / "published" / PRECOMPUTE_DIR

    class UploadClient:
        def __init__(self) -> None:
            self.uploads: list[tuple[str, str]] = []

        async def upload_dataset(self, dataset_name: str, path: str) -> None:
            self.uploads.append((dataset_name, path))

    client = UploadClient()
    manifest = await build_theme_state_precomputed(
        data_root=tmp_path,
        source_dir=source_dir,
        out_dir=output_dir,
        upload_client=client,
        skip_fundamentals=True,
        skip_volume_enrich=True,
    )

    assert Path(manifest["source_dir"]) == source_dir
    assert Path(manifest["published_dir"]) == output_dir
    assert manifest["uploaded_dataset"] == PRECOMPUTE_DIR
    assert client.uploads == [(PRECOMPUTE_DIR, str(output_dir))]
    assert (output_dir / CONSTITUENTS_FILE).exists()
    assert (output_dir / THEME_STATE_DAILY_FILE).exists()
    assert json.loads((source_dir / PHASE_A_MANIFEST).read_text(encoding="utf-8"))["schema_version"] == "3"
