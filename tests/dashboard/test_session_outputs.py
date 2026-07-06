from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from dojoagents.config.loader import ConfigStore
from dojoagents.dashboard.services.session_outputs import (
    list_session_output_files,
    resolve_session_output_file,
    reveal_path_in_file_manager,
)
from dojoagents.tools.session_file_tool import write_session_file


def test_list_session_output_files_returns_sorted_files(tmp_path: Path) -> None:
    write_session_file(
        sessions_root=tmp_path,
        session_id="sess-out",
        filename="beta.json",
        content={"a": 1},
        fmt="json",
    )
    write_session_file(
        sessions_root=tmp_path,
        session_id="sess-out",
        filename="alpha.jsonl",
        content=[{"row": 1}],
        fmt="jsonl",
    )

    payload = list_session_output_files(tmp_path, "sess-out")

    assert payload["session_id"] == "sess-out"
    assert payload["output_dir"].endswith("sess-out/outputs")
    assert [item["filename"] for item in payload["files"]] == ["alpha.jsonl", "beta.json"]
    assert all(item["bytes_written"] > 0 for item in payload["files"])
    assert all(item["path"].endswith(item["filename"]) for item in payload["files"])


def test_resolve_session_output_file_rejects_path_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="basename"):
        resolve_session_output_file(tmp_path, "sess-out", "../escape.json")


def test_reveal_path_in_file_manager_invokes_open_on_macos(tmp_path: Path, monkeypatch) -> None:
    target = tmp_path / "demo.json"
    target.write_text("{}", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_run(cmd, check):
        calls.append(cmd)
        assert check is True

    monkeypatch.setattr("dojoagents.dashboard.services.session_outputs.sys.platform", "darwin")
    monkeypatch.setattr("dojoagents.dashboard.services.session_outputs.subprocess.run", fake_run)

    reveal_path_in_file_manager(target)

    assert calls == [["open", "-R", str(target.resolve())]]


def _make_outputs_client(tmp_path: Path):
    from dojoagents.dashboard.server import create_app

    sessions_root = tmp_path / "strands_sessions"
    cfg_file = tmp_path / "agents.yaml"
    cfg_file.write_text(f"sessions:\n  root: {sessions_root}\n")
    config_store = ConfigStore(path=str(cfg_file))
    runtime = MagicMock()
    runtime.config_store = config_store
    runtime.sessions = MagicMock()
    return TestClient(create_app(runtime)), sessions_root


def test_chat_session_outputs_list_and_reveal_routes(tmp_path: Path, monkeypatch) -> None:
    client, sessions_root = _make_outputs_client(tmp_path)
    write_session_file(
        sessions_root=sessions_root,
        session_id="sess-api",
        filename="report.json",
        content={"ok": True},
        fmt="json",
    )

    list_response = client.get("/api/v1/chat/sessions/sess-api/outputs")
    assert list_response.status_code == 200
    body = list_response.json()
    assert body["session_id"] == "sess-api"
    assert body["files"][0]["filename"] == "report.json"

    reveal_calls: list[list[str]] = []

    def fake_run(cmd, check):
        reveal_calls.append(cmd)
        assert check is True

    monkeypatch.setattr("dojoagents.dashboard.services.session_outputs.sys.platform", "darwin")
    monkeypatch.setattr("dojoagents.dashboard.services.session_outputs.subprocess.run", fake_run)

    reveal_response = client.post("/api/v1/chat/sessions/sess-api/outputs/report.json/reveal")
    assert reveal_response.status_code == 200
    assert reveal_response.json()["ok"] is True
    assert reveal_calls


def test_chat_session_outputs_reveal_missing_file_returns_404(tmp_path: Path) -> None:
    client, _ = _make_outputs_client(tmp_path)

    response = client.post("/api/v1/chat/sessions/sess-missing/outputs/missing.json/reveal")

    assert response.status_code == 404
    assert "error" in response.json()
