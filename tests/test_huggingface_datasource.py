from __future__ import annotations

import threading
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module

import httpx
import pytest

from dojo.datasource.config import HFConfig
from dojo.datasource.huggingface import HuggingFaceDataSource
from dojo.client.async_client import AsyncDojo


def _config(tmp_path, *, retries: int = 2) -> HFConfig:
    return HFConfig(
        backend="huggingface",
        cache_dir=str(tmp_path),
        download_timeout_seconds=7,
        etag_timeout_seconds=3,
        max_download_retries=retries,
    )


def _download(source: HuggingFaceDataSource) -> str:
    return source._download_and_cleanup(
        repo_id="test/repo",
        filename="data.parquet",
        repo_type="dataset",
        revision="main",
        cache_dir=source._cfg.cache_dir,
        local_files_only=False,
    )


def _force_download(source: HuggingFaceDataSource) -> str:
    return source._download_and_cleanup(
        repo_id="test/repo",
        filename="data.parquet",
        repo_type="dataset",
        revision="main",
        cache_dir=source._cfg.cache_dir,
        local_files_only=False,
        force_download=True,
    )


def test_huggingface_datasource_does_not_start_download_watchdog(tmp_path):
    before = {thread.ident for thread in threading.enumerate()}

    HuggingFaceDataSource(_config(tmp_path))

    started = [thread.name for thread in threading.enumerate() if thread.ident not in before and thread.name == "DojoSDK-DownloadWatchdog"]
    assert started == []


def test_huggingface_download_retries_transient_errors_with_a_finite_limit(
    tmp_path,
    monkeypatch,
):
    attempts = 0

    def fail_download(**_kwargs):
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("slow dataset")

    monkeypatch.setattr("huggingface_hub.hf_hub_download", fail_download)
    monkeypatch.setattr("dojo.datasource.network.resolve_backend", lambda _config: "huggingface")
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    source = HuggingFaceDataSource(_config(tmp_path, retries=2))

    with pytest.raises(httpx.ReadTimeout):
        _download(source)

    assert attempts == 3


def test_modelscope_download_retries_transient_errors_with_a_finite_limit(
    tmp_path,
    monkeypatch,
):
    attempts = 0

    def fail_download(**_kwargs):
        nonlocal attempts
        attempts += 1
        raise httpx.ReadTimeout("slow dataset")

    file_download = import_module("modelscope.hub.file_download")
    monkeypatch.setattr(file_download, "dataset_file_download", fail_download)
    monkeypatch.setattr(
        "dojo.datasource.network.resolve_backend",
        lambda _config: "modelscope",
    )
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    source = HuggingFaceDataSource(_config(tmp_path, retries=2))

    with pytest.raises(httpx.ReadTimeout):
        source._download_and_cleanup(
            repo_id="test/repo",
            ms_repo_id="test/modelscope-repo",
            filename="data.parquet",
            repo_type="dataset",
            revision="main",
            cache_dir=source._cfg.cache_dir,
            local_files_only=True,
        )

    assert attempts == 3


def test_huggingface_download_single_flight_reuses_completed_path(
    tmp_path,
    monkeypatch,
):
    downloaded = tmp_path / "data.parquet"
    downloaded.write_bytes(b"parquet")
    entered = threading.Event()
    release = threading.Event()
    attempts = 0

    def download_once(**_kwargs):
        nonlocal attempts
        attempts += 1
        entered.set()
        assert release.wait(timeout=2)
        return str(downloaded)

    monkeypatch.setattr("huggingface_hub.hf_hub_download", download_once)
    monkeypatch.setattr("dojo.datasource.network.resolve_backend", lambda _config: "huggingface")
    source = HuggingFaceDataSource(_config(tmp_path))

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(_download, source)
        assert entered.wait(timeout=1)
        second = executor.submit(_download, source)
        release.set()
        assert first.result(timeout=2) == str(downloaded)
        assert second.result(timeout=2) == str(downloaded)

    assert attempts == 1


@pytest.mark.asyncio
async def test_async_dojo_applies_client_limits_to_offline_downloads(
    monkeypatch,
):
    monkeypatch.setenv("DOJO_ONLINE", "0")
    monkeypatch.delenv("DOJO_HF_DOWNLOAD_TIMEOUT", raising=False)
    monkeypatch.delenv("DOJO_HF_MAX_RETRIES", raising=False)

    client = AsyncDojo(timeout=17, max_retries=4)
    try:
        assert client._data_source._cfg.download_timeout_seconds == 17
        assert client._data_source._cfg.max_download_retries == 4
    finally:
        await client._client.aclose()


def test_force_download_replaces_the_single_flight_path_cache(
    tmp_path,
    monkeypatch,
):
    first_path = tmp_path / "first.parquet"
    second_path = tmp_path / "second.parquet"
    first_path.write_bytes(b"first")
    second_path.write_bytes(b"second")
    paths = iter((str(first_path), str(second_path)))

    monkeypatch.setattr(
        "huggingface_hub.hf_hub_download",
        lambda **_kwargs: next(paths),
    )
    monkeypatch.setattr(
        "dojo.datasource.network.resolve_backend",
        lambda _config: "huggingface",
    )
    source = HuggingFaceDataSource(_config(tmp_path))

    assert _download(source) == str(first_path)
    assert _force_download(source) == str(second_path)
    assert _download(source) == str(second_path)
