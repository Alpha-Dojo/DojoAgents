from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

from dojoagents.config.models import AgentsConfig, DojoSDKConfig, DojoSDKOfflineConfig
from dojoagents.dojo_sdk import create_async_dojo, create_dojo


def _config(tmp_path: Path) -> AgentsConfig:
    return AgentsConfig(
        dojosdk=DojoSDKConfig(
            api_key="test-key",
            base_url="https://example.invalid",
            timeout=19,
            max_retries=3,
            offline=DojoSDKOfflineConfig(
                enabled=True,
                cache_dir=str(tmp_path / "sdk-cache"),
                backend="modelscope",
                local_files_only=True,
            ),
        )
    )


def test_async_client_uses_canonical_offline_config(tmp_path: Path, monkeypatch) -> None:
    constructor = Mock(return_value=object())
    monkeypatch.setattr("dojoagents.dojo_sdk.AsyncDojo", constructor)

    result = create_async_dojo(_config(tmp_path))

    assert result is constructor.return_value
    kwargs = constructor.call_args.kwargs
    assert kwargs["online"] is False
    assert kwargs["api_key"] == "test-key"
    assert kwargs["base_url"] == "https://example.invalid"
    assert kwargs["timeout"] == 19
    assert kwargs["max_retries"] == 3
    assert kwargs["offline_config"].cache_dir == str((tmp_path / "sdk-cache").resolve())
    assert kwargs["offline_config"].backend == "modelscope"
    assert kwargs["offline_config"].local_only is True


def test_explicit_writer_and_sync_client_share_the_same_config(tmp_path: Path, monkeypatch) -> None:
    async_constructor = Mock(return_value=object())
    sync_constructor = Mock(return_value=object())
    monkeypatch.setattr("dojoagents.dojo_sdk.AsyncDojo", async_constructor)
    monkeypatch.setattr("dojoagents.dojo_sdk.Dojo", sync_constructor)
    config = _config(tmp_path)

    create_async_dojo(config, online=True)
    create_dojo(config)

    assert async_constructor.call_args.kwargs["online"] is True
    assert sync_constructor.call_args.kwargs["online"] is False
    assert (
        async_constructor.call_args.kwargs["offline_config"].cache_dir
        == sync_constructor.call_args.kwargs["offline_config"].cache_dir
    )
