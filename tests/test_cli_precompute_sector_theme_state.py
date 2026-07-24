from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from dojoagents.cli.main import build_parser
from dojoagents.dashboard.cli import precompute_theme_state as command


def test_theme_state_parser_accepts_explicit_input_and_output_dirs(tmp_path: Path) -> None:
    input_dir = tmp_path / "phase-a"
    output_dir = tmp_path / "published"
    args = build_parser().parse_args(
        [
            "precompute-sector-theme-state",
            "--input-dir",
            str(input_dir),
            "--output-dir",
            str(output_dir),
            "--upload",
        ]
    )

    assert args.input_dir == input_dir
    assert args.output_dir == output_dir
    assert args.upload is True


@pytest.mark.asyncio
async def test_theme_state_command_reads_local_phase_a_without_precomputed_store_sync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_dir = (tmp_path / "phase-a").resolve()
    output_dir = (tmp_path / "published").resolve()
    calls: dict[str, object] = {}

    class ReloadableStore:
        def __init__(self) -> None:
            self.paths: list[Path] = []

        def reload(self, path: Path) -> None:
            self.paths.append(path)

    class Registry:
        def __init__(self) -> None:
            self.sector_store = object()
            self.benchmark_store = object()
            self.stock_fin_indicators_store = object()
            self.stock_store = object()
            self.stock_sector_store = object()
            self.kline_store = object()
            self.sector_precomputed_store = ReloadableStore()
            self.theme_state_precomputed_store = ReloadableStore()
            calls["registry"] = self

        async def init_and_load_all(self, client: object, *, data_root: Path, preload: bool) -> None:
            calls["init"] = (client, data_root, preload)

        async def preload(self, store_names: list[str]) -> list[Exception]:
            calls.setdefault("preloads", []).append(store_names)  # type: ignore[union-attr]
            return []

    class Progress:
        callback = None

        def close(self) -> None:
            return None

    client = object()

    async def build(**kwargs: object) -> dict[str, object]:
        calls["build"] = kwargs
        return {"published_dir": str(output_dir)}

    monkeypatch.setattr(command, "AsyncDojo", lambda: client)
    monkeypatch.setattr(command, "FinancialDomainRegistry", Registry)
    monkeypatch.setattr(command, "_PrecomputeProgressReporter", Progress)
    monkeypatch.setattr(command, "build_theme_state_precomputed", build)
    monkeypatch.setattr(command, "apply_configured_ticker_market_cap_mins", lambda _path: {})

    args = SimpleNamespace(
        data_root=tmp_path,
        input_dir=input_dir,
        output_dir=output_dir,
        config=None,
        start_date=None,
        end_date=None,
        upload=True,
        skip_fundamentals=False,
        skip_volume_enrich=False,
    )
    assert await command.run_precompute_sector_theme_state(args) == 0

    assert calls["init"] == (client, tmp_path.resolve(), False)
    assert calls["preloads"] == [
        [
            "sector_store",
            "benchmark_store",
            "stock_fin_indicators_store",
            "stock_store",
            "stock_sector_store",
        ],
        ["kline_store"],
    ]
    build_args = calls["build"]
    assert isinstance(build_args, dict)
    assert build_args["source_dir"] == input_dir
    assert build_args["out_dir"] == output_dir
    assert build_args["upload_client"] is client
    registry = calls["registry"]
    assert isinstance(registry, Registry)
    assert registry.sector_precomputed_store.paths == [output_dir]
    assert registry.theme_state_precomputed_store.paths == [output_dir]
