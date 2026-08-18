"""Extract sector briefs from attribution factors and write them through DojoSDK."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

from dojo import AsyncDojo
from dojo.types.models import SectorBriefExtractWriteRequest

from dojoagents.config.loader import ConfigStore
from dojoagents.dashboard.cli.attribution_factor_crawl import (
    _close_client,
    _dojoagents_executable,
    _sdk_client,
    managed_dashboard_runtime,
)
from dojoagents.dashboard.client.tasks import dashboard_base_url_from_config
from dojoagents.dashboard.services.attribution_factor_service import (
    _calendar_day,
    _unwrap_payload,
    canonical_attribution_sector_ref,
)
from dojoagents.harnesses.built_in.financial.pipelines.trading_calendar import open_markets_on
from dojoagents.logging import LOGGER, configure_logging
from dojoagents.tasks.schema_validator import validate_json_payload

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MARKETS = ("us", "cn", "hk")
_DEFAULT_LOOKBACK_DAYS = 5
_DEFAULT_MAX_ATTEMPTS = 3
_DASHBOARD_STARTUP_TIMEOUT = 300.0
_WRITE_BATCH_SIZE = 10_000
_AF_OFFLINE_PATH = "/api/qdata/v1/analysis/attribution_factor"
_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "harnesses/built_in/financial/tasks/definitions/sector-brief-extract/schema/sector_theme_brief.schema.json"


@dataclass(frozen=True)
class BriefJob:
    market: str
    sector_id: str

    def output_filename(self, as_of_date: str) -> str:
        return f"sector_theme_brief_{self.market}_{self.sector_id.replace('/', '_')}_{as_of_date}.json"


def configure_parser(subparsers: Any) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "sector-brief-extract",
        help="Extract sector briefs from attribution factors and batch-write them through DojoSDK",
    )
    _add_arguments(parser)
    return parser


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    _add_arguments(parser)
    return parser


def _add_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--date",
        nargs="?",
        default="",
        const="",
        help="Brief as-of date YYYY-MM-DD; defaults to today when omitted or bare",
    )
    parser.add_argument(
        "--market",
        action="append",
        choices=list(_MARKETS),
        help="Market to process (us/cn/hk); repeatable, defaults to all markets",
    )
    parser.add_argument(
        "--lookback-days",
        type=int,
        default=_DEFAULT_LOOKBACK_DAYS,
        help=f"Attribution-factor calendar-day lookback (default: {_DEFAULT_LOOKBACK_DAYS})",
    )
    parser.add_argument("--concurrency", type=int, default=5, help="Maximum parallel brief tasks")
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=_DEFAULT_MAX_ATTEMPTS,
        help=f"Maximum attempts per sector job (default: {_DEFAULT_MAX_ATTEMPTS})",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Model override for each Task run; uses the configured provider",
    )
    parser.add_argument("--config", default="~/.dojo/agents.yaml", help="Path to agents.yaml")
    parser.add_argument("--dashboard-url", default="", help="Override Dashboard base URL")
    parser.add_argument(
        "--dashboard-startup-timeout",
        type=float,
        default=_DASHBOARD_STARTUP_TIMEOUT,
        help="Seconds to wait for an automatically started Dashboard",
    )
    parser.add_argument("--local", action="store_true", help="Run each Task in its local runtime")
    parser.add_argument("--preload", action="store_true", help="Preload offline attribution-factor data")
    parser.add_argument("--dry-run", action="store_true", help="Discover sectors and print commands only")
    parser.add_argument(
        "--force-rerun",
        action="store_true",
        help="Rerun tasks even when valid output files already exist",
    )
    parser.add_argument(
        "--write-only",
        action="store_true",
        help="Skip discovery/tasks and write existing outputs for the selected date",
    )
    parser.add_argument(
        "--skip-write",
        action="store_true",
        help="Validate generated briefs without writing them to the API",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Deprecated compatibility flag; successful jobs are always written",
    )


def _today_local() -> str:
    return datetime.now().astimezone().date().isoformat()


def _validate_args(args: argparse.Namespace) -> str:
    as_of_date = str(args.date or "").strip() or _today_local()
    if not _DATE_RE.fullmatch(as_of_date):
        raise ValueError(f"Invalid --date (expected YYYY-MM-DD): {args.date!r}")
    try:
        date.fromisoformat(as_of_date)
    except ValueError as exc:
        raise ValueError(f"Invalid --date (expected a real calendar date): {args.date!r}") from exc
    if int(args.lookback_days) < 0:
        raise ValueError("--lookback-days cannot be negative")
    if int(args.concurrency) < 1:
        raise ValueError("--concurrency must be at least 1")
    if int(args.max_attempts) < 1:
        raise ValueError("--max-attempts must be at least 1")
    if float(args.dashboard_startup_timeout) <= 0:
        raise ValueError("--dashboard-startup-timeout must be greater than 0")
    if args.dry_run and args.write_only:
        raise ValueError("--dry-run and --write-only cannot be used together")
    if args.force_rerun and args.write_only:
        raise ValueError("--force-rerun and --write-only cannot be used together")
    return as_of_date


def _resolve_markets(raw: list[str] | None) -> tuple[str, ...]:
    if not raw:
        return _MARKETS
    return tuple(dict.fromkeys(str(item).strip().lower() for item in raw))


def _window_start(as_of_date: str, lookback_days: int) -> str:
    return (date.fromisoformat(as_of_date) - timedelta(days=lookback_days)).isoformat()


def _sectors_in_window(rows: Iterable[Any], *, start_date: str, end_date: str) -> list[str]:
    sectors: set[str] = set()
    invalid_sector_ids: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        day = _calendar_day(row.get("event_time"))
        if day is None or day < start_date or day > end_date:
            continue
        sector_ref = canonical_attribution_sector_ref(row)
        if sector_ref:
            sectors.add(sector_ref)
            continue
        invalid_sector_ids.add(str(row.get("sector_id") or "<missing>").strip())
    if invalid_sector_ids:
        preview = ", ".join(sorted(invalid_sector_ids)[:8])
        raise ValueError("AttributionFactor rows lack a canonical sector_ref " f"(expected level1_id/level2_id/level3_id): {preview}")
    return sorted(sectors)


async def _ensure_af_preloaded(client: AsyncDojo, *, preload: bool) -> None:
    if not preload:
        return
    fn = getattr(client, "preload_offline_data", None)
    if not callable(fn):
        return
    LOGGER.info("Preloading offline attribution-factor data")
    result = fn(paths=[_AF_OFFLINE_PATH])
    if asyncio.iscoroutine(result):
        await result


async def discover_brief_jobs(
    client: AsyncDojo,
    *,
    as_of_date: str,
    lookback_days: int,
    markets: tuple[str, ...] = _MARKETS,
) -> list[BriefJob]:
    open_markets = set(open_markets_on(as_of_date, markets))
    LOGGER.info(
        "Trading-day filter for %s: open=%s closed=%s",
        as_of_date,
        ",".join(market for market in markets if market in open_markets) or "(none)",
        ",".join(market for market in markets if market not in open_markets) or "(none)",
    )
    start_date = _window_start(as_of_date, lookback_days)
    jobs: list[BriefJob] = []
    for market in markets:
        if market not in open_markets:
            continue
        payload = await client.analysis.get_attribution_factor(market=market)
        rows = [row for row in _unwrap_payload(payload) if isinstance(row, dict)]
        sectors = _sectors_in_window(rows, start_date=start_date, end_date=as_of_date)
        LOGGER.info("market=%s sectors_with_attribution_factors=%d", market, len(sectors))
        jobs.extend(BriefJob(market, sector_id) for sector_id in sectors)
    return jobs


def _build_task_command(
    job: BriefJob,
    *,
    as_of_date: str,
    lookback_days: int,
    local: bool,
    config: str | None = None,
    model: str | None = None,
) -> list[str]:
    if canonical_attribution_sector_ref({"sector_ref": job.sector_id}) != job.sector_id:
        raise ValueError(f"Invalid sector path {job.sector_id!r}; expected level1_id/level2_id/level3_id")
    command = [
        _dojoagents_executable(),
        "tasks",
        "run",
        "--task",
        "sector-brief-extract",
        "--date",
        as_of_date,
    ]
    if config:
        command.extend(["--config", config])
    if model:
        command.extend(["--model", model])
    if local:
        command.append("--local")
    command.extend(
        [
            f"market={job.market}",
            f"sector_id={job.sector_id}",
            f"sector_path_id={job.sector_id}",
            f"as_of_date={as_of_date}",
            f"lookback_days={lookback_days}",
        ]
    )
    return command


async def _run_one(
    job: BriefJob,
    *,
    as_of_date: str,
    lookback_days: int,
    local: bool,
    config: str | None,
    model: str | None,
    output_path: Path,
    max_attempts: int,
    semaphore: asyncio.Semaphore,
    dry_run: bool,
) -> tuple[BriefJob, int]:
    command = _build_task_command(
        job,
        as_of_date=as_of_date,
        lookback_days=lookback_days,
        local=local,
        config=config,
        model=model,
    )
    async with semaphore:
        if dry_run:
            LOGGER.info("DRY RUN %s %s | %s", job.market, job.sector_id, " ".join(command))
            return job, 0
        for attempt in range(1, max_attempts + 1):
            LOGGER.info(
                "START %s %s attempt=%d/%d | %s",
                job.market,
                job.sector_id,
                attempt,
                max_attempts,
                " ".join(command),
            )
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            stdout, _ = await process.communicate()
            process_code = int(process.returncode or 0)
            code = process_code
            error = ""
            if code:
                error = (stdout or b"").decode("utf-8", errors="replace")[-2000:]
            else:
                try:
                    payload = _read_brief(output_path)
                    _validate_output_context(output_path, payload, as_of_date)
                    _api_write_items([payload])
                except ValueError as exc:
                    code = 1
                    error = f"output validation failed: {exc}"
            if code == 0:
                LOGGER.info(
                    "OK %s %s attempt=%d/%d",
                    job.market,
                    job.sector_id,
                    attempt,
                    max_attempts,
                )
                return job, 0
            LOGGER.error(
                "FAIL %s %s attempt=%d/%d exit=%s | %s",
                job.market,
                job.sector_id,
                attempt,
                max_attempts,
                process_code,
                error,
            )
            if attempt < max_attempts:
                LOGGER.warning("RETRY %s %s after failed attempt", job.market, job.sector_id)
        LOGGER.error(
            "SKIP %s %s after %d failed attempts; continuing remaining jobs",
            job.market,
            job.sector_id,
            max_attempts,
        )
        return job, 1


def _read_brief(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Brief output must be a JSON object: {path}")
    issues = validate_json_payload(payload, _SCHEMA_PATH)
    if issues:
        raise ValueError(f"Invalid brief output {path.name}: {'; '.join(issues[:8])}")
    if not any(payload.get(key) for key in ("key_drivers", "key_risks", "top_components")):
        raise ValueError(f"Invalid brief output {path.name}: all brief sections are empty")
    return payload


def _validate_output_context(path: Path, payload: dict[str, Any], as_of_date: str) -> None:
    match = re.fullmatch(
        rf"sector_theme_brief_(us|cn|hk)_(.+)_{re.escape(as_of_date)}\.json",
        path.name,
    )
    if not match:
        raise ValueError(f"Unexpected sector brief output filename: {path.name}")
    expected_market, expected_sector = match.groups()
    actual_sector = str(payload.get("sector_id") or "").replace("/", "_")
    if payload.get("market") != expected_market or actual_sector != expected_sector or payload.get("as_of_date") != as_of_date:
        raise ValueError(f"{path.name} context does not match its market/sector/as_of_date")


def _has_reusable_output(path: Path, as_of_date: str) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        payload = _read_brief(path)
        _validate_output_context(path, payload, as_of_date)
        _api_write_items([payload])
        return True
    except ValueError as exc:
        LOGGER.warning("Existing brief is invalid and will be rerun: %s (%s)", path, exc)
        return False


def _brief_uid(payload: dict[str, Any]) -> str:
    identity = "\x1f".join(str(payload.get(key) or "").strip().casefold() for key in ("market", "sector_id", "as_of_date"))
    return f"dojoagents:{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"


def _api_write_items(payloads: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    items_by_uid: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        item = dict(payload)
        brief_uid = str(item.get("brief_uid") or "").strip() or _brief_uid(item)
        item["brief_uid"] = brief_uid
        validated = SectorBriefExtractWriteRequest(items=[item]).items[0]
        items_by_uid[brief_uid] = validated.model_dump(mode="json", exclude_none=True)
    return list(items_by_uid.values())


async def _write_sector_briefs(client: AsyncDojo, items: list[dict[str, Any]], *, generation_time: str) -> int:
    written = 0
    for offset in range(0, len(items), _WRITE_BATCH_SIZE):
        batch = items[offset : offset + _WRITE_BATCH_SIZE]
        await client.analysis.create_sector_brief_extract(body={"items": batch, "generation_time": generation_time})
        written += len(batch)
        LOGGER.info("Wrote sector-brief batch: %d/%d", written, len(items))
    return written


@asynccontextmanager
async def _task_runtime(
    *,
    local: bool,
    base_url: str,
    config_path: str,
    startup_timeout: float,
):
    if local:
        yield
        return
    async with managed_dashboard_runtime(
        base_url=base_url,
        config_path=config_path,
        startup_timeout=startup_timeout,
    ):
        yield


async def run_sector_brief_extract(args: argparse.Namespace) -> int:
    as_of_date = _validate_args(args)
    generation_time = datetime.now(timezone.utc).isoformat()
    store = ConfigStore(args.config)
    config = store.snapshot()
    configure_logging(config.logging)
    if not config.tasks.enabled:
        raise ValueError("tasks.enabled is false in config")

    markets = _resolve_markets(args.market)
    output_dir = Path(config.tasks.output_root).expanduser() / "sector-brief-extract"
    failed: list[BriefJob] = []
    output_paths: list[Path]

    if args.write_only:
        output_paths = sorted(path for market in markets for path in output_dir.glob(f"sector_theme_brief_{market}_*_{as_of_date}.json"))
    else:
        discovery_client = _sdk_client(config)
        try:
            await _ensure_af_preloaded(discovery_client, preload=bool(args.preload))
            jobs = await discover_brief_jobs(
                discovery_client,
                as_of_date=as_of_date,
                lookback_days=int(args.lookback_days),
                markets=markets,
            )
        finally:
            await _close_client(discovery_client)

        if not jobs:
            if not open_markets_on(as_of_date, markets):
                LOGGER.info("No open markets on %s for %s; nothing to run", as_of_date, ",".join(markets))
            else:
                LOGGER.info("No sectors with attribution factors in the selected window")
            return 0

        reused: list[BriefJob] = []
        pending: list[BriefJob] = []
        for job in jobs:
            path = output_dir / job.output_filename(as_of_date)
            if not args.force_rerun and _has_reusable_output(path, as_of_date):
                reused.append(job)
                LOGGER.info("SKIP existing brief %s %s | %s", job.market, job.sector_id, path)
            else:
                pending.append(job)

        base_url = dashboard_base_url_from_config(args.config, override=args.dashboard_url or None)
        config_override = None if args.config == "~/.dojo/agents.yaml" else str(args.config)
        results: list[tuple[BriefJob, int]] = []
        if pending:
            async with _task_runtime(
                local=bool(args.local),
                base_url=base_url,
                config_path=str(args.config),
                startup_timeout=float(args.dashboard_startup_timeout),
            ):
                semaphore = asyncio.Semaphore(int(args.concurrency))
                results = await asyncio.gather(
                    *(
                        _run_one(
                            job,
                            as_of_date=as_of_date,
                            lookback_days=int(args.lookback_days),
                            local=bool(args.local),
                            config=config_override,
                            model=str(args.model or "").strip() or None,
                            output_path=output_dir / job.output_filename(as_of_date),
                            max_attempts=int(args.max_attempts),
                            semaphore=semaphore,
                            dry_run=bool(args.dry_run),
                        )
                        for job in pending
                    )
                )
        if args.dry_run:
            LOGGER.info("Dry run complete: run=%d skipped=%d", len(results), len(reused))
            return 0
        failed = [job for job, code in results if code]
        if failed:
            LOGGER.error(
                "Skipped %d failed sector brief job(s); successful jobs will continue",
                len(failed),
            )
        successful = [job for job, code in results if not code]
        output_paths = [output_dir / job.output_filename(as_of_date) for job in [*reused, *successful]]

    if not output_paths:
        LOGGER.error("No successful sector brief outputs found for %s; nothing to write", as_of_date)
        return 0
    payloads: list[dict[str, Any]] = []
    for path in output_paths:
        try:
            payload = _read_brief(path)
            _validate_output_context(path, payload, as_of_date)
            _api_write_items([payload])
            payloads.append(payload)
        except ValueError as exc:
            LOGGER.error("SKIP invalid sector brief output %s: %s", path, exc)
    if not payloads:
        LOGGER.error("No valid sector brief outputs found for %s; nothing to write", as_of_date)
        return 0
    items = _api_write_items(payloads)
    if args.skip_write:
        LOGGER.info("Validated %d sector briefs without API write", len(items))
        return 0

    client = _sdk_client(config)
    try:
        written = await _write_sector_briefs(client, items, generation_time=generation_time)
        LOGGER.info("Successfully wrote %d sector briefs through DojoSDK", written)
        return 0
    finally:
        await _close_client(client)


def main(argv: list[str] | None = None) -> int:
    try:
        return asyncio.run(run_sector_brief_extract(build_parser().parse_args(argv)))
    except KeyboardInterrupt:
        LOGGER.error("Interrupted")
        return 130
    except Exception as exc:
        LOGGER.exception("sector-brief-extract failed: %s", exc)
        return 1


__all__ = [
    "BriefJob",
    "build_parser",
    "configure_parser",
    "discover_brief_jobs",
    "main",
    "run_sector_brief_extract",
]
