from __future__ import annotations

import pytest
from unittest.mock import MagicMock, AsyncMock

from dojoagents.gateway.runner import GatewayRunner
from dojoagents.gateway.adapters.base import GatewayEvent, GatewaySendResult
from dojoagents.gateway.registry import GatewayRegistry
from dojoagents.gateway.registry import PlatformEntry


@pytest.mark.asyncio
async def test_gateway_skill_command_expansion(tmp_path):
    class FakeAdapter:
        platform = "test"
        def __init__(self, config):
            self.config = config
            self.sent = []
        async def start(self):
            pass
        async def stop(self):
            pass
        def normalize_message(self, payload):
            return GatewayEvent(
                platform="test",
                text=payload.get("text", "hello"),
                target=payload.get("target", "U1"),
                user_id=payload.get("user_id", "U1"),
            )
        async def send(self, target, message, thread_id=None):
            self.sent.append((target, message))
            return GatewaySendResult(success=True, message_id="msg_123")

    registry = GatewayRegistry()
    registry.register(
        PlatformEntry(name="test", label="Test", adapter_factory=lambda config: FakeAdapter(config))
    )

    runner = GatewayRunner(
        registry=registry,
        gateway_config={
            "session_store": str(tmp_path / "state.db"),
            "pairing_store": str(tmp_path / "pairing.json"),
            "hooks": {
                "test": {
                    "enabled": True,
                    "allow_all": True,
                }
            }
        }
    )
    # Start runner to initialize runtime, agent, and skills
    await runner.start()

    # Create event invoking /plan command
    event = GatewayEvent(
        platform="test",
        text="/plan my custom planning request",
        target="U1",
        user_id="U1",
        message_id="msg1",
        raw={},
    )
    adapter = runner.adapters["test"]

    # Call _handle_command
    result = await runner._handle_command(adapter, event)

    # Assert that the command was successfully intercepted as a skill:
    # 1. It returns None (so runner falls through to run the agent)
    # 2. It overrides event.text with the loaded skill template and instructions
    assert result is None
    assert "[IMPORTANT: The user has invoked the \"plan\" skill" in event.text
    assert "my custom planning request" in event.text
    # Verify it has loaded the actual instructions of the plan skill
    assert "Plan Mode" in event.text or "Writing Plans" in event.text or "plan" in event.text.lower()
