from __future__ import annotations

import asyncio
from datetime import datetime
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from dojoagents.cli.main import build_parser as build_main_parser
from dojoagents.dashboard.cli.sector_brief_extract import (
    BriefJob,
    _api_write_items,
    _build_task_command,
    _has_reusable_output,
    _read_brief,
    _run_one,
    _sectors_in_window,
    _validate_args,
    _write_sector_briefs,
    build_parser,
    discover_brief_jobs,
    run_sector_brief_extract,
)


def _brief(*, market: str = "cn", sector_id: str = "1/9/10") -> dict:
    return {
        "market": market,
        "sector_id": sector_id,
        "as_of_date": "2026-07-31",
        "key_drivers": [
            {
                "title": {"zh": "算力需求增长", "en": "Compute demand expands"},
                "importance": "high",
                "price_direction": "up",
            }
        ],
        "key_risks": [],
        "top_components": [
            {
                "ticker": "002916.SZ",
                "role_label": {"zh": "算力龙头", "en": "AI leader"},
                "thesis": {"zh": "受益服务器需求", "en": "Benefits from server demand"},
            }
        ],
    }


def test_top_level_sector_brief_extract_parser() -> None:
    args = build_main_parser().parse_args(
        [
            "sector-brief-extract",
            "--date",
            "2026-07-31",
            "--market",
            "cn",
            "--model",
            "deepseek-v4-flash-0731",
            "--write-only",
        ]
    )
    assert args.command == "sector-brief-extract"
    assert args.market == ["cn"]
    assert args.write_only is True
    assert args.lookback_days == 5
    assert args.max_attempts == 3
    assert args.model == "deepseek-v4-flash-0731"


@pytest.mark.parametrize("argv", [[], ["--date"]])
def test_date_defaults_to_today(argv) -> None:
    args = build_parser().parse_args(argv)
    with patch(
        "dojoagents.dashboard.cli.sector_brief_extract._today_local",
        return_value="2026-08-04",
    ):
        assert _validate_args(args) == "2026-08-04"


def test_sectors_in_window_filters_dates_and_deduplicates() -> None:
    rows = [
        {"sector_id": 10, "sector_ref": "1/9/10", "event_time": "2026-07-31T10:00:00+08:00"},
        {"sector_id": "1/9/10", "event_time": "2026-07-30T10:00:00+08:00"},
        {"sector_id": "1/9/11", "event_time": "2026-07-20T10:00:00+08:00"},
    ]
    assert _sectors_in_window(rows, start_date="2026-07-26", end_date="2026-07-31") == ["1/9/10"]


def test_sectors_in_window_rejects_leaf_id_without_sector_ref() -> None:
    with pytest.raises(ValueError, match="lack a canonical sector_ref"):
        _sectors_in_window(
            [{"sector_id": 10, "event_time": "2026-07-31T10:00:00+08:00"}],
            start_date="2026-07-26",
            end_date="2026-07-31",
        )


@pytest.mark.asyncio
async def test_discover_brief_jobs_uses_attribution_factor_api() -> None:
    get_factors = AsyncMock(
        return_value={
            "data": [
                {"sector_id": 10, "sector_ref": "1/9/10", "event_time": "2026-07-31T10:00:00+08:00"},
                {"sector_id": "1/9/11", "event_time": "2026-07-20T10:00:00+08:00"},
            ]
        }
    )
    client = SimpleNamespace(analysis=SimpleNamespace(get_attribution_factor=get_factors))
    with patch(
        "dojoagents.dashboard.cli.sector_brief_extract.open_markets_on",
        return_value=("cn",),
    ):
        jobs = await discover_brief_jobs(
            client,
            as_of_date="2026-07-31",
            lookback_days=5,
            markets=("cn",),
        )

    assert jobs == [BriefJob("cn", "1/9/10")]
    get_factors.assert_awaited_once_with(market="cn")


def test_task_command_resolves_as_of_output_context() -> None:
    with patch(
        "dojoagents.dashboard.cli.sector_brief_extract._dojoagents_executable",
        return_value="/venv/bin/dojoagents",
    ):
        command = _build_task_command(
            BriefJob("cn", "1/9/10"),
            as_of_date="2026-07-31",
            lookback_days=5,
            local=False,
            model="deepseek-v4-flash-0731",
        )
    assert "sector_id=1/9/10" in command
    assert "sector_path_id=1/9/10" in command
    assert "as_of_date=2026-07-31" in command
    assert "lookback_days=5" in command
    assert command[command.index("--model") + 1] == "deepseek-v4-flash-0731"


def test_task_command_rejects_leaf_sector_id() -> None:
    with pytest.raises(ValueError, match="Invalid sector path"):
        _build_task_command(
            BriefJob("cn", "10"),
            as_of_date="2026-07-31",
            lookback_days=5,
            local=False,
        )


@pytest.mark.asyncio
async def test_run_one_retries_invalid_output_then_succeeds(tmp_path) -> None:
    path = tmp_path / "sector_theme_brief_cn_1_9_10_2026-07-31.json"
    invalid = _brief()
    invalid["key_drivers"][0]["title"]["en"] = "x" * 61

    async def first_communicate():
        path.write_text(json.dumps(invalid, ensure_ascii=False), encoding="utf-8")
        return b"", None

    async def second_communicate():
        path.write_text(json.dumps(_brief(), ensure_ascii=False), encoding="utf-8")
        return b"", None

    processes = [
        SimpleNamespace(returncode=0, communicate=first_communicate),
        SimpleNamespace(returncode=0, communicate=second_communicate),
    ]
    with (
        patch(
            "dojoagents.dashboard.cli.sector_brief_extract._dojoagents_executable",
            return_value="/venv/bin/dojoagents",
        ),
        patch(
            "dojoagents.dashboard.cli.sector_brief_extract.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            side_effect=processes,
        ) as create_process,
    ):
        result = await _run_one(
            BriefJob("cn", "1/9/10"),
            as_of_date="2026-07-31",
            lookback_days=5,
            local=False,
            config=None,
            model="deepseek-v4-flash-0731",
            output_path=path,
            max_attempts=3,
            semaphore=asyncio.Semaphore(1),
            dry_run=False,
        )

    assert result == (BriefJob("cn", "1/9/10"), 0)
    assert create_process.await_count == 2


@pytest.mark.asyncio
async def test_run_one_skips_after_three_process_failures(tmp_path) -> None:
    process = SimpleNamespace(returncode=1, communicate=AsyncMock(return_value=(b"failed", None)))
    with (
        patch(
            "dojoagents.dashboard.cli.sector_brief_extract._dojoagents_executable",
            return_value="/venv/bin/dojoagents",
        ),
        patch(
            "dojoagents.dashboard.cli.sector_brief_extract.asyncio.create_subprocess_exec",
            new_callable=AsyncMock,
            side_effect=[process, process, process],
        ) as create_process,
    ):
        result = await _run_one(
            BriefJob("cn", "1/9/10"),
            as_of_date="2026-07-31",
            lookback_days=5,
            local=False,
            config=None,
            model=None,
            output_path=tmp_path / "missing.json",
            max_attempts=3,
            semaphore=asyncio.Semaphore(1),
            dry_run=False,
        )

    assert result == (BriefJob("cn", "1/9/10"), 1)
    assert create_process.await_count == 3


def test_valid_existing_brief_is_reusable_and_gets_stable_uid(tmp_path) -> None:
    path = tmp_path / "sector_theme_brief_cn_1_9_10_2026-07-31.json"
    path.write_text(json.dumps(_brief(), ensure_ascii=False), encoding="utf-8")
    assert _has_reusable_output(path, "2026-07-31") is True

    first = _api_write_items([_brief()])
    second = _api_write_items([_brief()])
    assert first == second
    assert first[0]["brief_uid"].startswith("dojoagents:")


def test_existing_brief_must_also_pass_sdk_write_validation(tmp_path) -> None:
    path = tmp_path / "sector_theme_brief_cn_1_9_10_2026-07-31.json"
    payload = _brief()
    payload["key_drivers"][0]["title"]["en"] = "x" * 61
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(ValueError, match="maxLength 60"):
        _read_brief(path)
    assert _has_reusable_output(path, "2026-07-31") is False


def test_empty_existing_brief_is_not_reusable(tmp_path) -> None:
    path = tmp_path / "sector_theme_brief_cn_1_9_10_2026-07-31.json"
    payload = _brief()
    payload["key_drivers"] = []
    payload["key_risks"] = []
    payload["top_components"] = []
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    assert _has_reusable_output(path, "2026-07-31") is False


@pytest.mark.asyncio
async def test_write_sector_briefs_splits_batches() -> None:
    create = AsyncMock()
    client = SimpleNamespace(analysis=SimpleNamespace(create_sector_brief_extract=create))
    items = [{"brief_uid": str(index)} for index in range(3)]
    with patch("dojoagents.dashboard.cli.sector_brief_extract._WRITE_BATCH_SIZE", 2):
        written = await _write_sector_briefs(client, items)
    assert written == 3
    batches = [call.kwargs["body"]["items"] for call in create.await_args_list]
    assert [[{key: value for key, value in item.items() if key != "generation_time"} for item in batch] for batch in batches] == [items[:2], items[2:]]
    assert all(datetime.fromisoformat(item["generation_time"]).tzinfo is not None for batch in batches for item in batch)
    assert all(len({item["generation_time"] for item in batch}) == 1 for batch in batches)


@pytest.mark.asyncio
async def test_write_only_validates_and_submits_existing_brief(tmp_path) -> None:
    output_root = tmp_path / "outputs"
    output_dir = output_root / "sector-brief-extract"
    output_dir.mkdir(parents=True)
    path = output_dir / "sector_theme_brief_cn_1_9_10_2026-07-31.json"
    path.write_text(json.dumps(_brief(), ensure_ascii=False), encoding="utf-8")
    args = build_parser().parse_args(["--date", "2026-07-31", "--market", "cn", "--write-only"])
    config = SimpleNamespace(
        tasks=SimpleNamespace(enabled=True, output_root=str(output_root)),
        logging=SimpleNamespace(),
        dojosdk=None,
    )
    client = SimpleNamespace(
        analysis=SimpleNamespace(create_sector_brief_extract=AsyncMock()),
        aclose=AsyncMock(),
    )
    with (
        patch(
            "dojoagents.dashboard.cli.sector_brief_extract.ConfigStore",
            return_value=SimpleNamespace(snapshot=lambda: config),
        ),
        patch("dojoagents.dashboard.cli.sector_brief_extract.configure_logging"),
        patch("dojoagents.dashboard.cli.sector_brief_extract._sdk_client", return_value=client),
    ):
        assert await run_sector_brief_extract(args) == 0

    client.analysis.create_sector_brief_extract.assert_awaited_once()
    item = client.analysis.create_sector_brief_extract.await_args.kwargs["body"]["items"][0]
    assert item["sector_id"] == "1/9/10"
    assert item["brief_uid"].startswith("dojoagents:")
    client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_all_reusable_outputs_do_not_start_task_runtime(tmp_path) -> None:
    output_root = tmp_path / "outputs"
    output_dir = output_root / "sector-brief-extract"
    output_dir.mkdir(parents=True)
    path = output_dir / "sector_theme_brief_cn_1_9_10_2026-07-31.json"
    path.write_text(json.dumps(_brief(), ensure_ascii=False), encoding="utf-8")
    args = build_parser().parse_args(["--date", "2026-07-31", "--market", "cn"])
    config = SimpleNamespace(
        tasks=SimpleNamespace(enabled=True, output_root=str(output_root)),
        logging=SimpleNamespace(),
        dojosdk=None,
    )
    discovery = SimpleNamespace(
        analysis=SimpleNamespace(get_attribution_factor=AsyncMock(return_value={"data": [{"sector_id": 10, "sector_ref": "1/9/10", "event_time": "2026-07-31T10:00:00+08:00"}]})),
        aclose=AsyncMock(),
    )
    writer = SimpleNamespace(
        analysis=SimpleNamespace(create_sector_brief_extract=AsyncMock()),
        aclose=AsyncMock(),
    )
    with (
        patch(
            "dojoagents.dashboard.cli.sector_brief_extract.ConfigStore",
            return_value=SimpleNamespace(snapshot=lambda: config),
        ),
        patch("dojoagents.dashboard.cli.sector_brief_extract.configure_logging"),
        patch(
            "dojoagents.dashboard.cli.sector_brief_extract._sdk_client",
            side_effect=[discovery, writer],
        ),
        patch(
            "dojoagents.dashboard.cli.sector_brief_extract.open_markets_on",
            return_value=("cn",),
        ),
        patch("dojoagents.dashboard.cli.sector_brief_extract._task_runtime") as task_runtime,
    ):
        assert await run_sector_brief_extract(args) == 0

    task_runtime.assert_not_called()
    writer.analysis.create_sector_brief_extract.assert_awaited_once()


@pytest.mark.asyncio
async def test_failed_jobs_are_skipped_without_interrupting_batch(tmp_path) -> None:
    args = build_parser().parse_args(["--date", "2026-07-31", "--market", "cn"])
    config = SimpleNamespace(
        tasks=SimpleNamespace(enabled=True, output_root=str(tmp_path / "outputs")),
        logging=SimpleNamespace(),
        dojosdk=None,
    )
    discovery = SimpleNamespace(
        analysis=SimpleNamespace(
            get_attribution_factor=AsyncMock(
                return_value={
                    "data": [
                        {
                            "sector_id": 10,
                            "sector_ref": "1/9/10",
                            "event_time": "2026-07-31T10:00:00+08:00",
                        }
                    ]
                }
            )
        ),
        aclose=AsyncMock(),
    )

    class TaskRuntime:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, traceback):
            return False

    with (
        patch(
            "dojoagents.dashboard.cli.sector_brief_extract.ConfigStore",
            return_value=SimpleNamespace(snapshot=lambda: config),
        ),
        patch("dojoagents.dashboard.cli.sector_brief_extract.configure_logging"),
        patch("dojoagents.dashboard.cli.sector_brief_extract._sdk_client", return_value=discovery),
        patch(
            "dojoagents.dashboard.cli.sector_brief_extract.open_markets_on",
            return_value=("cn",),
        ),
        patch(
            "dojoagents.dashboard.cli.sector_brief_extract._task_runtime",
            return_value=TaskRuntime(),
        ),
        patch(
            "dojoagents.dashboard.cli.sector_brief_extract._run_one",
            new_callable=AsyncMock,
            return_value=(BriefJob("cn", "1/9/10"), 1),
        ),
    ):
        assert await run_sector_brief_extract(args) == 0
