from dojoagents.cli.main import build_parser


def test_precompute_sector_accepts_kline_concurrency_override() -> None:
    args = build_parser().parse_args(["precompute-sector", "--market", "us", "--kline-concurrency", "7"])

    assert args.kline_concurrency == 7
