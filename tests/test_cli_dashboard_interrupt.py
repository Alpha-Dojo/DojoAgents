from __future__ import annotations

import signal
from types import SimpleNamespace

import uvicorn

from dojoagents.cli.main import _InterruptibleDashboardServer


async def _app(_scope, _receive, _send):
    return None


def test_dashboard_server_forwards_sigint_to_startup_cancellation() -> None:
    cancellations: list[None] = []
    server = _InterruptibleDashboardServer(
        uvicorn.Config(_app),
        cancel_startup=lambda: cancellations.append(None),
    )
    server.lifespan = SimpleNamespace(should_exit=False)

    server.handle_exit(signal.SIGINT, None)

    assert cancellations == [None]
    assert server.should_exit is True
    assert server.lifespan.should_exit is True
