import subprocess
from pathlib import Path


def test_dashboard_builds_frontend_before_starting_server(monkeypatch):
    from dojoagents.cli import main as cli_main

    calls = []
    runtime = object()
    app = object()

    monkeypatch.setattr(
        cli_main.subprocess,
        "run",
        lambda command, *, cwd, check: calls.append(
            ("build", command, cwd, check)
        ),
    )
    monkeypatch.setattr(
        cli_main.Runtime,
        "from_default_config",
        lambda: calls.append(("runtime",)) or runtime,
    )
    monkeypatch.setattr(
        cli_main,
        "create_dashboard_app",
        lambda received_runtime: calls.append(("app", received_runtime)) or app,
    )
    monkeypatch.setattr(
        cli_main.uvicorn,
        "run",
        lambda received_app, *, host, port: calls.append(
            ("uvicorn", received_app, host, port)
        ),
    )

    result = cli_main.main(
        ["dashboard", "--host", "127.0.0.2", "--port", "9000"]
    )

    expected_web_dir = (
        Path(cli_main.__file__).resolve().parents[1] / "dashboard" / "web"
    )
    assert result == 0
    assert calls == [
        ("build", ["npm", "run", "build"], expected_web_dir, True),
        ("runtime",),
        ("app", runtime),
        ("uvicorn", app, "127.0.0.2", 9000),
    ]


def test_dashboard_starts_with_existing_assets_when_frontend_build_fails(
    monkeypatch,
):
    from dojoagents.cli import main as cli_main

    calls = []
    runtime = object()
    app = object()

    def fail_build():
        raise subprocess.CalledProcessError(1, ["npm", "run", "build"])

    monkeypatch.setattr(cli_main, "_build_dashboard_frontend", fail_build)
    monkeypatch.setattr(
        cli_main.LOGGER,
        "exception",
        lambda message: calls.append(("log", message)),
    )
    monkeypatch.setattr(
        cli_main.Runtime,
        "from_default_config",
        lambda: calls.append(("runtime",)) or runtime,
    )
    monkeypatch.setattr(
        cli_main,
        "create_dashboard_app",
        lambda received_runtime: calls.append(("app", received_runtime)) or app,
    )
    monkeypatch.setattr(
        cli_main.uvicorn,
        "run",
        lambda received_app, *, host, port: calls.append(
            ("uvicorn", received_app, host, port)
        ),
    )

    result = cli_main.main(["dashboard"])

    assert result == 0
    assert calls == [
        (
            "log",
            "Dashboard frontend build failed; starting with the existing built assets",
        ),
        ("runtime",),
        ("app", runtime),
        ("uvicorn", app, "127.0.0.1", 8765),
    ]
