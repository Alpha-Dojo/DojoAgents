from __future__ import annotations

from datetime import datetime
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from dojoagents.cli.main import build_parser as build_main_parser
from dojoagents.dashboard.cli.attribution_factor_crawl import (
    SectorJob,
    _api_write_items,
    _build_task_command,
    _has_reusable_output,
    _partition_jobs,
    _read_jsonl,
    _resolve_markets,
    _top_jobs_for_market,
    _validate_output_context,
    _validate_args,
    _write_attribution_factors,
    build_parser,
    managed_dashboard_runtime,
    run_attribution_factor_crawl,
)


def _factor(*, mechanism: str = "New mechanism") -> dict:
    return {
        "claim": {"zh": "需求改善", "en": "Demand improved"},
        "sector_id": "1/2/6",
        "market": "cn",
        "factor_topic": "demand_supply",
        "role": "explains_move",
        "price_direction": "up",
        "importance": "high",
        "mechanism": {"zh": mechanism, "en": ""},
        "evidence": [{"quote": "Demand rose", "url": "https://example.com"}],
        "affected_tickers": ["000001.SZ"],
        "event_time": "2026-07-31T10:00:00+08:00",
        "attrs": {"source": "daily-crawl"},
    }


def test_top_level_attribution_factor_crawl_parser() -> None:
    args = build_main_parser().parse_args(["attribution-factor-crawl", "--date", "2026-07-31", "--write-only", "--skip-write"])
    assert args.command == "attribution-factor-crawl"
    assert args.date == "2026-07-31"
    assert args.write_only is True
    assert args.skip_write is True
    assert args.dashboard_startup_timeout == 300.0
    assert args.market is None


def test_market_filter_is_repeatable_and_deduplicated() -> None:
    args = build_parser().parse_args(["--market", "cn", "--market", "us", "--market", "cn"])
    assert _resolve_markets(args.market) == ("cn", "us")


def test_force_rerun_parser_and_write_only_conflict() -> None:
    args = build_parser().parse_args(["--force-rerun"])
    assert args.force_rerun is True

    conflicting = build_parser().parse_args(["--force-rerun", "--write-only"])
    with pytest.raises(ValueError, match="cannot be used together"):
        _validate_args(conflicting)


def test_legacy_publish_flags_remain_aliases() -> None:
    args = build_parser().parse_args(["--merge-only", "--skip-upload"])
    assert args.write_only is True
    assert args.skip_write is True


def test_dashboard_parser_accepts_config_path() -> None:
    args = build_main_parser().parse_args(["dashboard", "--config", "custom-agents.yaml", "--lightweight-runtime"])
    assert args.config == "custom-agents.yaml"
    assert args.lightweight_runtime is True


@pytest.mark.parametrize("argv", [[], ["--date"]])
def test_date_defaults_to_local_today_when_omitted_or_value_is_missing(argv) -> None:
    args = build_parser().parse_args(argv)
    with patch(
        "dojoagents.dashboard.cli.attribution_factor_crawl._today_local",
        return_value="2026-08-03",
    ):
        assert _validate_args(args) == "2026-08-03"


def test_top_jobs_require_taxonomy_path_and_rank_absolute_change() -> None:
    payload = {
        "gainers": [
            {
                "name": {"zh": "芯片"},
                "level1_id": "1",
                "level2_id": "2",
                "level3_id": "6",
                "change_percent": 3,
            },
            {"name": {"zh": "无路径"}, "change_percent": 99},
        ],
        "losers": [
            {
                "name": {"en": "Software"},
                "level1_id": "1",
                "level2_id": "3",
                "level3_id": "7",
                "change_percent": -5,
            }
        ],
    }
    jobs = _top_jobs_for_market("cn", payload, top_n=2)
    assert [(job.name, job.sector_path_id) for job in jobs] == [
        ("Software", "1/3/7"),
        ("芯片", "1/2/6"),
    ]


def test_task_command_passes_resolved_discovery_context() -> None:
    job = SectorJob("us", "Application Software", "1/3/7", -5.2)
    with patch(
        "dojoagents.dashboard.cli.attribution_factor_crawl._dojoagents_executable",
        return_value="/venv/bin/dojoagents",
    ):
        command = _build_task_command(
            job,
            trading_date="2026-07-31",
            local=False,
        )

    assert "market=us" in command
    assert "sector_id=1/3/7" in command
    assert "sector_path_id=1/3/7" in command
    assert "sector_name=Application Software" in command
    assert "change_percent=-5.2" in command


def test_legacy_daily_script_passes_same_discovery_context() -> None:
    from run_daily_attribution_factor_crawl import (
        SectorJob as LegacySectorJob,
        _build_task_command as build_legacy_command,
    )

    command = build_legacy_command(
        LegacySectorJob("us", "Application Software", "1/3/7", -5.2),
        trading_date="2026-07-31",
        local=False,
    )

    assert "market=us" in command
    assert "sector_id=1/3/7" in command
    assert "sector_path_id=1/3/7" in command
    assert "sector_name=Application Software" in command
    assert "change_percent=-5.2" in command


@pytest.mark.asyncio
async def test_fetch_movers_surfaces_dashboard_error_detail() -> None:
    from dojoagents.dashboard.cli.attribution_factor_crawl import _fetch_movers_for_market

    request = httpx.Request("GET", "http://127.0.0.1:8765/api/v1/market/sector-movers")
    response = httpx.Response(
        400,
        request=request,
        json={"detail": "No trading data available between 2026-08-03 and 2026-08-03."},
    )
    client = AsyncMock()
    client.get.return_value = response

    with pytest.raises(RuntimeError, match="No trading data available between 2026-08-03"):
        await _fetch_movers_for_market(
            client,
            base_url="http://127.0.0.1:8765",
            market="us",
            trading_date="2026-08-03",
            top_n=1,
            min_cap=0,
        )


def test_jsonl_arrays_are_flattened_and_validated(tmp_path) -> None:
    output = tmp_path / "factors.jsonl"
    second = _factor(mechanism="Second")
    second["event_time"] = "2026-07-31T11:00:00+08:00"
    output.write_text(json.dumps([_factor(), second]), encoding="utf-8")
    items = _api_write_items(_read_jsonl([output]))
    assert len(items) == 2
    assert items[0]["claim"]["zh"] == "需求改善"
    assert items[0]["payload_status"] == "ready"
    assert items[0]["factor_uid"].startswith("dojoagents:")


def test_api_items_are_idempotent_and_preserve_explicit_factor_uid() -> None:
    first = _factor(mechanism="First")
    updated = _factor(mechanism="Updated")
    explicit = _factor(mechanism="Explicit")
    explicit["factor_uid"] = "upstream-factor-1"

    first_uid = _api_write_items([first])[0]["factor_uid"]
    items = _api_write_items([first, updated, explicit])

    assert len(items) == 2
    assert items[0]["factor_uid"] == first_uid
    assert items[0]["mechanism"]["zh"] == "Updated"
    assert items[1]["factor_uid"] == "upstream-factor-1"


def test_new_factor_rejects_date_only_event_time() -> None:
    factor = _factor()
    factor["event_time"] = "2026-07-31"
    with pytest.raises(ValueError, match="event_time"):
        _api_write_items([factor])


def test_output_filename_context_must_match_rows(tmp_path) -> None:
    path = tmp_path / "attribution_factors_us_1_2_6_2026-07-31.jsonl"
    with pytest.raises(ValueError, match="context mismatch"):
        _validate_output_context(path, [_factor()], "2026-07-31")


def test_reusable_output_requires_valid_nonempty_current_data(tmp_path) -> None:
    valid = tmp_path / "attribution_factors_cn_1_2_6_2026-07-31.jsonl"
    valid.write_text(json.dumps(_factor()) + "\n", encoding="utf-8")
    assert _has_reusable_output(valid, "2026-07-31") is True

    empty = tmp_path / "attribution_factors_cn_1_2_7_2026-07-31.jsonl"
    empty.touch()
    assert _has_reusable_output(empty, "2026-07-31") is False

    invalid = tmp_path / "attribution_factors_cn_1_2_8_2026-07-31.jsonl"
    invalid.write_text("not-json\n", encoding="utf-8")
    assert _has_reusable_output(invalid, "2026-07-31") is False


def test_partition_jobs_skips_existing_unless_force_rerun(tmp_path) -> None:
    existing = SectorJob("cn", "芯片", "1/2/6", 3.0)
    missing = SectorJob("cn", "软件", "1/2/7", -2.0)
    existing_path = tmp_path / existing.output_filename("2026-07-31")
    existing_path.write_text(json.dumps(_factor()) + "\n", encoding="utf-8")

    reused, pending = _partition_jobs(
        [existing, missing],
        output_dir=tmp_path,
        trading_date="2026-07-31",
        force_rerun=False,
    )
    assert reused == [existing]
    assert pending == [missing]

    reused, pending = _partition_jobs(
        [existing, missing],
        output_dir=tmp_path,
        trading_date="2026-07-31",
        force_rerun=True,
    )
    assert reused == []
    assert pending == [existing, missing]


@pytest.mark.asyncio
async def test_managed_dashboard_reuses_existing_instance() -> None:
    with (
        patch(
            "dojoagents.dashboard.cli.attribution_factor_crawl.check_dashboard_health",
            new=AsyncMock(return_value=True),
        ),
        patch("dojoagents.dashboard.cli.attribution_factor_crawl.asyncio.create_subprocess_exec") as spawn,
    ):
        async with managed_dashboard_runtime(
            base_url="http://127.0.0.1:8765",
            config_path="agents.yaml",
            startup_timeout=1,
        ):
            pass
    spawn.assert_not_called()


@pytest.mark.asyncio
async def test_managed_dashboard_starts_waits_and_stops_owned_process() -> None:
    class FakeProcess:
        returncode = None
        pid = 1234
        terminated = False
        killed = False

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True

        async def wait(self) -> int:
            return 0

    process = FakeProcess()
    health = AsyncMock(side_effect=[False, True])
    spawn = AsyncMock(return_value=process)
    with (
        patch(
            "dojoagents.dashboard.cli.attribution_factor_crawl.check_dashboard_health",
            new=health,
        ),
        patch(
            "dojoagents.dashboard.cli.attribution_factor_crawl.asyncio.create_subprocess_exec",
            new=spawn,
        ),
        patch(
            "dojoagents.dashboard.cli.attribution_factor_crawl._dojoagents_executable",
            return_value="/venv/bin/dojoagents",
        ),
    ):
        async with managed_dashboard_runtime(
            base_url="http://127.0.0.1:8765",
            config_path="custom.yaml",
            startup_timeout=1,
        ):
            assert process.terminated is False

    spawn.assert_awaited_once_with(
        "/venv/bin/dojoagents",
        "dashboard",
        "--host",
        "127.0.0.1",
        "--port",
        "8765",
        "--config",
        "custom.yaml",
        "--lightweight-runtime",
    )
    assert process.terminated is True
    assert process.killed is False


@pytest.mark.asyncio
async def test_managed_dashboard_does_not_start_unreachable_remote_url() -> None:
    with patch(
        "dojoagents.dashboard.cli.attribution_factor_crawl.check_dashboard_health",
        new=AsyncMock(return_value=False),
    ):
        with pytest.raises(RuntimeError, match="only supports local"):
            async with managed_dashboard_runtime(
                base_url="https://dashboard.example.com",
                config_path="agents.yaml",
                startup_timeout=1,
            ):
                pass


@pytest.mark.asyncio
async def test_write_only_batches_existing_outputs_through_create_api(tmp_path) -> None:
    output_root = tmp_path / "outputs"
    task_dir = output_root / "attribution-factor-crawl"
    task_dir.mkdir(parents=True)
    factor_file = task_dir / "attribution_factors_cn_1_2_6_2026-07-31.jsonl"
    factor_file.write_text(json.dumps(_factor()) + "\n", encoding="utf-8")
    us_factor = _factor()
    us_factor.update({"market": "us", "sector_id": "1/3/7"})
    (task_dir / "attribution_factors_us_1_3_7_2026-07-31.jsonl").write_text(
        json.dumps(us_factor) + "\n",
        encoding="utf-8",
    )

    args = build_parser().parse_args(
        [
            "--date",
            "2026-07-31",
            "--write-only",
            "--market",
            "cn",
        ]
    )
    config = SimpleNamespace(
        tasks=SimpleNamespace(enabled=True, output_root=str(output_root)),
        logging=SimpleNamespace(),
        dojosdk=None,
    )
    store = SimpleNamespace(snapshot=lambda: config)
    create = AsyncMock(return_value=SimpleNamespace(data=[]))
    client = SimpleNamespace(
        analysis=SimpleNamespace(create_attribution_factor=create),
        aclose=AsyncMock(),
    )

    with (
        patch("dojoagents.dashboard.cli.attribution_factor_crawl.ConfigStore", return_value=store),
        patch("dojoagents.dashboard.cli.attribution_factor_crawl.configure_logging"),
        patch("dojoagents.dashboard.cli.attribution_factor_crawl._sdk_client", return_value=client),
    ):
        result = await run_attribution_factor_crawl(args)

    assert result == 0
    create.assert_awaited_once()
    body = create.await_args.kwargs["body"]
    assert len(body["items"]) == 1
    assert body["items"][0]["claim"] == {"zh": "需求改善", "en": "Demand improved"}
    assert body["items"][0]["payload_status"] == "ready"
    client.aclose.assert_awaited_once()


@pytest.mark.asyncio
async def test_write_attribution_factors_splits_at_api_limit() -> None:
    create = AsyncMock()
    client = SimpleNamespace(analysis=SimpleNamespace(create_attribution_factor=create))
    items = [{"sector_id": str(index)} for index in range(3)]

    with patch(
        "dojoagents.dashboard.cli.attribution_factor_crawl._WRITE_BATCH_SIZE",
        2,
    ):
        written = await _write_attribution_factors(client, items)

    assert written == 3
    bodies = [call.kwargs["body"] for call in create.await_args_list]
    assert [body["items"] for body in bodies] == [items[:2], items[2:]]
    assert all(datetime.fromisoformat(body["generation_time"]).tzinfo is not None for body in bodies)
    assert all("generation_time" not in item for body in bodies for item in body["items"])


@pytest.mark.asyncio
async def test_skip_write_validates_without_creating_client(tmp_path) -> None:
    output_root = tmp_path / "outputs"
    task_dir = output_root / "attribution-factor-crawl"
    task_dir.mkdir(parents=True)
    factor_file = task_dir / "attribution_factors_cn_1_2_6_2026-07-31.jsonl"
    factor_file.write_text(json.dumps(_factor()) + "\n", encoding="utf-8")
    args = build_parser().parse_args(["--date", "2026-07-31", "--write-only", "--skip-write"])
    config = SimpleNamespace(
        tasks=SimpleNamespace(enabled=True, output_root=str(output_root)),
        logging=SimpleNamespace(),
        dojosdk=None,
    )
    store = SimpleNamespace(snapshot=lambda: config)

    with (
        patch("dojoagents.dashboard.cli.attribution_factor_crawl.ConfigStore", return_value=store),
        patch("dojoagents.dashboard.cli.attribution_factor_crawl.configure_logging"),
        patch("dojoagents.dashboard.cli.attribution_factor_crawl._sdk_client") as client_factory,
    ):
        result = await run_attribution_factor_crawl(args)

    assert result == 0
    client_factory.assert_not_called()
