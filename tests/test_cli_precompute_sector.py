from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from dojoagents.cli.main import build_parser
from dojoagents.dashboard.cli.precompute_sector import _write_api_batches


def test_precompute_sector_accepts_kline_concurrency_override() -> None:
    args = build_parser().parse_args(["precompute-sector", "--market", "us", "--kline-concurrency", "7"])

    assert args.kline_concurrency == 7


def test_precompute_sector_accepts_constituent_trade_date() -> None:
    args = build_parser().parse_args(["precompute-sector", "--market", "cn", "--trade-date", "2026-08-28", "--upload-api"])

    assert args.trade_date == "2026-08-28"


@pytest.mark.asyncio
async def test_constituent_batches_forward_one_trade_date() -> None:
    create_constituents = AsyncMock()
    client = SimpleNamespace(sectors=SimpleNamespace(create_constituents=create_constituents))

    await _write_api_batches(client, "create_constituents", [{"ticker": "A"}, {"ticker": "B"}], trade_date="2026-08-28")

    create_constituents.assert_awaited_once_with(observations=[{"ticker": "A"}, {"ticker": "B"}], trade_date="2026-08-28")
