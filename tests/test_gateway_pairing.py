import json
import time
import pytest
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock

from dojoagents.gateway.pairing import PairingStore
from dojoagents.gateway.runner import GatewayRunner
from dojoagents.gateway.adapters.base import GatewayEvent, GatewaySendResult
from dojoagents.gateway.registry import GatewayRegistry
from dojoagents.gateway.registry import PlatformEntry

def test_pairing_store_lifecycle(tmp_path):
    store_file = tmp_path / "pairing.json"
    store = PairingStore(filepath=str(store_file))

    # Test initial state
    assert not store.is_approved("slack", "user_1")
    assert len(store.list_pending("slack")) == 0

    # Test generating code
    code = store.generate_code("slack", "user_1", "User One")
    assert len(code) == 8
    assert isinstance(code, str)
    
    pending = store.list_pending("slack")
    assert len(pending) == 1
    assert pending[0]["user_id"] == "user_1"
    assert pending[0]["code"] == code

    # Test approving code
    success = store.approve_code("slack", code)
    assert success is True
    assert store.is_approved("slack", "user_1")
    assert len(store.list_pending("slack")) == 0

    # Test persistence by reload
    store2 = PairingStore(filepath=str(store_file))
    assert store2.is_approved("slack", "user_1")

def test_pairing_store_rate_limit(tmp_path):
    store_file = tmp_path / "pairing.json"
    store = PairingStore(filepath=str(store_file))

    # Generate first code
    store.generate_code("slack", "user_1", "User One")

    # Second generate code within 10 minutes should fail
    with pytest.raises(ValueError, match="Rate limit exceeded"):
        store.generate_code("slack", "user_1", "User One")

    # Mocks time to be 11 minutes later
    original_time = time.time
    try:
        time.time = lambda: original_time() + 660
        code = store.generate_code("slack", "user_1", "User One")
        assert len(code) == 8
    finally:
        time.time = original_time

def test_pairing_store_brute_force_lockout(tmp_path):
    store_file = tmp_path / "pairing.json"
    store = PairingStore(filepath=str(store_file))

    # Generate a valid code
    code = store.generate_code("slack", "user_1", "User One")

    # Fail validation 4 times
    for _ in range(4):
        assert store.approve_code("slack", "WRONGCOD") is False

    # 5th failure should trigger lockout
    with pytest.raises(ValueError, match="Lockout"):
        store.approve_code("slack", "WRONGCOD")

    # Subsequent validation with correct code should also fail due to lockout
    with pytest.raises(ValueError, match="Lockout"):
        store.approve_code("slack", code)

@pytest.mark.asyncio
async def test_gateway_unauthorized_user_pairing_dm(tmp_path):
    # Setup PairingStore
    store_file = tmp_path / "pairing.json"
    
    # Mock platform adapter
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
                target=payload.get("target", "U-bad"),
                user_id=payload.get("user_id", "U-bad"),
            )
        async def send(self, target, message, thread_id=None):
            self.sent.append((target, message))
            return GatewaySendResult(success=True, message_id="msg_123")

    registry = GatewayRegistry()
    registry.register(
        PlatformEntry(name="test", label="Test", adapter_factory=lambda config: FakeAdapter(config))
    )
    
    # Setup runner with specific pairing store filepath and unauthorized settings
    runner = GatewayRunner(
        runtime=MagicMock(),
        registry=registry,
        gateway_config={
            "session_store": str(tmp_path / "state.db"),
            "pairing_store": str(store_file),
            "hooks": {
                "test": {
                    "enabled": True,
                    "allow_from": ["U-admin"], # Static allowed
                }
            }
        }
    )
    await runner.start()

    # Unauthorized DM (target matches user_id meaning DM)
    result = await runner.handle_webhook("test", {"user_id": "U-bad", "target": "U-bad", "text": "hello"})
    assert result == {"accepted": False, "reason": "unauthorized"}
    
    # Check that a pairing code was generated and sent
    adapter = runner.adapters["test"]
    assert len(adapter.sent) == 1
    target, msg = adapter.sent[0]
    assert target == "U-bad"
    assert "pairing code" in msg.lower()
    
    # Retrieve the code from the message
    import re
    match = re.search(r"code:\s*([A-Za-z0-9]{8})", msg)
    assert match is not None
    code = match.group(1)

    # Admin user approves via command `/approve <code>`
    admin_payload = {"user_id": "U-admin", "target": "admin-channel", "text": f"/approve {code}"}
    cmd_result = await runner.handle_webhook("test", admin_payload)
    assert cmd_result == {"accepted": True, "command": "approve"}

    # Now the user should be authorized
    result2 = await runner.handle_webhook("test", {"user_id": "U-bad", "target": "U-bad", "text": "hello"})
    # Since they are authorized now, the webhook proceeds to agent execution. Let's make sure it didn't return unauthorized.
    assert result2 != {"accepted": False, "reason": "unauthorized"}

def test_cli_pairing_commands(tmp_path, capsys):
    import yaml
    from dojoagents.cli.main import main

    config_path = tmp_path / "agents.yaml"
    pairing_file = tmp_path / "pairing.json"

    # Write config file pointing to the pairing file
    config_data = {
        "gateway": {
            "pairing_store": str(pairing_file)
        }
    }
    config_path.write_text(yaml.safe_dump(config_data), encoding="utf-8")

    # Initially, list should print "no pending pairing requests"
    code = main(["gateway", "pairing", "list", "--config", str(config_path)])
    assert code == 0
    out, _ = capsys.readouterr()
    assert "no pending pairing requests" in out.lower()

    # Generate a code manually to test CLI approve/deny
    store = PairingStore(filepath=str(pairing_file))
    p_code = store.generate_code("slack", "user_1", "User One")

    # List should now show the pending request
    code = main(["gateway", "pairing", "list", "--config", str(config_path)])
    assert code == 0
    out, _ = capsys.readouterr()
    assert "user_1" in out
    assert p_code in out

    # Approve via CLI
    code = main(["gateway", "pairing", "approve", "slack", p_code, "--config", str(config_path)])
    assert code == 0
    out, _ = capsys.readouterr()
    assert "successfully approved" in out.lower()

    # Verify approved in store
    store.load()
    assert store.is_approved("slack", "user_1")

    # Try denying a non-existent code
    code = main(["gateway", "pairing", "deny", "slack", "NOTEXIST", "--config", str(config_path)])
    assert code == 1
    out, _ = capsys.readouterr()
    assert "failed to deny" in out.lower()

    # Generate another code for deny
    p_code2 = store.generate_code("slack", "user_2", "User Two")
    code = main(["gateway", "pairing", "deny", "slack", p_code2, "--config", str(config_path)])
    assert code == 0
    out, _ = capsys.readouterr()
    assert "successfully denied" in out.lower()

    # Verify not pending and not approved
    store.load()
    assert not store.is_approved("slack", "user_2")
    assert len(store.list_pending("slack")) == 0
