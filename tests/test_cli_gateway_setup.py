import json

import pytest
import yaml


class FakeWeChatQRClient:
    def __init__(self):
        self.started = False

    async def login(self):
        self.started = True
        print("WeChat QR login URL: https://login.example/qr")
        return {
            "account_id": "bot-account",
            "token": "bot-token",
            "base_url": "https://ilink.example",
            "user_id": "wechat-user",
        }


@pytest.mark.asyncio
async def test_wechat_qr_login_client_uses_async_httpx(monkeypatch):
    import httpx

    from dojoagents.cli.gateway_setup import WeChatQRLoginClient

    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(
            {
                "url": str(request.url),
                "headers": dict(request.headers),
            }
        )
        if request.url.path.endswith("/get_bot_qrcode"):
            assert request.url.params["bot_type"] == "3"
            return httpx.Response(
                200,
                json={
                    "data": {
                        "qrcode": "qr-1",
                        "qrcode_img_content": "https://login.example/qr",
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "data": {
                    "status": "confirmed",
                    "ilink_bot_id": "bot-account",
                    "bot_token": "bot-token",
                    "baseurl": "https://ilink.example",
                    "ilink_user_id": "wechat-user",
                }
            },
        )

    monkeypatch.setattr("builtins.input", lambda _prompt="": "")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        qr_client = WeChatQRLoginClient(
            http_client=client,
            poll_interval_seconds=0,
            max_attempts=1,
        )
        credentials = await qr_client.login()

    assert credentials == {
        "account_id": "bot-account",
        "token": "bot-token",
        "base_url": "https://ilink.example",
        "user_id": "wechat-user",
    }
    assert calls[0]["url"] == "https://ilinkai.weixin.qq.com/ilink/bot/get_bot_qrcode?bot_type=3"
    assert calls[1]["url"] == "https://ilinkai.weixin.qq.com/ilink/bot/get_qrcode_status?qrcode=qr-1"
    assert calls[0]["headers"]["ilink-app-id"] == "bot"
    assert calls[0]["headers"]["ilink-app-clientversion"] == str((2 << 16) | (2 << 8) | 0)
    assert calls[1]["headers"]["ilink-app-id"] == "bot"


def test_gateway_setup_single_adapter_writes_config(tmp_path, monkeypatch, capsys):
    from dojoagents.cli.main import main

    config_path = tmp_path / "agents.yaml"
    answers = iter(["telegram-token", "123456"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    code = main(["gateway", "setup", "telegram", "--config", str(config_path)])

    assert code == 0
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["gateway"]["enabled"] is True
    assert data["gateway"]["hooks"]["telegram"] == {
        "enabled": True,
        "bot_token": "telegram-token",
        "home_channel": "123456",
    }
    output = capsys.readouterr().out + capsys.readouterr().err
    assert "Telegram configured" in output
    assert str(config_path) in output


def test_gateway_setup_all_adapters_writes_every_hook(tmp_path, monkeypatch):
    from dojoagents.cli.gateway_setup import configure_gateway_adapters

    config_path = tmp_path / "agents.yaml"
    answers = iter(
        [
            "slack-token",
            "C123",
            "",
            "pairing",
            "disabled",
            "y",
            "wecom-key",
            "room-1",
            "feishu-token",
            "chat_id",
            "oc-chat",
            "discord-token",
            "channel-1",
            "telegram-token",
            "123456",
        ]
    )
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    fake_wechat = FakeWeChatQRClient()
    code = configure_gateway_adapters(
        "all",
        config_path=config_path,
        wechat_qr_client=fake_wechat,
    )

    assert code == 0
    hooks = yaml.safe_load(config_path.read_text(encoding="utf-8"))["gateway"]["hooks"]
    assert list(hooks) == ["slack", "wechat", "wecom", "feishu", "discord", "telegram"]
    assert hooks["slack"]["bot_token"] == "slack-token"
    assert hooks["wechat"]["account_id"] == "bot-account"
    assert hooks["wechat"]["token"] == "bot-token"
    assert hooks["wechat"]["base_url"] == "https://ilink.example"
    assert hooks["wechat"]["home_channel"] == "wechat-user"
    assert hooks["wechat"]["dm_policy"] == "pairing"
    assert hooks["wechat"]["group_policy"] == "disabled"
    assert hooks["wecom"]["webhook_key"] == "wecom-key"
    assert hooks["feishu"]["receive_id_type"] == "chat_id"
    assert hooks["discord"]["home_channel"] == "channel-1"
    assert hooks["telegram"]["home_channel"] == "123456"
    assert fake_wechat.started is True


def test_gateway_setup_wechat_uses_qr_url_flow(tmp_path, monkeypatch, capsys):
    from dojoagents.cli.gateway_setup import configure_gateway_adapters

    config_path = tmp_path / "agents.yaml"
    answers = iter(["", "open", "disabled", "n", "manual-home"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(answers))

    code = configure_gateway_adapters(
        "wechat",
        config_path=config_path,
        wechat_qr_client=FakeWeChatQRClient(),
    )

    assert code == 0
    hook = yaml.safe_load(config_path.read_text(encoding="utf-8"))["gateway"]["hooks"]["wechat"]
    assert hook["account_id"] == "bot-account"
    assert hook["token"] == "bot-token"
    assert hook["dm_policy"] == "open"
    assert hook["group_policy"] == "disabled"
    assert hook["home_channel"] == "manual-home"
    output = capsys.readouterr().out + capsys.readouterr().err
    assert "WeChat QR login URL: https://login.example/qr" in output
    assert "WeChat configured via QR login" in output


def test_gateway_setup_rejects_unknown_adapter(tmp_path):
    from dojoagents.cli.main import main

    code = main(["gateway", "setup", "unknown", "--config", str(tmp_path / "agents.yaml")])

    assert code == 2


def test_sessions_export_cli_exports_messages(tmp_path):
    from dojoagents.cli.main import main
    from dojoagents.agent.models import AgentResponse, ChatRequest
    from dojoagents.agent.session_manager import DojoAgentSessionManager

    sessions_root = tmp_path / "sessions"
    manager = DojoAgentSessionManager(root=sessions_root)
    request = ChatRequest(message="hello", user_id="u1", session_id="sess-cli", channel="cli")
    handle = manager.begin_run_sync(request, model="fake-model", run_id="run-cli")
    manager.repository.create_message(
        "sess-cli",
        "dojo-agent",
        manager.message_from_text("user", "hello", 0),
    )
    manager.finish_run_sync(handle, AgentResponse(content="hi", session_id="sess-cli"))
    other = ChatRequest(message="other", user_id="u1", session_id="sess-other", channel="cli")
    other_handle = manager.begin_run_sync(other, model="fake-model", run_id="run-other")
    manager.repository.create_message(
        "sess-other",
        "dojo-agent",
        manager.message_from_text("user", "other", 0),
    )
    manager.finish_run_sync(other_handle, AgentResponse(content="other", session_id="sess-other"))

    config_path = tmp_path / "agents.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "sessions": {
                    "root": str(sessions_root),
                    "agent_id": "dojo-agent",
                    "export_default_dir": str(tmp_path / "default-export"),
                }
            }
        ),
        encoding="utf-8",
    )
    output_root = tmp_path / "exports"

    code = main(
        [
            "sessions",
            "export",
            "--config",
            str(config_path),
            "--session-id",
            "sess-cli",
            "--output-dir",
            str(output_root),
            "--include-archived",
            "--no-raw-strands",
        ]
    )

    assert code == 0
    [export_dir] = [path for path in output_root.iterdir() if path.is_dir()]
    assert (export_dir / "messages.jsonl").exists()
    assert (export_dir / "openai_dataset.jsonl").exists()
    rows = [json.loads(line) for line in (export_dir / "messages.jsonl").read_text(encoding="utf-8").splitlines()]
    assert {row["session_id"] for row in rows} == {"sess-cli"}
    assert not (export_dir / "strands").exists()


def test_model_setup_writes_config(tmp_path, monkeypatch):
    import httpx
    from dojoagents.cli.main import main

    config_path = tmp_path / "agents.yaml"

    inputs = iter(["1", "", "1"])
    monkeypatch.setattr("builtins.input", lambda _prompt="": next(inputs))
    monkeypatch.setattr("getpass.getpass", lambda _prompt="": "fake-openai-key")

    def mock_get(url, headers=None, timeout=None):
        return httpx.Response(200, json={"data": [{"id": "gpt-4o"}, {"id": "gpt-4o-mini"}]})

    monkeypatch.setattr("httpx.get", mock_get)

    code = main(["model", "--config", str(config_path)])

    assert code == 0
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    assert data["llm_provider"]["default"] == "openai"
    assert data["llm_provider"]["providers"]["openai"]["model"] == "gpt-4o"
    assert data["llm_provider"]["providers"]["openai"]["base_url"] == "https://api.openai.com/v1"
    assert data["llm_provider"]["providers"]["openai"]["api_key"] == "fake-openai-key"
    assert data["agent"]["model"] == "gpt-4o"
