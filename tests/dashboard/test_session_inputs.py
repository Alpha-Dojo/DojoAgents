from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from dojoagents.config.loader import ConfigStore
from dojoagents.tools.session_input_ingest import (
    ingest_session_input_preview,
    read_session_input_slice,
)
from dojoagents.dashboard.services.session_inputs import (
    list_session_input_files,
    save_session_input_file,
)


def test_save_and_preview_text_input(tmp_path: Path) -> None:
    payload = save_session_input_file(
        tmp_path,
        "sess-in",
        "analysis.py",
        b"def main():\n    return 42\n",
    )
    assert payload["kind"] == "code"
    assert "main" in payload["preview_text"]
    listed = list_session_input_files(tmp_path, "sess-in")
    assert listed["files"][0]["filename"] == "analysis.py"


def test_read_session_input_slice_returns_line_window(tmp_path: Path) -> None:
    target = tmp_path / "sess-in" / "inputs" / "notes.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("line1\nline2\nline3\n", encoding="utf-8")

    payload = read_session_input_slice(target, offset=2, limit=1)

    assert payload["content"] == "line2"
    assert payload["returned_lines"] == 1


def test_ingest_csv_preview(tmp_path: Path) -> None:
    target = tmp_path / "sample.csv"
    target.write_text("ticker,price\nAAPL,100\nMSFT,200\n", encoding="utf-8")

    payload = ingest_session_input_preview(target)

    assert payload["kind"] == "csv"
    assert "AAPL" in payload["preview_text"]


def test_ingest_excel_preview(tmp_path: Path) -> None:
    pytest.importorskip("openpyxl")
    import pandas as pd

    target = tmp_path / "sample.xlsx"
    pd.DataFrame({"ticker": ["AAPL"], "price": [100]}).to_excel(target, index=False)

    payload = ingest_session_input_preview(target)

    assert payload["kind"] == "excel"
    assert "AAPL" in payload["preview_text"]


def test_ingest_pdf_preview(tmp_path: Path) -> None:
    pytest.importorskip("pypdf")
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    buffer = BytesIO()
    writer.write(buffer)
    target = tmp_path / "sample.pdf"
    target.write_bytes(buffer.getvalue())

    payload = ingest_session_input_preview(target)

    assert payload["kind"] == "pdf"
    assert payload["page_count"] == 1


def _make_inputs_client(tmp_path: Path):
    from dojoagents.dashboard.server import create_app

    sessions_root = tmp_path / "strands_sessions"
    cfg_file = tmp_path / "agents.yaml"
    cfg_file.write_text(f"sessions:\n  root: {sessions_root}\n")
    config_store = ConfigStore(path=str(cfg_file))
    runtime = MagicMock()
    runtime.config_store = config_store
    runtime.sessions = MagicMock()
    return TestClient(create_app(runtime)), sessions_root


def test_chat_session_inputs_upload_list_and_reveal(tmp_path: Path, monkeypatch) -> None:
    client, _ = _make_inputs_client(tmp_path)
    files = {"file": ("notes.txt", b"hello inputs", "text/plain")}

    upload_response = client.post("/api/v1/chat/sessions/sess-in/inputs", files=files)
    assert upload_response.status_code == 200
    body = upload_response.json()
    assert body["file"]["filename"] == "notes.txt"
    assert "hello inputs" in body["file"]["preview_text"]

    list_response = client.get("/api/v1/chat/sessions/sess-in/inputs")
    assert list_response.status_code == 200
    assert list_response.json()["files"][0]["filename"] == "notes.txt"

    reveal_calls: list[list[str]] = []

    def fake_run(cmd, check):
        reveal_calls.append(cmd)
        assert check is True

    monkeypatch.setattr("dojoagents.dashboard.services.session_outputs.sys.platform", "darwin")
    monkeypatch.setattr("dojoagents.dashboard.services.session_outputs.subprocess.run", fake_run)

    reveal_response = client.post("/api/v1/chat/sessions/sess-in/inputs/notes.txt/reveal")
    assert reveal_response.status_code == 200
    assert reveal_calls
