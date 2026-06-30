import pytest
from fastapi.testclient import TestClient


@pytest.mark.asyncio
async def test_scheduler_runs_job_through_runtime_and_saves_output(tmp_path):
    from dojoagents.agent.models import AgentResponse
    from dojoagents.cron.jobs import JobStore, ScheduledJob
    from dojoagents.cron.scheduler import SchedulerService
    from dojoagents.quant.context import QuantContext

    class FakeAgent:
        async def run(self, request):
            assert request.quant == QuantContext(market="crypto", symbols=["BTC-USD"], timeframe="1d")
            return AgentResponse(content="daily brief", session_id=request.session_id)

    class FakeRuntime:
        agent = FakeAgent()

    class FakeRuntimeFactory:
        def for_profile(self, profile):
            assert profile == "default"
            return FakeRuntime()

    store = JobStore(tmp_path / "jobs.yaml", output_dir=tmp_path / "runs")
    store.add(
        ScheduledJob(
            id="daily-btc",
            name="Daily BTC",
            schedule={"kind": "cron", "expr": "0 8 * * 1-5"},
            prompt="Write a daily BTC brief.",
            quant=QuantContext(market="crypto", symbols=["BTC-USD"], timeframe="1d"),
        )
    )

    service = SchedulerService(runtime_factory=FakeRuntimeFactory(), job_store=store)
    run = await service.run_job("daily-btc")

    assert run.job_id == "daily-btc"
    assert run.output == "daily brief"
    assert (tmp_path / "runs" / "daily-btc").exists()


def test_dashboard_exposes_health_jobs_extensions_and_chat(tmp_path):
    from dojoagents.agent.models import AgentResponse
    from dojoagents.cron.jobs import JobStore, ScheduledJob
    from dojoagents.dashboard.server import create_app
    from dojoagents.dojo_extensions.registry import DojoExtensionRegistry

    class FakeAgent:
        async def run(self, request):
            return AgentResponse(content=f"reply:{request.message}", session_id=request.session_id)

    class FakeRuntime:
        def __init__(self):
            self.agent = FakeAgent()
            self.scheduler = JobStore(tmp_path / "jobs.yaml", output_dir=tmp_path / "runs")
            self.scheduler.add(
                ScheduledJob(
                    id="job-1",
                    name="Job 1",
                    schedule={"kind": "interval", "minutes": 60},
                    prompt="Run job",
                )
            )
            from dojoagents.dojo_extensions.research import DojoResearchExtension

            self.extensions = DojoExtensionRegistry()
            self.extensions.register(DojoResearchExtension())
            self.config_store = None

    client = TestClient(create_app(FakeRuntime()))

    assert client.get("/api/health").json()["ok"] is True
    assert client.get("/api/jobs").json()[0]["id"] == "job-1"
    assert client.get("/api/extensions").json()[0]["name"] == "dojo_research"
    response = client.post(
        "/api/chat",
        json={"message": "hi", "user_id": "u", "session_id": "s", "channel": "dashboard"},
    )
    assert response.json()["content"] == "reply:hi"


def test_gateway_registry_creates_registered_adapter():
    from dojoagents.gateway.registry import GatewayRegistry, PlatformEntry

    class Adapter:
        def __init__(self, config):
            self.config = config

    registry = GatewayRegistry()
    registry.register(
        PlatformEntry(
            name="telegram",
            label="Telegram",
            adapter_factory=lambda config: Adapter(config),
            required_env=["TELEGRAM_BOT_TOKEN"],
        )
    )

    adapter = registry.create_adapter("telegram", {"enabled": True})
    assert isinstance(adapter, Adapter)
    assert registry.status()[0]["name"] == "telegram"


def test_runtime_wires_default_components_from_config(tmp_path):
    from dojoagents.agent.runtime import Runtime
    from dojoagents.config.loader import ConfigStore

    config_path = tmp_path / "agents.yaml"
    config_path.write_text(
        """
llm_provider:
  providers:
    openai:
      model: test-model
agent:
  max_iterations: 2
""",
        encoding="utf-8",
    )

    runtime = Runtime.from_config_store(ConfigStore(config_path))

    assert runtime.config.agent.max_iterations == 2
    assert runtime.agent.config.model == "test-model"
    assert runtime.extensions.status()[0]["name"] == "dojo_research"


def test_runtime_starts_without_llm_provider_config(tmp_path):
    from dojoagents.agent.providers import UnconfiguredLLMProvider
    from dojoagents.agent.runtime import Runtime
    from dojoagents.config.loader import ConfigStore

    config_path = tmp_path / "agents.yaml"
    config_path.write_text("agent:\n  max_iterations: 2\n", encoding="utf-8")

    runtime = Runtime.from_config_store(ConfigStore(config_path))

    assert runtime.config.agent.model is None
    assert isinstance(runtime.agent.llm_provider, UnconfiguredLLMProvider)
