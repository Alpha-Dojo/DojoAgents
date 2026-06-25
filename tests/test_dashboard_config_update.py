"""Tests for PUT /api/config — editable settings endpoint (TDD)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import yaml
from fastapi.testclient import TestClient

from dojoagents.config.loader import ConfigStore
from dojoagents.dashboard.server import create_app

# ── Helpers ──────────────────────────────────────────────────────────


class FakeAgent:
    async def run(self, request):
        from dojoagents.agent.models import AgentResponse

        return AgentResponse(content="ok", session_id="s")


def _make_runtime_with_config(tmp_path: Path, initial: dict | None = None):
    """Create a FakeRuntime backed by a real ConfigStore on disk."""
    cfg_file = tmp_path / "agents.yaml"
    if initial is not None:
        cfg_file.write_text(yaml.safe_dump(initial), encoding="utf-8")

    store = ConfigStore(path=str(cfg_file))

    class FakeRuntime:
        def __init__(self):
            self.agent = FakeAgent()
            self.config_store = store
            self.extensions = MagicMock()
            self.extensions.status = MagicMock(return_value=[])
            self.scheduler = MagicMock()
            self.scheduler.list_jobs = MagicMock(return_value=[])

    return FakeRuntime(), cfg_file


def _make_runtime_no_config():
    """Runtime without config_store."""

    class FakeRuntime:
        def __init__(self):
            self.agent = FakeAgent()
            self.config_store = None
            self.extensions = MagicMock()
            self.extensions.status = MagicMock(return_value=[])
            self.scheduler = MagicMock()
            self.scheduler.list_jobs = MagicMock(return_value=[])

    return FakeRuntime()


# ── Tests ────────────────────────────────────────────────────────────


def test_put_config_saves_and_returns_updated(tmp_path):
    """PUT /api/config deep-merges payload into YAML and returns updated config."""
    runtime, cfg_file = _make_runtime_with_config(
        tmp_path,
        {
            "version": 1,
            "logging": {"level": "INFO"},
        },
    )
    app = create_app(runtime)
    client = TestClient(app)

    resp = client.put("/api/config", json={"logging": {"level": "DEBUG"}})
    assert resp.status_code == 200

    body = resp.json()
    # The returned config should reflect the change
    assert body["logging"]["level"] == "DEBUG"

    # Verify the YAML file was updated on disk
    saved = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
    assert saved["logging"]["level"] == "DEBUG"
    # Original top-level keys preserved
    assert saved["version"] == 1


def test_put_config_nested_agent_fields(tmp_path):
    """PUT merges nested agent config correctly."""
    runtime, _ = _make_runtime_with_config(
        tmp_path,
        {
            "version": 1,
            "agent": {"max_iterations": 8, "max_tool_workers": 4},
        },
    )
    app = create_app(runtime)
    client = TestClient(app)

    resp = client.put("/api/config", json={"agent": {"max_iterations": 20}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["agent"]["max_iterations"] == 20
    # Other agent fields preserved from defaults
    assert body["agent"]["max_tool_workers"] == 4


def test_put_config_empty_body_no_change(tmp_path):
    """PUT with empty body returns current config without modifications."""
    runtime, cfg_file = _make_runtime_with_config(
        tmp_path,
        {
            "version": 1,
            "logging": {"level": "WARNING"},
        },
    )
    app = create_app(runtime)
    client = TestClient(app)

    resp = client.put("/api/config", json={})
    assert resp.status_code == 200
    body = resp.json()
    assert body["logging"]["level"] == "WARNING"


def test_put_config_no_config_store_returns_503():
    """PUT returns 503 when runtime has no config_store."""
    runtime = _make_runtime_no_config()
    app = create_app(runtime)
    client = TestClient(app)

    resp = client.put("/api/config", json={"logging": {"level": "DEBUG"}})
    assert resp.status_code == 503


def test_put_config_permission_denied_returns_403(tmp_path):
    """PUT returns a clear 403 when the config file cannot be written."""
    runtime, _ = _make_runtime_with_config(tmp_path, {"version": 1})
    runtime.config_store.save_raw = MagicMock(side_effect=PermissionError("denied"))
    app = create_app(runtime)
    client = TestClient(app)

    resp = client.put("/api/config", json={"logging": {"level": "DEBUG"}})

    assert resp.status_code == 403
    body = resp.json()
    assert "Configuration file is not writable" in body["error"]


def test_put_config_redacts_api_keys(tmp_path):
    """PUT response redacts sensitive api_key values."""
    runtime, _ = _make_runtime_with_config(
        tmp_path,
        {
            "version": 1,
            "llm_provider": {
                "default": "openai",
                "providers": {
                    "openai": {
                        "model": "gpt-4.1",
                        "api_key": "sk-secret-123",
                    }
                },
            },
        },
    )
    app = create_app(runtime)
    client = TestClient(app)

    resp = client.put("/api/config", json={"logging": {"level": "INFO"}})
    assert resp.status_code == 200
    body = resp.json()
    provider = body["llm_provider"]["providers"]["openai"]
    assert provider["api_key"] == "***"


def test_put_config_invalid_json_returns_422(tmp_path):
    """PUT with non-JSON content-type returns 422."""
    runtime, _ = _make_runtime_with_config(tmp_path, {"version": 1})
    app = create_app(runtime)
    client = TestClient(app)

    resp = client.put("/api/config", content="not json", headers={"Content-Type": "text/plain"})
    assert resp.status_code == 422


def test_put_config_multiple_sections(tmp_path):
    """PUT can update multiple top-level sections at once."""
    runtime, _ = _make_runtime_with_config(
        tmp_path,
        {
            "version": 1,
            "logging": {"level": "INFO"},
            "scheduler": {"enabled": True, "timezone": "Asia/Shanghai"},
        },
    )
    app = create_app(runtime)
    client = TestClient(app)

    resp = client.put(
        "/api/config",
        json={
            "logging": {"level": "ERROR"},
            "scheduler": {"timezone": "UTC"},
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["logging"]["level"] == "ERROR"
    assert body["scheduler"]["timezone"] == "UTC"
    assert body["scheduler"]["enabled"] is True  # preserved


def test_put_config_updates_web_tool_settings(tmp_path):
    """PUT can update nested tools.web settings and preserve sibling sandbox config."""
    runtime, _ = _make_runtime_with_config(
        tmp_path,
        {
            "version": 1,
            "tools": {
                "sandbox": {"allow_network": False, "timeout_seconds": 120},
                "web": {"search_backend": "ddgs", "extract_backend": "firecrawl"},
            },
        },
    )
    app = create_app(runtime)
    client = TestClient(app)

    resp = client.put(
        "/api/config",
        json={
            "tools": {
                "web": {
                    "search_backend": "tavily",
                    "summary_threshold_chars": 2400,
                }
            }
        },
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["tools"]["web"]["search_backend"] == "tavily"
    assert body["tools"]["web"]["extract_backend"] == "firecrawl"
    assert body["tools"]["web"]["summary_threshold_chars"] == 2400
    assert body["tools"]["sandbox"]["timeout_seconds"] == 120


def test_get_config_still_works_after_put(tmp_path):
    """GET /api/config reflects changes made by PUT."""
    runtime, _ = _make_runtime_with_config(
        tmp_path,
        {
            "version": 1,
            "logging": {"level": "INFO"},
        },
    )
    app = create_app(runtime)
    client = TestClient(app)

    # PUT change
    resp = client.put("/api/config", json={"logging": {"level": "DEBUG"}})
    assert resp.status_code == 200

    # GET should reflect the change
    resp = client.get("/api/config")
    assert resp.status_code == 200
    assert resp.json()["logging"]["level"] == "DEBUG"


def test_agent_models_reflect_configured_llm_providers(tmp_path):
    """GET /api/v1/agent/models derives selectable models from llm_provider.providers."""
    runtime, _ = _make_runtime_with_config(
        tmp_path,
        {
            "version": 1,
            "llm_provider": {
                "default": "deepseek",
                "providers": {
                    "openai": {
                        "model": "gpt-4.1",
                        "base_url": "https://api.openai.com/v1",
                        "api_key_env": "OPENAI_API_KEY",
                    },
                    "deepseek": {
                        "model": "deepseek-chat",
                        "base_url": "https://api.deepseek.com/v1",
                        "api_key_env": "DEEPSEEK_API_KEY",
                    },
                },
            },
        },
    )
    app = create_app(runtime)
    client = TestClient(app)

    resp = client.get("/api/v1/agent/models")

    assert resp.status_code == 200
    body = resp.json()
    assert body["default_model_id"] == "deepseek"
    assert body["agent_ready"] is True
    assert body["models"] == [
        {
            "id": "openai",
            "label": "OpenAI · gpt-4.1",
            "provider": "openai",
            "model": "gpt-4.1",
            "available": True,
            "unavailable_reason": None,
        },
        {
            "id": "deepseek",
            "label": "DeepSeek · deepseek-chat",
            "provider": "deepseek",
            "model": "deepseek-chat",
            "available": True,
            "unavailable_reason": None,
        },
    ]


def test_put_config_default_provider_updates_agent_model(tmp_path):
    """PUT /api/config keeps agent.model aligned with the selected default provider."""
    runtime, _ = _make_runtime_with_config(
        tmp_path,
        {
            "version": 1,
            "llm_provider": {
                "default": "openai",
                "providers": {
                    "openai": {"model": "gpt-4.1", "api_key_env": "OPENAI_API_KEY"},
                    "deepseek": {"model": "deepseek-chat", "api_key_env": "DEEPSEEK_API_KEY"},
                },
            },
            "agent": {"model": "gpt-4.1", "max_iterations": 8},
        },
    )
    app = create_app(runtime)
    client = TestClient(app)

    resp = client.put("/api/config", json={"llm_provider": {"default": "deepseek"}})

    assert resp.status_code == 200
    body = resp.json()
    assert body["llm_provider"]["default"] == "deepseek"
    assert body["agent"]["model"] == "deepseek-chat"
