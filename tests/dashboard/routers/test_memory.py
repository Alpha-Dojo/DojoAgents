from __future__ import annotations

import stat
from types import SimpleNamespace
from unittest.mock import MagicMock

import yaml
from fastapi.testclient import TestClient

from dojoagents.config.loader import ConfigStore
from dojoagents.dashboard.server import create_app


def _make_client(tmp_path, generated_skill_dir) -> TestClient:
    config_path = tmp_path / "agents.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "memory": {
                    "provider": "skill_summary",
                    "generated_skill_dir": str(generated_skill_dir),
                }
            }
        ),
        encoding="utf-8",
    )
    runtime = SimpleNamespace(
        agent=None,
        config_store=ConfigStore(path=str(config_path)),
        extensions=MagicMock(),
        scheduler=MagicMock(),
    )
    runtime.extensions.status.return_value = []
    runtime.scheduler.list_jobs.return_value = []
    return TestClient(create_app(runtime))


def test_clear_generated_memory_removes_contents_and_keeps_directory(tmp_path):
    generated_dir = tmp_path / "generated"
    skill_dir = generated_dir / "generated-session"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("memory", encoding="utf-8")
    (generated_dir / ".skills_cache.json").write_text("{}", encoding="utf-8")
    client = _make_client(tmp_path, generated_dir)

    response = client.delete("/api/v1/memory/generated-skills")

    assert response.status_code == 200
    assert response.json() == {
        "ok": True,
        "directory": str(generated_dir.resolve()),
        "deleted_count": 2,
    }
    assert generated_dir.is_dir()
    assert list(generated_dir.iterdir()) == []


def test_clear_generated_memory_is_idempotent_when_directory_is_missing(tmp_path):
    generated_dir = tmp_path / "missing" / "generated"
    client = _make_client(tmp_path, generated_dir)

    response = client.delete("/api/v1/memory/generated-skills")

    assert response.status_code == 200
    assert response.json()["deleted_count"] == 0
    assert generated_dir.is_dir()


def test_clear_generated_memory_unlinks_symlink_without_following_it(tmp_path):
    generated_dir = tmp_path / "generated"
    generated_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    protected = outside / "keep.txt"
    protected.write_text("keep", encoding="utf-8")
    (generated_dir / "linked").symlink_to(outside, target_is_directory=True)
    client = _make_client(tmp_path, generated_dir)

    response = client.delete("/api/v1/memory/generated-skills")

    assert response.status_code == 200
    assert response.json()["deleted_count"] == 1
    assert protected.read_text(encoding="utf-8") == "keep"


def test_clear_generated_memory_removes_read_only_tree(tmp_path):
    generated_dir = tmp_path / "generated"
    skill_dir = generated_dir / "generated-read-only"
    skill_dir.mkdir(parents=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text("memory", encoding="utf-8")
    skill_file.chmod(stat.S_IRUSR)
    skill_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
    generated_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)
    client = _make_client(tmp_path, generated_dir)

    response = client.delete("/api/v1/memory/generated-skills")

    assert response.status_code == 200
    assert response.json()["deleted_count"] == 1
    assert list(generated_dir.iterdir()) == []


def test_clear_generated_memory_rejects_home_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "dojoagents.dashboard.services.generated_memory_service.Path.home",
        lambda: tmp_path,
    )
    client = _make_client(tmp_path, tmp_path)

    response = client.delete("/api/v1/memory/generated-skills")

    assert response.status_code == 400
    assert "unsafe generated memory path" in response.json()["error"]


def test_clear_generated_memory_without_config_store_returns_503():
    runtime = SimpleNamespace(
        agent=None,
        config_store=None,
        extensions=MagicMock(),
        scheduler=MagicMock(),
    )
    runtime.extensions.status.return_value = []
    runtime.scheduler.list_jobs.return_value = []
    client = TestClient(create_app(runtime))

    response = client.delete("/api/v1/memory/generated-skills")

    assert response.status_code == 503
