from __future__ import annotations

from pathlib import Path

from dojoagents.tasks.manager import TaskPromptManager
from dojoagents.tasks.models import PipelineSpec
from dojoagents.harnesses.built_in.financial.pipelines.preflight import (
    evaluate_pipeline_preflight,
)


def test_daily_market_events_pipeline_loads_preflight() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    financial_root = repo_root / "dojoagents" / "harnesses" / "built_in" / "financial"
    manager = TaskPromptManager(
        task_dirs=[financial_root / "tasks" / "definitions"],
        pipeline_dirs=[financial_root / "pipelines" / "definitions"],
    )
    pipeline = manager.get_pipeline("daily-market-events")
    assert pipeline is not None
    assert pipeline.preflight is not None
    assert pipeline.preflight["require_any_trading_market"] == [
        "us",
        "cn",
        "hk",
    ]


def test_preflight_skips_when_all_markets_closed() -> None:
    pipeline = PipelineSpec(
        id="daily-market-events",
        preflight={"require_any_trading_market": ("us", "cn", "hk")},
    )
    result = evaluate_pipeline_preflight(pipeline, trading_date="2026-07-12")
    assert result.action == "skip"
    assert result.open_markets == ()
    assert set(result.closed_markets) == {"us", "cn", "hk"}


def test_preflight_runs_when_any_market_open() -> None:
    pipeline = PipelineSpec(
        id="daily-market-events",
        preflight={"require_any_trading_market": ("us", "cn", "hk")},
    )
    result = evaluate_pipeline_preflight(pipeline, trading_date="2026-07-13")
    assert result.action == "run"
    assert result.open_markets


def test_preflight_force_bypasses_skip() -> None:
    pipeline = PipelineSpec(
        id="daily-market-events",
        preflight={"require_any_trading_market": ("us", "cn", "hk")},
    )
    result = evaluate_pipeline_preflight(pipeline, trading_date="2026-07-12", force=True)
    assert result.action == "run"
    assert "force" in result.reason
