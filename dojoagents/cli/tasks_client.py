from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from dojoagents.config.loader import ConfigStore
from dojoagents.logging import LOGGER

_DEFAULT_POLL_INTERVAL_S = 2.0
_HEALTH_TIMEOUT_S = 5.0
_REQUEST_TIMEOUT_S = 60.0


class DashboardTaskClientError(RuntimeError):
    pass


def dashboard_base_url_from_config(config_path: str, override: str | None = None) -> str:
    if override and str(override).strip():
        return str(override).strip().rstrip("/")
    config = ConfigStore(config_path).snapshot()
    host = str(config.dashboard.host or "127.0.0.1").strip() or "127.0.0.1"
    port = int(config.dashboard.port or 8765)
    return f"http://{host}:{port}"


def _api_url(base_url: str, path: str) -> str:
    normalized = base_url.rstrip("/") + "/"
    if not path.startswith("/"):
        path = f"/{path}"
    return urljoin(normalized, path.lstrip("/"))


def _is_local_dashboard(base_url: str) -> bool:
    host = (urlparse(base_url).hostname or "").strip().lower()
    return host in {"127.0.0.1", "localhost", "::1"}


def _dashboard_client(*, timeout: float, base_url: str) -> httpx.AsyncClient:
    # Local dashboard calls must bypass HTTP(S)_PROXY; otherwise httpx may route
    # 127.0.0.1 through the proxy and fail even when the server is running.
    return httpx.AsyncClient(timeout=timeout, trust_env=not _is_local_dashboard(base_url))


async def check_dashboard_health(base_url: str) -> bool:
    url = _api_url(base_url, "/api/v1/utility/market-data-revision")
    try:
        async with _dashboard_client(timeout=_HEALTH_TIMEOUT_S, base_url=base_url) as client:
            response = await client.get(url)
            if response.status_code != 200:
                LOGGER.debug(
                    "Dashboard health check failed: url=%s status=%s body=%s",
                    url,
                    response.status_code,
                    response.text[:200],
                )
                return False
            payload = response.json()
            return isinstance(payload, dict)
    except (httpx.HTTPError, ValueError) as exc:
        LOGGER.debug("Dashboard health check error: url=%s error=%s", url, exc)
        return False


async def create_chat_run(
    *,
    base_url: str,
    message: str,
    session_id: str,
    model: str = "default",
) -> dict[str, Any]:
    url = _api_url(base_url, "/api/chat/runs")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": message}],
        "metadata": {
            "session_id": session_id,
            "persist_session": False,
            "locale": "zh",
            "event_format": "dojo.v2",
        },
    }
    async with _dashboard_client(timeout=_REQUEST_TIMEOUT_S, base_url=base_url) as client:
        response = await client.post(url, json=payload)
        if response.status_code >= 400:
            detail = response.text.strip() or response.reason_phrase
            raise DashboardTaskClientError(f"Dashboard rejected run ({response.status_code}): {detail}")
        data = response.json()
        if not isinstance(data, dict) or not data.get("run_id"):
            raise DashboardTaskClientError("Dashboard returned an invalid run payload")
        return data


async def fetch_chat_run(base_url: str, run_id: str) -> dict[str, Any]:
    url = _api_url(base_url, f"/api/chat/runs/{run_id}")
    async with _dashboard_client(timeout=_REQUEST_TIMEOUT_S, base_url=base_url) as client:
        response = await client.get(url)
        if response.status_code == 404:
            raise DashboardTaskClientError(f"Unknown run: {run_id}")
        if response.status_code >= 400:
            detail = response.text.strip() or response.reason_phrase
            raise DashboardTaskClientError(f"Failed to fetch run ({response.status_code}): {detail}")
        data = response.json()
        if not isinstance(data, dict):
            raise DashboardTaskClientError("Dashboard returned invalid run status payload")
        return data


async def wait_for_chat_run(
    base_url: str,
    run_id: str,
    *,
    poll_interval: float = _DEFAULT_POLL_INTERVAL_S,
) -> dict[str, Any]:
    last_event_count = -1
    while True:
        record = await fetch_chat_run(base_url, run_id)
        status = str(record.get("status") or "")
        event_count = int(record.get("event_count") or 0)
        if event_count != last_event_count:
            LOGGER.info(
                "Dashboard run %s status=%s events=%d pipeline_completed=%s",
                run_id,
                status,
                event_count,
                record.get("pipeline_completed"),
            )
            last_event_count = event_count
        if status in {"done", "error", "cancelled"}:
            return record
        await asyncio.sleep(max(0.5, float(poll_interval)))


async def run_pipeline_via_dashboard(
    *,
    base_url: str,
    pipeline_id: str,
    trading_date: str,
    session_id: str,
    poll_interval: float = _DEFAULT_POLL_INTERVAL_S,
) -> dict[str, Any]:
    if not await check_dashboard_health(base_url):
        raise DashboardTaskClientError(
            f"Dashboard is not reachable at {base_url}. "
            "Start it with `dojoagents dashboard` or pass --local."
        )

    message = f"/pipeline {pipeline_id} {trading_date}"
    LOGGER.info(
        "Submitting pipeline to dashboard: base_url=%s pipeline=%s date=%s session_id=%s",
        base_url,
        pipeline_id,
        trading_date,
        session_id,
    )
    created = await create_chat_run(base_url=base_url, message=message, session_id=session_id)
    run_id = str(created["run_id"])
    LOGGER.info("Dashboard run created: run_id=%s", run_id)
    return await wait_for_chat_run(base_url, run_id, poll_interval=poll_interval)
