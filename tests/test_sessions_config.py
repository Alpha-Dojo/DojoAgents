from dojoagents.config.loader import _to_config
from dojoagents.config.models import AgentsConfig


def test_tasks_config_defaults_include_output_root():
    cfg = AgentsConfig()

    assert cfg.tasks.output_root == "~/.dojo/tasks/outputs"


def test_sessions_config_defaults_are_runtime_level():
    cfg = AgentsConfig()

    assert cfg.sessions.enabled is True
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
