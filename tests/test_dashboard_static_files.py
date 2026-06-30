from fastapi.testclient import TestClient


def test_dashboard_serves_built_favicon(monkeypatch, tmp_path):
    from dojoagents.dashboard import server

    static_dir = tmp_path / "dist"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html></html>", encoding="utf-8")
    (static_dir / "favicon.svg").write_text("<svg></svg>", encoding="utf-8")

    monkeypatch.setenv("DOJO_DASHBOARD_STATIC_DIR", str(static_dir))
    monkeypatch.setattr(server, "setup_frontend_static_files", lambda **_: None)

    runtime = type("FakeRuntime", (), {"config_store": None})()
    response = TestClient(server.create_app(runtime)).get("/favicon.svg")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/svg+xml")
