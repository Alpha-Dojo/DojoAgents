from __future__ import annotations

from pathlib import Path

import pytest

from dojoagents.tasks.manager import TaskPromptManager
from dojoagents.tasks.output_validation import (
    is_placeholder_task_output,
    validate_task_output_content,
)


@pytest.fixture
def task_manager() -> TaskPromptManager:
    repo_root = Path(__file__).resolve().parents[1]
    financial = repo_root / "dojoagents" / "harnesses" / "built_in" / "financial"
    built_in = financial / "tasks" / "definitions"
    pipelines = financial / "pipelines" / "definitions"
    return TaskPromptManager(task_dirs=[built_in], pipeline_dirs=[pipelines])


def test_is_placeholder_task_output_detects_copy_note() -> None:
    payload = {
        "note": "This file is also saved at ~/.dojo/tasks/outputs/sector-attribution/foo.json",
        "copy_of_task_output": True,
    }
    assert is_placeholder_task_output(payload, fmt="json") is True


def test_validate_task_output_content_rejects_placeholder(task_manager) -> None:
    issues = validate_task_output_content(
        manager=task_manager,
        task_id="sector-attribution",
        artifact_meta={
            "filename": "market_news_raw_pack_2026-07-02.json",
            "format": "json",
            "schema": "schema/market_news_raw_pack.schema.json",
        },
        content={
            "note": "saved elsewhere",
            "copy_of_task_output": True,
        },
        fmt="json",
    )
    assert issues
    assert "placeholder" in issues[0].lower()


def test_validate_task_output_content_accepts_minimal_valid_pack(task_manager) -> None:
    issues = validate_task_output_content(
        manager=task_manager,
        task_id="sector-attribution",
        artifact_meta={
            "filename": "market_news_raw_pack_2026-07-02.json",
            "format": "json",
            "schema": "schema/market_news_raw_pack.schema.json",
        },
        content={
            "trading_date": "2026-07-02",
            "window_start_date": "2026-07-02",
            "window_end_date": "2026-07-02",
            "sector_moves": [],
            "news_items": [],
            "sectors_without_news": [],
        },
        fmt="json",
    )
    assert issues == []


def test_validate_ticker_sector_labels_enforces_ticker_and_primary(task_manager) -> None:
    artifact_meta = {
        "filename": "ticker_sector_labels.json",
        "format": "json",
        "schema": "schema/ticker_sector_labels.schema.json",
    }
    label = {
        "level_1": "科技",
        "level_2": "半导体与集成电路",
        "level_3": "芯片设计",
        "level1_id": "1",
        "level2_id": "2",
        "level3_id": "3",
        "type": "Primary",
        "reason": "Fabless GPU 设计为主业",
    }
    assert (
        validate_task_output_content(
            manager=task_manager,
            task_id="ticker-sector-classify",
            artifact_meta=artifact_meta,
            content={"ticker": "NVDA", "labels": [label]},
            fmt="json",
        )
        == []
    )
    bad_ticker = validate_task_output_content(
        manager=task_manager,
        task_id="ticker-sector-classify",
        artifact_meta=artifact_meta,
        content={"ticker": "600519", "labels": [label]},
        fmt="json",
    )
    assert any("pattern" in issue for issue in bad_ticker)

    missing_labels = validate_task_output_content(
        manager=task_manager,
        task_id="ticker-sector-classify",
        artifact_meta=artifact_meta,
        content={"ticker": "600519.SS"},
        fmt="json",
    )
    assert any("labels" in issue for issue in missing_labels)

    labels_as_object = validate_task_output_content(
        manager=task_manager,
        task_id="ticker-sector-classify",
        artifact_meta=artifact_meta,
        content={
            "ticker": "NVDA",
            "labels": {
                "yahoo_sector": "Technology",
                "dashboard_level3_zh": "芯片设计",
            },
        },
        fmt="json",
    )
    assert any("expected type array" in issue for issue in labels_as_object)

    extra_top_level = validate_task_output_content(
        manager=task_manager,
        task_id="ticker-sector-classify",
        artifact_meta=artifact_meta,
        content={
            "ticker": "688825.SS",
            "market": "cn",
            "pe": 31.74,
            "sector_classification": {"sector_path_id": "1/2/7"},
            "labels": [label],
        },
        fmt="json",
    )
    assert any("additional properties" in issue for issue in extra_top_level)

    no_primary = validate_task_output_content(
        manager=task_manager,
        task_id="ticker-sector-classify",
        artifact_meta=artifact_meta,
        content={
            "ticker": "NVDA",
            "labels": [{**label, "type": "Secondary"}],
        },
        fmt="json",
    )
    assert any("at least 1 matching" in issue for issue in no_primary)


def test_generic_write_contract_from_schema(task_manager) -> None:
    from dojoagents.tasks.write_contract import compact_schema_hint, format_write_contract_block, load_json_schema

    spec = task_manager.get_task("ticker-sector-classify")
    assert spec is not None
    schema_path = task_manager.resolve_schema_path(spec, "schema/ticker_sector_labels.schema.json")
    assert schema_path is not None
    schema = load_json_schema(schema_path)
    assert schema is not None
    block = "\n".join(
        format_write_contract_block(
            filename="ticker_sector_labels.json",
            fmt="json",
            schema=schema,
        )
    )
    assert "write_session_file" in block
    assert "ticker_sector_labels.json" in block
    assert '"ticker"' in block
    assert '"labels"' in block
    assert "Primary" in block
    assert "additionalProperties=false" in block
    hint = compact_schema_hint(schema)
    assert "ticker" in hint and "labels" in hint
