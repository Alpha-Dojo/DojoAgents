from __future__ import annotations

import asyncio
import base64
import json
from unittest.mock import MagicMock

from fastapi.testclient import TestClient


class FakeBackgroundAgent:
    def __init__(self, *, hold: bool = False) -> None:
        self._hold = hold
        self.cancelled = False

    async def run(self, request, *, event_sink=None):
        from dojoagents.agent.models import AgentResponse

        if event_sink is not None:
            event_sink.phase("planning")
            event_sink.tool_start(
                call_id="call-1",
                tool="portfolio_write_create",
                arguments={"name": "Quality"},
            )
            event_sink.tool_result(
                call_id="call-1",
                tool="portfolio_write_create",
                ok=True,
                content="created",
                latency_ms=12,
                data={"portfolio_id": "p-1", "name": "Quality"},
                viz_blocks=[
                    {
                        "id": "viz-portfolio",
                        "kind": "table",
                        "title": "Portfolio",
                        "subtitle": None,
                        "source_tool": "agent_viz_build",
                        "truncated": False,
                        "payload": {"rows": [{"name": "Quality"}]},
                    }
                ],
                resource_changes=[{"resource": "portfolio", "action": "create", "portfolio_id": "p-1"}],
            )
            if self._hold:
                try:
                    await asyncio.sleep(60)
                except asyncio.CancelledError:
                    self.cancelled = True
                    raise
            event_sink.phase("answering")
            event_sink.delta("done")
            event_sink.done(
                model_id="gpt-4.1",
                tool_trace=[
                    {
                        "call_id": "call-1",
                        "tool": "portfolio_write_create",
                        "arguments": {"name": "Quality"},
                        "ok": True,
                    }
                ],
                tool_steps=1,
            )
        return AgentResponse(
            content="done",
            session_id=request.session_id,
            metadata={"usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
        )


class FakeRuntime:
    def __init__(self, agent=None):
        self.agent = agent or FakeBackgroundAgent()
        self.config_store = None
        self.extensions = MagicMock()
        self.extensions.status = MagicMock(return_value=[])
        self.scheduler = MagicMock()
        self.scheduler.list_jobs = MagicMock(return_value=[])
        from dojoagents.tasks.activator import TaskActivator
        from dojoagents.tasks.command_router import CommandRouter
        from dojoagents.tasks.manager import TaskPromptManager
        from dojoagents.tasks.pipeline import PipelineRunner
        from dojoagents.tasks.schema_validator import TaskOutputValidator
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[1]
        self.task_manager = TaskPromptManager(
            task_dirs=[repo_root / "dojoagents" / "tasks" / "built_in"],
            pipeline_dirs=[repo_root / "dojoagents" / "tasks" / "pipelines"],
        )
        self.task_activator = TaskActivator(
            manager=self.task_manager,
            sessions_root="/tmp",
            task_output_root="/tmp/task-outputs",
            auto_detect=False,
        )
        self.command_router = CommandRouter(
            manager=self.task_manager,
            activator=self.task_activator,
            skill_manager=None,
        )
        self.pipeline_runner = PipelineRunner(
            manager=self.task_manager,
            activator=self.task_activator,
            validator=TaskOutputValidator(self.task_manager),
            task_output_root="/tmp/task-outputs",
        )


def _make_app(agent=None):
    from dojoagents.dashboard.server import create_app
    from dojoagents.dashboard.agent_runs import AgentRunManager

    app = create_app(FakeRuntime(agent))
    app.state.agent_run_manager = AgentRunManager()
    return app


def _parse_sse_events(response) -> list[dict]:
    lines = [line.strip() for line in response.iter_lines() if line.strip()]
    payloads: list[dict] = []
    for line in lines:
        if not line.startswith("data: ") or "[DONE]" in line:
            continue
        payloads.append(json.loads(line.replace("data: ", "", 1)))
    return payloads


def test_create_background_run_and_fetch_status_and_events():
    client = TestClient(_make_app())

    response = client.post(
        "/api/chat/runs",
        json={
            "model": "gpt-4.1",
            "messages": [{"role": "user", "content": "build portfolio"}],
            "metadata": {"session_id": "sess-run"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["run_id"]
    assert body["session_id"] == "sess-run"

    status_response = client.get(f"/api/chat/runs/{body['run_id']}")
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["run_id"] == body["run_id"]
    assert status["session_id"] == "sess-run"
    assert status["status"] in {"running", "done"}

    with client.stream("GET", f"/api/chat/runs/{body['run_id']}/events?cursor=0") as events_response:
        assert events_response.status_code == 200
        payloads = _parse_sse_events(events_response)

    assert [payload["type"] for payload in payloads][-1] == "done"
    assert any(payload["type"] == "tool_start" and payload["call_id"] == "call-1" for payload in payloads)
    assert any(payload["type"] == "tool_result" and payload["call_id"] == "call-1" for payload in payloads)
    tool_result = next(payload for payload in payloads if payload["type"] == "tool_result")
    done = next(payload for payload in payloads if payload["type"] == "done")
    assert tool_result["viz_blocks"][0]["kind"] == "table"
    assert done["tool_trace"][0]["arguments"] == {"name": "Quality"}


def test_background_run_events_respect_cursor():
    client = TestClient(_make_app())

    create_response = client.post(
        "/api/chat/runs",
        json={
            "model": "gpt-4.1",
            "messages": [{"role": "user", "content": "build portfolio"}],
            "metadata": {"session_id": "sess-cursor"},
        },
    )
    run_id = create_response.json()["run_id"]

    with client.stream("GET", f"/api/chat/runs/{run_id}/events?cursor=0") as first_response:
        first_payloads = _parse_sse_events(first_response)
    assert len(first_payloads) >= 4

    with client.stream("GET", f"/api/chat/runs/{run_id}/events?cursor=2") as second_response:
        replay_payloads = _parse_sse_events(second_response)

    assert replay_payloads
    assert all(payload["seq"] > 2 for payload in replay_payloads)
    assert replay_payloads[0]["seq"] == 3


def test_cancel_background_run_returns_cancelled_status():
    agent = FakeBackgroundAgent(hold=True)
    client = TestClient(_make_app(agent))

    create_response = client.post(
        "/api/chat/runs",
        json={
            "model": "gpt-4.1",
            "messages": [{"role": "user", "content": "long task"}],
            "metadata": {"session_id": "sess-cancel"},
        },
    )
    run_id = create_response.json()["run_id"]

    cancel_response = client.post(f"/api/chat/runs/{run_id}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.json() == {"cancelled": True}

    status_response = client.get(f"/api/chat/runs/{run_id}")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "cancelled"
    assert agent.cancelled is True


def test_background_run_preprocesses_pipeline_command():
    captured: dict = {}

    class CapturingAgent(FakeBackgroundAgent):
        async def run(self, request, *, event_sink=None):
            captured["active_task"] = request.metadata.get("active_task")
            captured["pipeline"] = request.metadata.get("pipeline")
            return await super().run(request, event_sink=event_sink)

    client = TestClient(_make_app(CapturingAgent()))

    response = client.post(
        "/api/chat/runs",
        json={
            "model": "gpt-4.1",
            "messages": [{"role": "user", "content": "/pipeline daily-market-events 2026-07-03"}],
            "metadata": {"session_id": "sess-pipeline"},
        },
    )
    assert response.status_code == 200
    run_id = response.json()["run_id"]

    with client.stream("GET", f"/api/chat/runs/{run_id}/events?cursor=0") as events_response:
        _parse_sse_events(events_response)

    active_task = captured.get("active_task")
    pipeline = captured.get("pipeline")
    assert isinstance(active_task, dict)
    assert active_task["task_id"] == "sector-attribution"
    assert active_task["params"]["trading_date"] == "2026-07-03"
    assert isinstance(pipeline, dict)
    assert pipeline["id"] == "daily-market-events"
    assert pipeline["step"] == 1


def test_create_background_run_rejects_unsupported_image_input():
    from dojoagents.agent.model_context import ModelContextInfo
    from dojoagents.config.models import LLMProviderConfig

    class FakeModelContextRegistry:
        async def resolve_info(self, provider_name, provider_cfg, *, client=None):
            assert provider_name == "zhipu"
            assert provider_cfg.author == "z-ai"
            assert provider_cfg.model == "glm-5.2"
            return ModelContextInfo(
                context_window=1048576,
                input_modalities=("text",),
                output_modalities=("text",),
                canonical_slug="z-ai/glm-5.2-20260616",
                provider_model_id="z-ai/glm-5.2",
                author="z-ai",
                slug="glm-5.2",
            )

    agent = FakeBackgroundAgent()
    agent.provider_config = LLMProviderConfig(model="glm-5.2", author="z-ai")
    agent.model_context_registry = FakeModelContextRegistry()
    agent.llm_provider = type("FakeProvider", (), {"name": "zhipu"})()

    client = TestClient(_make_app(agent))
    data_url = "data:image/png;base64," + base64.b64encode(b"abc").decode("ascii")

    response = client.post(
        "/api/chat/runs",
        json={
            "model": "zhipu",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "look at this"},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            ],
            "metadata": {"session_id": "sess-image"},
        },
    )

    assert response.status_code == 422
    assert "does not support input modalities: image" in response.json()["error"]
