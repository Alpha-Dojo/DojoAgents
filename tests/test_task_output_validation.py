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
