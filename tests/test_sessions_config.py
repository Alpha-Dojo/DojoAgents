import pytest

from dojoagents.config.loader import ConfigStore, _to_config
from dojoagents.config.models import AgentsConfig


def test_tasks_config_defaults_include_output_root():
    cfg = AgentsConfig()

    assert cfg.tasks.output_root == "~/.dojo/tasks/outputs"


def test_sessions_config_defaults_are_runtime_level():
    cfg = AgentsConfig()

    assert cfg.sessions.enabled is True
    assert cfg.sessions.store.provider == "file"
    assert cfg.sessions.blob_store.provider == "file"
    assert cfg.sessions.runtime.require_user_id is True
    assert cfg.sessions.runtime.lease_seconds == 90
    assert cfg.sessions.provider == "dojo_repository"
    assert cfg.sessions.root == "~/.dojo/agents/strands_sessions"
    assert cfg.sessions.agent_id == "dojo-agent"
    assert cfg.sessions.sync_memory is True


def test_sessions_config_loads_from_raw_config():
    cfg = _to_config(
        {
            "sessions": {
                "enabled": False,
                "provider": "strands_file",
                "root": "/tmp/dojo-sessions",
                "agent_id": "custom-agent",
                "persist_openai_history": False,
                "sync_memory": False,
                "export_default_dir": "/tmp/exports",
            }
        }
    )

    assert cfg.sessions.enabled is False
    assert cfg.sessions.provider == "strands_file"
    assert cfg.sessions.root == "/tmp/dojo-sessions"
    assert cfg.sessions.agent_id == "custom-agent"
    assert cfg.sessions.persist_openai_history is False
    assert cfg.sessions.sync_memory is False
    assert cfg.sessions.export_default_dir == "/tmp/exports"
    assert cfg.sessions.store.provider == "file"
    assert cfg.sessions.store.options["root"] == "/tmp/dojo-sessions"
    assert cfg.sessions.store.options["compatibility_mode"] == "strands_file"
    assert cfg.sessions.blob_store.options["root"] == "/tmp/dojo-sessions"


def test_sessions_config_loads_nested_store_runtime_and_expands_secrets(tmp_path, monkeypatch):
    monkeypatch.setenv("DOJO_SESSION_DSN", "postgresql://user:secret@db/sessions")
    monkeypatch.setenv("DOJO_BLOB_SECRET", "blob-secret")
    path = tmp_path / "agents.yaml"
    path.write_text(
        """
sessions:
  enabled: true
  store:
    provider: postgresql
    factory: project.sessions:create_store
    options:
      dsn: ${DOJO_SESSION_DSN}
  blob_store:
    provider: s3
    factory: project.blobs:create_store
    options:
      secret_key: ${DOJO_BLOB_SECRET}
  runtime:
    require_user_id: true
    lease_seconds: 120
    heartbeat_seconds: 20
    event_batch_size: 50
""".strip(),
        encoding="utf-8",
    )

    store = ConfigStore(path)
    sessions = store.snapshot().sessions

    assert sessions.store.provider == "postgresql"
    assert sessions.store.factory == "project.sessions:create_store"
    assert sessions.store.options["dsn"].endswith("@db/sessions")
    assert sessions.blob_store.provider == "s3"
    assert sessions.runtime.lease_seconds == 120
    redacted = store.redacted()["sessions"]
    assert redacted["store"]["options"]["dsn"] == "***"
    assert redacted["blob_store"]["options"]["secret_key"] == "***"


def test_sessions_disabled_is_preserved_without_constructing_a_fallback_session():
    cfg = _to_config({"sessions": {"enabled": False}})

    assert cfg.sessions.enabled is False


@pytest.mark.parametrize(
    "payload",
    [
        {"sessions": {"mystery": True}},
        {"sessions": {"store": {"provider": "file", "mystery": True}}},
        {"sessions": {"runtime": {"lease_seconds": 90, "mystery": True}}},
    ],
)
def test_sessions_config_rejects_unknown_keys(payload):
    with pytest.raises(ValueError, match="unknown"):
        _to_config(payload)
