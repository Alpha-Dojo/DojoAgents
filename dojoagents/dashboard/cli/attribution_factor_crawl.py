"""Crawl daily sector attribution factors and write them through the Dojo API."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import shutil
import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlencode, urlparse

import httpx
from pydantic import ValidationError

from dojo import AsyncDojo
from dojoagents.attribution.base import AttributionFactor
from dojoagents.config.loader import ConfigStore
from dojoagents.dashboard.client.tasks import check_dashboard_health, dashboard_base_url_from_config
from dojoagents.harnesses.built_in.financial.pipelines.trading_calendar import open_markets_on
from dojoagents.logging import LOGGER, configure_logging

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_MARKETS = ("us", "cn", "hk")
_TREEMAP_TOP_N = 10
_DEFAULT_MIN_CAP = 200 * 1e8
_DASHBOARD_STARTUP_TIMEOUT = 300.0
_WRITE_BATCH_SIZE = 10_000


@dataclass(frozen=True)
class SectorJob:
    market: str
    name: str
    sector_path_id: str
    change_percent: float

    def output_filename(self, trading_date: str) -> str:
        safe_sector_id = self.sector_path_id.replace("/", "_")
        return f"attribution_factors_{self.market}_{safe_sector_id}_{trading_date}.jsonl"


def configure_parser(subparsers: Any) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(
        "attribution-factor-crawl",
        help="Crawl and write daily attribution factors through the Dojo API",
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
        help="Trading date YYYY-MM-DD; defaults to today when omitted or used without a value",
    )
    parser.add_argument("--concurrency", type=int, default=3, help="Maximum parallel crawl tasks")
    parser.add_argument(
        "--market",
        action="append",
        choices=list(_MARKETS),
        help="Market to crawl (us/cn/hk); repeatable, defaults to all markets",
    )
    parser.add_argument("--top-n", type=int, default=_TREEMAP_TOP_N, help="Top sectors per open market")
    parser.add_argument(
        "--min-cap",
        type=float,
        default=_DEFAULT_MIN_CAP,
        help="Sector total-cap floor in absolute currency units",
    )
    parser.add_argument("--config", default="~/.dojo/agents.yaml", help="Path to agents.yaml")
    parser.add_argument("--dashboard-url", default="", help="Override dashboard base URL")
    parser.add_argument(
        "--dashboard-startup-timeout",
        type=float,
        default=_DASHBOARD_STARTUP_TIMEOUT,
        help="Seconds to wait for an automatically started Dashboard",
    )
    parser.add_argument("--local", action="store_true", help="Pass --local to each task run")
    parser.add_argument("--dry-run", action="store_true", help="Resolve sectors and print commands only")
    parser.add_argument(
        "--force-rerun",
        action="store_true",
        help="Rerun sector tasks even when valid output files already exist",
    )
    parser.add_argument(
        "--write-only",
        "--merge-only",
        dest="write_only",
        action="store_true",
        help="Skip discovery/crawl and write this date's existing task outputs",
    )
    parser.add_argument(
        "--skip-write",
        "--skip-upload",
        dest="skip_write",
        action="store_true",
        help="Validate generated factors without writing them to the API",
    )
    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Write successful outputs even when some sector tasks fail",
    )


def _validate_args(args: argparse.Namespace) -> str:
    trading_date = str(args.date or "").strip() or _today_local()
    if not _DATE_RE.fullmatch(trading_date):
        raise ValueError(f"Invalid --date (expected YYYY-MM-DD): {args.date!r}")
    if int(args.concurrency) < 1:
        raise ValueError("--concurrency must be at least 1")
    if int(args.top_n) < 1:
        raise ValueError("--top-n must be at least 1")
    if float(args.min_cap) < 0:
        raise ValueError("--min-cap cannot be negative")
    if float(args.dashboard_startup_timeout) <= 0:
        raise ValueError("--dashboard-startup-timeout must be greater than 0")
    if args.dry_run and args.write_only:
        raise ValueError("--dry-run and --write-only cannot be used together")
    if args.force_rerun and args.write_only:
        raise ValueError("--force-rerun and --write-only cannot be used together")
    return trading_date


def _today_local() -> str:
    return datetime.now().astimezone().date().isoformat()


def _resolve_markets(raw: list[str] | None) -> tuple[str, ...]:
    if not raw:
        return _MARKETS
    return tuple(dict.fromkeys(str(item).strip().lower() for item in raw))


def _dojoagents_executable() -> str:
    candidates = [Path(sys.argv[0]).expanduser(), Path(sys.executable).with_name("dojoagents")]
    for candidate in candidates:
        if candidate.name == "dojoagents" and candidate.is_file():
            return str(candidate.resolve())
    executable = shutil.which("dojoagents")
    if executable:
        return executable
    raise FileNotFoundError("dojoagents executable was not found beside the current Python interpreter or on PATH")


def _local_dashboard_bind(base_url: str) -> tuple[str, int] | None:
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").strip().lower()
    if parsed.scheme != "http" or host not in {
        "127.0.0.1",
        "localhost",
        "::1",
        "0.0.0.0",
        "::",
    }:
        return None
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    bind_host = "127.0.0.1" if host == "localhost" else host
    return bind_host, port


async def _wait_for_dashboard(
    process: asyncio.subprocess.Process,
    *,
    base_url: str,
    timeout: float,
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        if await check_dashboard_health(base_url):
            LOGGER.info("Runtime Dashboard is ready: %s", base_url)
            return
        if process.returncode is not None:
            raise RuntimeError(f"Runtime Dashboard exited during startup with code {process.returncode}")
        await asyncio.sleep(0.5)
    raise TimeoutError(f"Runtime Dashboard did not become ready within {timeout:g}s: {base_url}")


async def _stop_dashboard(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    LOGGER.info("Stopping managed runtime Dashboard (pid=%s)", process.pid)
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=30.0)
    except asyncio.TimeoutError:
        LOGGER.warning("Managed runtime Dashboard did not stop gracefully; killing pid=%s", process.pid)
        process.kill()
        await process.wait()


@asynccontextmanager
async def managed_dashboard_runtime(
    *,
    base_url: str,
    config_path: str,
    startup_timeout: float,
):
    if await check_dashboard_health(base_url):
        LOGGER.info("Using existing runtime Dashboard: %s", base_url)
        yield
        return

    bind = _local_dashboard_bind(base_url)
    if bind is None:
        raise RuntimeError(f"Dashboard is not reachable at {base_url}; automatic startup only supports local Dashboard URLs")
    host, port = bind
    command = [
        _dojoagents_executable(),
        "dashboard",
        "--host",
        host,
        "--port",
        str(port),
        "--config",
        str(config_path),
        "--lightweight-runtime",
    ]
    LOGGER.info("Starting managed runtime Dashboard: %s", " ".join(command))
    process = await asyncio.create_subprocess_exec(*command)
    try:
        await _wait_for_dashboard(
            process,
            base_url=base_url,
            timeout=float(startup_timeout),
        )
        yield
    finally:
        await _stop_dashboard(process)


def _sector_display_name(item: dict[str, Any]) -> str:
    name = item.get("name")
    if isinstance(name, dict):
        return str(name.get("zh") or name.get("en") or "").strip()
    return str(name or "").strip()


def _sector_path_id(item: dict[str, Any]) -> str:
    parts = [str(item.get(key) or "").strip() for key in ("level1_id", "level2_id", "level3_id")]
    return "/".join(parts) if all(parts) else ""


def _top_jobs_for_market(market: str, payload: dict[str, Any], *, top_n: int) -> list[SectorJob]:
    gainers = payload.get("gainers") if isinstance(payload.get("gainers"), list) else []
    losers = payload.get("losers") if isinstance(payload.get("losers"), list) else []
    unique: dict[str, dict[str, Any]] = {}
    for item in [*gainers, *losers]:
        if not isinstance(item, dict):
            continue
        path = _sector_path_id(item)
        if path:
            unique.setdefault(path, item)
    ranked = sorted(
        (item for item in unique.values() if _sector_display_name(item)),
        key=lambda row: abs(float(row.get("change_percent") or 0)),
        reverse=True,
    )
    return [
        SectorJob(
            market=market,
            name=_sector_display_name(item),
            sector_path_id=_sector_path_id(item),
            change_percent=float(item.get("change_percent") or 0),
        )
        for item in ranked[:top_n]
    ]


async def _fetch_movers_for_market(
    client: httpx.AsyncClient,
    *,
    base_url: str,
    market: str,
    trading_date: str,
    top_n: int,
    min_cap: float,
) -> dict[str, Any]:
    params = {
        "market": market,
        "limit": str(top_n),
        "start_date": trading_date,
        "end_date": trading_date,
        "include_members": "false",
        "min_cap_us": str(min_cap),
        "min_cap_cn": str(min_cap),
        "min_cap_hk": str(min_cap),
    }
    url = f"{base_url.rstrip('/')}/api/v1/market/sector-movers?{urlencode(params)}"
    LOGGER.info("Fetching discovery movers: %s", url)
    response = await client.get(url)
    try:
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        try:
            body = response.json()
            detail = body.get("detail") if isinstance(body, dict) else body
        except ValueError:
            detail = response.text.strip()
        raise RuntimeError(f"Dashboard sector-movers failed for market={market} " f"(HTTP {response.status_code}): {detail or 'empty response'}") from exc
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError(f"sector-movers returned invalid payload for market={market}")
    markets = data.get("markets") if isinstance(data.get("markets"), dict) else {}
    payload = markets.get(market)
    return payload if isinstance(payload, dict) else {}


async def fetch_discovery_jobs(
    *,
    base_url: str,
    trading_date: str,
    top_n: int,
    min_cap: float,
    markets: tuple[str, ...] = _MARKETS,
) -> list[SectorJob]:
    open_markets = set(open_markets_on(trading_date, markets))
    closed_markets = [market for market in markets if market not in open_markets]
    LOGGER.info(
        "Trading-day filter for %s: open=%s closed=%s",
        trading_date,
        ",".join(market for market in markets if market in open_markets) or "(none)",
        ",".join(closed_markets) or "(none)",
    )
    jobs: list[SectorJob] = []
    async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
        for market in markets:
            if market not in open_markets:
                LOGGER.info("Skip market=%s: not a trading day on %s", market, trading_date)
                continue
            payload = await _fetch_movers_for_market(
                client,
                base_url=base_url,
                market=market,
                trading_date=trading_date,
                top_n=top_n,
                min_cap=min_cap,
            )
            market_jobs = _top_jobs_for_market(market, payload, top_n=top_n)
            LOGGER.info(
                "market=%s selected %d sectors: %s",
                market,
                len(market_jobs),
                ", ".join(f"{job.name}({job.change_percent:+.2f}%)" for job in market_jobs),
            )
            jobs.extend(market_jobs)
    return jobs


def _build_task_command(job: SectorJob, *, trading_date: str, local: bool, config: str | None = None) -> list[str]:
    command = [
        _dojoagents_executable(),
        "tasks",
        "run",
        "--task",
        "attribution-factor-crawl",
        "--date",
        trading_date,
    ]
    if config:
        command.extend(["--config", config])
    if local:
        command.append("--local")
    command.extend(
        [
            f"market={job.market}",
            f"sector_id={job.sector_path_id}",
            f"sector_path_id={job.sector_path_id}",
            f"sector_name={job.name}",
            f"change_percent={job.change_percent:g}",
        ]
    )
    return command


async def _run_one(
    job: SectorJob,
    *,
    trading_date: str,
    local: bool,
    config: str | None,
    semaphore: asyncio.Semaphore,
    dry_run: bool,
) -> tuple[SectorJob, int]:
    command = _build_task_command(job, trading_date=trading_date, local=local, config=config)
    async with semaphore:
        LOGGER.info("START %s %s | %s", job.market, job.name, " ".join(command))
        if dry_run:
            return job, 0
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await process.communicate()
        code = int(process.returncode or 0)
        if code:
            output = (stdout or b"").decode("utf-8", errors="replace")
            LOGGER.error("FAIL %s %s exit=%s\n%s", job.market, job.name, code, output[-2000:])
        else:
            LOGGER.info("OK %s %s", job.market, job.name)
        return job, code


def _read_jsonl(paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in paths:
        line_number = 0
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    if not line.strip():
                        continue
                    value = json.loads(line)
                    values = value if isinstance(value, list) else [value]
                    if not all(isinstance(item, dict) for item in values):
                        raise ValueError("each JSONL value must be an object or an array of objects")
                    rows.extend(values)
        except Exception as exc:
            raise ValueError(f"Cannot read {path} at line {line_number}: {exc}") from exc
    return rows


def _api_write_items(raw_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    items_by_uid: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for index, raw in enumerate(raw_rows, start=1):
        try:
            item = AttributionFactor.model_validate(raw).model_dump(mode="json")
        except ValidationError as exc:
            errors.append(f"row {index}: {exc.errors(include_url=False)}")
            continue
        item["role"] = item.get("role") or "explains_move"
        item["event_time"] = item.get("event_time") or None
        if item["event_time"] and not re.fullmatch(
            r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?",
            str(item["event_time"]),
        ):
            errors.append(f"row {index}: event_time must include date and time")
            continue
        if item.get("payload_status") == "draft":
            item["payload_status"] = "ready"
        factor_uid = str(raw.get("factor_uid") or "").strip() or _factor_uid(item)
        item["factor_uid"] = factor_uid
        items_by_uid[factor_uid] = {key: value for key, value in item.items() if value is not None}
    if errors:
        preview = "; ".join(errors[:5])
        raise ValueError(f"Invalid attribution factor output ({len(errors)} rows): {preview}")
    return list(items_by_uid.values())


def _factor_uid(item: dict[str, Any]) -> str:
    claim = item.get("claim") if isinstance(item.get("claim"), dict) else {}
    identity = (
        str(item.get("market") or "").strip().casefold(),
        str(item.get("sector_id") or "").strip(),
        str(item.get("factor_topic") or "").strip().casefold(),
        str(item.get("event_time") or "").strip(),
        str(claim.get("zh") or "").strip().casefold(),
        str(claim.get("en") or "").strip().casefold(),
    )
    digest = hashlib.sha256("\x1f".join(identity).encode("utf-8")).hexdigest()
    return f"dojoagents:{digest}"


def _validate_output_context(path: Path, rows: Iterable[dict[str, Any]], trading_date: str) -> None:
    match = re.fullmatch(
        rf"attribution_factors_(us|cn|hk)_(.+)_{re.escape(trading_date)}\.jsonl",
        path.name,
    )
    if not match:
        raise ValueError(f"Unexpected attribution output filename: {path.name}")
    expected_market, expected_sector = match.groups()
    for index, row in enumerate(rows, start=1):
        market = str(row.get("market") or "").strip()
        sector = str(row.get("sector_id") or "").strip().replace("/", "_")
        if market != expected_market or sector != expected_sector:
            raise ValueError(
                f"{path.name} row {index} context mismatch: " f"expected market={expected_market} sector={expected_sector}, " f"got market={market or '-'} sector={sector or '-'}"
            )


def _has_reusable_output(path: Path, trading_date: str) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        rows = _read_jsonl([path])
        if not rows:
            return False
        _validate_output_context(path, rows, trading_date)
        return bool(_api_write_items(rows))
    except ValueError as exc:
        LOGGER.warning("Existing output is invalid and will be rerun: %s (%s)", path, exc)
        return False


def _partition_jobs(
    jobs: Iterable[SectorJob],
    *,
    output_dir: Path,
    trading_date: str,
    force_rerun: bool,
) -> tuple[list[SectorJob], list[SectorJob]]:
    reused: list[SectorJob] = []
    pending: list[SectorJob] = []
    for job in jobs:
        path = output_dir / job.output_filename(trading_date)
        if not force_rerun and _has_reusable_output(path, trading_date):
            reused.append(job)
        else:
            pending.append(job)
    return reused, pending


async def _close_client(client: Any) -> None:
    close = getattr(client, "aclose", None)
    if callable(close):
        await close()
        return
    close = getattr(getattr(client, "_client", None), "aclose", None)
    if callable(close):
        await close()


def _sdk_client(config: Any) -> AsyncDojo:
    sdk = config.dojosdk
    kwargs = {
        "api_key": sdk.api_key if sdk else None,
        "base_url": sdk.base_url if sdk else None,
        "timeout": sdk.timeout if sdk else 60.0,
        "max_retries": sdk.max_retries if sdk else 1,
    }
    return AsyncDojo(**{key: value for key, value in kwargs.items() if value is not None})


async def _write_attribution_factors(client: AsyncDojo, items: list[dict[str, Any]], *, generation_time: str) -> int:
    written = 0
    for offset in range(0, len(items), _WRITE_BATCH_SIZE):
        batch = items[offset : offset + _WRITE_BATCH_SIZE]
        await client.analysis.create_attribution_factor(body={"items": batch, "generation_time": generation_time})
        written += len(batch)
        LOGGER.info("Wrote attribution-factor batch: %d/%d", written, len(items))
    return written


async def run_attribution_factor_crawl(args: argparse.Namespace) -> int:
    trading_date = _validate_args(args)
    generation_time = datetime.now(timezone.utc).isoformat()
    store = ConfigStore(args.config)
    config = store.snapshot()
    configure_logging(config.logging)
    if not config.tasks.enabled:
        raise ValueError("tasks.enabled is false in config")

    output_dir = Path(config.tasks.output_root).expanduser() / "attribution-factor-crawl"
    markets = _resolve_markets(args.market)
    output_paths: list[Path]
    failed: list[SectorJob] = []
    if args.write_only:
        output_paths = sorted(path for market in markets for path in output_dir.glob(f"attribution_factors_{market}_*_{trading_date}.jsonl"))
    else:
        base_url = dashboard_base_url_from_config(args.config, override=args.dashboard_url or None)
        async with managed_dashboard_runtime(
            base_url=base_url,
            config_path=str(args.config),
            startup_timeout=float(args.dashboard_startup_timeout),
        ):
            jobs = await fetch_discovery_jobs(
                base_url=base_url,
                trading_date=trading_date,
                top_n=int(args.top_n),
                min_cap=float(args.min_cap),
                markets=markets,
            )
            if not jobs:
                if not open_markets_on(trading_date, markets):
                    LOGGER.info(
                        "No open markets on %s for %s; nothing to run",
                        trading_date,
                        ",".join(markets),
                    )
                    return 0
                raise ValueError(f"No discovery sectors for trading_date={trading_date} markets={','.join(markets)}")
            reused_jobs, pending_jobs = _partition_jobs(
                jobs,
                output_dir=output_dir,
                trading_date=trading_date,
                force_rerun=bool(args.force_rerun),
            )
            for job in reused_jobs:
                path = output_dir / job.output_filename(trading_date)
                LOGGER.info("SKIP existing output %s %s | %s", job.market, job.name, path)
            if reused_jobs:
                LOGGER.info(
                    "Reusing %d existing sector outputs; running %d remaining tasks",
                    len(reused_jobs),
                    len(pending_jobs),
                )
            config_override = None if args.config == "~/.dojo/agents.yaml" else str(args.config)
            semaphore = asyncio.Semaphore(int(args.concurrency))
            results = await asyncio.gather(
                *(
                    _run_one(
                        job,
                        trading_date=trading_date,
                        local=bool(args.local),
                        config=config_override,
                        semaphore=semaphore,
                        dry_run=bool(args.dry_run),
                    )
                    for job in pending_jobs
                )
            )
            if args.dry_run:
                LOGGER.info(
                    "Dry run complete: run=%d skipped=%d",
                    len(results),
                    len(reused_jobs),
                )
                return 0
            failed = [job for job, code in results if code]
            if failed and not args.allow_partial:
                raise RuntimeError(f"{len(failed)} crawl task(s) failed; factors were not written")
            successful = [job for job, code in results if not code]
            output_paths = [output_dir / job.output_filename(trading_date) for job in [*reused_jobs, *successful]]

    missing_outputs = [str(path) for path in output_paths if not path.is_file()]
    if missing_outputs:
        raise FileNotFoundError("Successful tasks are missing outputs: " + ", ".join(missing_outputs))
    if not output_paths:
        raise ValueError(f"No attribution factor outputs found for {trading_date}")
    raw_rows: list[dict[str, Any]] = []
    for path in output_paths:
        file_rows = _read_jsonl([path])
        _validate_output_context(path, file_rows, trading_date)
        raw_rows.extend(file_rows)
    items = _api_write_items(raw_rows)
    if not items:
        raise ValueError(f"Attribution factor outputs for {trading_date} are empty")

    if args.skip_write:
        LOGGER.info(
            "Validated %d attribution factors without API write%s",
            len(items),
            f"; partial_failures={len(failed)}" if failed else "",
        )
        return 0

    client = _sdk_client(config)
    try:
        written = await _write_attribution_factors(client, items, generation_time=generation_time)
        LOGGER.info(
            "Successfully wrote %d attribution factors through create_attribution_factor%s",
            written,
            f" partial_failures={len(failed)}" if failed else "",
        )
        return 0
    finally:
        await _close_client(client)


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        return asyncio.run(run_attribution_factor_crawl(args))
    except KeyboardInterrupt:
        LOGGER.error("Interrupted")
        return 130
    except Exception as exc:
        LOGGER.exception("attribution-factor-crawl failed: %s", exc)
        return 1


__all__ = [
    "SectorJob",
    "build_parser",
    "configure_parser",
    "fetch_discovery_jobs",
    "main",
    "run_attribution_factor_crawl",
]
