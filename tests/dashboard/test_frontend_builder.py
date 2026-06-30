from dojoagents.dashboard.frontend_builder import _frontend_rebuild_forced


def test_frontend_rebuild_forced(monkeypatch) -> None:
    monkeypatch.delenv("DOJO_DASHBOARD_REBUILD_FRONTEND", raising=False)
    assert _frontend_rebuild_forced() is False

    for value in ("1", "true", "TRUE", "yes"):
        monkeypatch.setenv("DOJO_DASHBOARD_REBUILD_FRONTEND", value)
        assert _frontend_rebuild_forced() is True

    monkeypatch.setenv("DOJO_DASHBOARD_REBUILD_FRONTEND", "0")
    assert _frontend_rebuild_forced() is False
