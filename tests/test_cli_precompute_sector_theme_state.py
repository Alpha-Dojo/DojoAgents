from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

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
@pytest.mark.parametrize("skip_fundamentals,skip_volume_enrich", [(False, False), (True, False), (False, True), (True, True)])
@pytest.mark.parametrize("failure_store", [None, "sector_store", "benchmark_store"])
async def test_theme_state_command_reads_local_phase_a_without_precomputed_store_sync(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    skip_fundamentals: bool,
    skip_volume_enrich: bool,
    failure_store: str | None,
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

        async def ensure_stores_loaded(self, *store_names: str) -> None:
            calls.setdefault("loads", []).extend(store_names)  # type: ignore[union-attr]
            if failure_store in store_names:
                raise RuntimeError("required data unavailable")

    class Progress:
        callback = None

        def close(self) -> None:
            return None

    client = object()
    writer = object()

    async def build(**kwargs: object) -> dict[str, object]:
        calls["build"] = kwargs
        return {"published_dir": str(output_dir)}

    constructor = Mock(side_effect=[client, writer])
    close = AsyncMock()
    build_mock = AsyncMock(side_effect=build)
    monkeypatch.setenv("DOJO_ONLINE", "false")
    monkeypatch.setenv("DOJO_HF_OFFLINE", "true")
    monkeypatch.setattr(command, "create_async_dojo", constructor)
    monkeypatch.setattr(command, "close_async_dojo", close)
    monkeypatch.setattr(command, "FinancialDomainRegistry", Registry)
    monkeypatch.setattr(command, "_PrecomputeProgressReporter", Progress)
    monkeypatch.setattr(command, "build_theme_state_precomputed", build_mock)
    monkeypatch.setattr(command, "apply_configured_ticker_market_cap_mins", lambda _path: {})

    args = SimpleNamespace(
        data_root=tmp_path,
        input_dir=input_dir,
        output_dir=output_dir,
        config=str(tmp_path / "agents.yaml"),
        start_date=None,
        end_date=None,
        upload=True,
        skip_fundamentals=skip_fundamentals,
        skip_volume_enrich=skip_volume_enrich,
    )
    if failure_store is not None:
        with pytest.raises(RuntimeError, match="required data unavailable"):
            await command.run_precompute_sector_theme_state(args)
        build_mock.assert_not_awaited()
        registry = calls["registry"]
        assert isinstance(registry, Registry)
        assert registry.sector_precomputed_store.paths == []
        assert close.await_count == 2
        return
    assert await command.run_precompute_sector_theme_state(args) == 0

    assert calls["init"] == (client, tmp_path.resolve(), False)
    assert all(call.kwargs["online"] is True for call in constructor.call_args_list)
    required = ["sector_store", "benchmark_store"]
    if not skip_volume_enrich:
        required.extend(["stock_store", "stock_sector_store", "kline_store"])
    assert calls["loads"] == required
    build_args = calls["build"]
    assert isinstance(build_args, dict)
    assert build_args["source_dir"] == input_dir
    assert build_args["out_dir"] == output_dir
    assert build_args["upload_client"] is writer
    registry = calls["registry"]
    assert isinstance(registry, Registry)
    assert build_args["fin_store"] is (None if skip_fundamentals else registry.stock_fin_indicators_store)
    assert registry.sector_precomputed_store.paths == [output_dir]
    assert registry.theme_state_precomputed_store.paths == [output_dir]
    assert close.await_count == 2
