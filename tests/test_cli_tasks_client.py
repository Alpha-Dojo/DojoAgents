from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from dojoagents.harnesses.built_in.financial.surfaces.tasks_client import (
    DashboardTaskClientError,
    _dashboard_client,
    _is_local_dashboard,
    check_dashboard_health,
    create_chat_run,
    dashboard_base_url_from_config,
    wait_for_chat_run,
)

RealAsyncClient = httpx.AsyncClient


def test_dashboard_base_url_from_config_override() -> None:
    assert dashboard_base_url_from_config("~/.dojo/agents.yaml", override="http://127.0.0.1:9999/") == ("http://127.0.0.1:9999")


@pytest.mark.parametrize(
    ("base_url", "expected"),
    [
        ("http://127.0.0.1:8765", True),
        ("http://localhost:8765", True),
        ("http://[::1]:8765", True),
        ("http://10.0.0.5:8765", False),
    ],
)
def test_is_local_dashboard(base_url: str, expected: bool) -> None:
    assert _is_local_dashboard(base_url) is expected


def test_dashboard_client_bypasses_proxy_for_localhost() -> None:
    client = _dashboard_client(timeout=1.0, base_url="http://127.0.0.1:8765")
    assert client._trust_env is False


def _client_factory(transport: httpx.MockTransport):
    def factory(*args, **kwargs):
        return RealAsyncClient(transport=transport, **kwargs)

    return factory


@pytest.mark.asyncio
async def test_check_dashboard_health_success() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/utility/market-data-revision"
        return httpx.Response(200, json={"revision": "abc"})

    transport = httpx.MockTransport(handler)
    with patch("dojoagents.harnesses.built_in.financial.surfaces.tasks_client.httpx.AsyncClient", side_effect=_client_factory(transport)):
        assert await check_dashboard_health("http://127.0.0.1:8765") is True


@pytest.mark.asyncio
async def test_create_chat_run_posts_pipeline_message() -> None:
    captured: dict = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["payload"] = request.read().decode("utf-8")
        return httpx.Response(200, json={"run_id": "run-123", "session_id": "sess-1"})

    transport = httpx.MockTransport(handler)
    with patch("dojoagents.harnesses.built_in.financial.surfaces.tasks_client.httpx.AsyncClient", side_effect=_client_factory(transport)):
        payload = await create_chat_run(
            base_url="http://127.0.0.1:8765",
            message="/pipeline daily-market-events 2026-06-01",
            session_id="cli-task-daily-market-events-2026-06-01",
        )

    assert payload["run_id"] == "run-123"
    assert captured["path"] == "/api/chat/runs"
    assert "/pipeline daily-market-events 2026-06-01" in captured["payload"]
    assert "cli-task-daily-market-events-2026-06-01" in captured["payload"]


@pytest.mark.asyncio
async def test_wait_for_chat_run_polls_until_terminal_status() -> None:
    calls = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        calls["count"] += 1
        if calls["count"] == 1:
            return httpx.Response(
                200,
                json={"run_id": "run-123", "status": "running", "event_count": 1},
            )
        return httpx.Response(
            200,
            json={
                "run_id": "run-123",
                "status": "done",
                "event_count": 4,
                "metadata": {"pipeline_completed": True},
            },
        )

    transport = httpx.MockTransport(handler)
    with patch("dojoagents.harnesses.built_in.financial.surfaces.tasks_client.httpx.AsyncClient", side_effect=_client_factory(transport)):
        with patch("dojoagents.harnesses.built_in.financial.surfaces.tasks_client.asyncio.sleep", new_callable=AsyncMock):
            record = await wait_for_chat_run("http://127.0.0.1:8765", "run-123", poll_interval=0.01)

    assert calls["count"] == 2
    assert record["status"] == "done"
    assert record["metadata"]["pipeline_completed"] is True


@pytest.mark.asyncio
async def test_create_chat_run_raises_on_http_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="dashboard unavailable")

    transport = httpx.MockTransport(handler)
    with patch("dojoagents.harnesses.built_in.financial.surfaces.tasks_client.httpx.AsyncClient", side_effect=_client_factory(transport)):
        with pytest.raises(DashboardTaskClientError, match="503"):
            await create_chat_run(
                base_url="http://127.0.0.1:8765",
                message="hello",
                session_id="sess-1",
            )
