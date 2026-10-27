from __future__ import annotations

from types import SimpleNamespace

import pytest

from dojoagents.cli import main as cli_main


@pytest.mark.anyio
async def test_cli_chat_uses_canonical_financial_request_context(monkeypatch) -> None:
    requests = []

    class Agent:
        async def run(self, request):
            requests.append(request)
            return SimpleNamespace(content="done")

    runtime = SimpleNamespace(agent=Agent())
    monkeypatch.setattr(
        cli_main.Runtime,
        "from_default_config",
        lambda: runtime,
    )
    args = cli_main.build_parser().parse_args(
        [
            "chat",
            "analyze",
            "--market",
            "stock",
            "--symbols",
            " aapl, MSFT ",
            "--timeframe",
            "1d",
        ]
    )

    assert await cli_main._run_chat(args) == 0

    [request] = requests
    assert request.quant is None
    assert request.context == {
        "financial": {
            "market": "stock",
            "symbols": ["aapl", "MSFT"],
            "timeframe": "1d",
        }
    }
