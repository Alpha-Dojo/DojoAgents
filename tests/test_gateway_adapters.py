import json
import asyncio

import pytest


class FakeHttpClient:
    def __init__(self):
        self.calls = []

    async def post_json(self, url, payload, headers=None):
        self.calls.append({"url": url, "payload": payload, "headers": headers or {}})
        return {"ok": True, "message_id": "sent-1"}


@pytest.mark.asyncio
async def test_httpx_client_posts_json_with_async_transport():
    import httpx

    from dojoagents.gateway.adapters.base import HttpxAsyncHttpClient

    seen = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["headers"] = dict(request.headers)
        seen["payload"] = request.read().decode("utf-8")
        return httpx.Response(200, json={"ok": True, "message_id": "m-httpx"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        http = HttpxAsyncHttpClient(client=client)
        response = await http.post_json(
            "https://example.test/send",
            {"text": "hello"},
            headers={"X-Dojo-Test": "1"},
        )

    assert response == {"ok": True, "message_id": "m-httpx"}
    assert seen["method"] == "POST"
    assert seen["headers"]["x-dojo-test"] == "1"
    assert seen["payload"] == '{"text":"hello"}'


def test_default_gateway_registry_contains_all_designed_adapters():
    from dojoagents.gateway.adapters import create_default_gateway_registry

    registry = create_default_gateway_registry()

    assert [entry["name"] for entry in registry.status()] == [
        "slack",
        "wechat",
        "wecom",
        "feishu",
        "discord",
        "telegram",
    ]


@pytest.mark.parametrize(
    ("adapter_path", "config", "payload", "expected_text", "expected_target"),
    [
        (
            "dojoagents.gateway.adapters.slack.SlackAdapter",
            {"bot_token": "xoxb-token"},
            {"event": {"text": "hello slack", "channel": "C1", "user": "U1", "ts": "100.1"}},
            "hello slack",
            "C1",
        ),
        (
            "dojoagents.gateway.adapters.telegram.TelegramAdapter",
            {"bot_token": "telegram-token"},
            {"message": {"text": "hello tg", "chat": {"id": 123}, "from": {"id": 45}, "message_id": 7}},
            "hello tg",
            "123",
        ),
        (
            "dojoagents.gateway.adapters.discord.DiscordAdapter",
            {"bot_token": "discord-token"},
            {"content": "hello discord", "channel_id": "D1", "author": {"id": "A1"}, "id": "M1"},
            "hello discord",
            "D1",
        ),
        (
            "dojoagents.gateway.adapters.feishu.FeishuAdapter",
            {"bot_token": "feishu-token"},
            {"event": {"message": {"content": '{"text":"hello feishu"}', "chat_id": "F1", "message_id": "M1"}, "sender": {"sender_id": {"open_id": "O1"}}}},
            "hello feishu",
            "F1",
        ),
        (
            "dojoagents.gateway.adapters.wecom.WeComAdapter",
            {"bot_token": "wecom-token"},
            {"text": {"content": "hello wecom"}, "from": "U1", "roomid": "R1", "msgid": "M1"},
            "hello wecom",
            "R1",
        ),
        (
            "dojoagents.gateway.adapters.wechat.WeChatAdapter",
            {"bot_token": "wechat-token"},
            {"Content": "hello wechat", "FromUserName": "U1", "ToUserName": "BOT", "MsgId": "M1"},
            "hello wechat",
            "U1",
        ),
    ],
)
def test_adapters_normalize_text_payloads(adapter_path, config, payload, expected_text, expected_target):
    module_name, _, class_name = adapter_path.rpartition(".")
    module = __import__(module_name, fromlist=[class_name])
    adapter_cls = getattr(module, class_name)
    adapter = adapter_cls(config)

    event = adapter.normalize_message(payload)

    assert event.text == expected_text
    assert event.target == expected_target
    assert event.platform == adapter.platform
    assert event.to_chat_request(session_id="s1").message == expected_text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter_path", "config", "target", "expected_url_part", "expected_payload_key"),
    [
        ("dojoagents.gateway.adapters.slack.SlackAdapter", {"bot_token": "xoxb-token"}, "C1", "slack.com/api/chat.postMessage", "channel"),
        ("dojoagents.gateway.adapters.telegram.TelegramAdapter", {"bot_token": "telegram-token"}, "123", "api.telegram.org/bottelegram-token/sendMessage", "chat_id"),
        ("dojoagents.gateway.adapters.discord.DiscordAdapter", {"bot_token": "discord-token"}, "D1", "discord.com/api/v10/channels/D1/messages", "content"),
        ("dojoagents.gateway.adapters.feishu.FeishuAdapter", {"bot_token": "feishu-token"}, "F1", "open.feishu.cn/open-apis/im/v1/messages", "receive_id"),
        ("dojoagents.gateway.adapters.wecom.WeComAdapter", {"bot_token": "wecom-token"}, "R1", "qyapi.weixin.qq.com/cgi-bin/webhook/send", "chatid"),
        ("dojoagents.gateway.adapters.wechat.WeChatAdapter", {"token": "wechat-token"}, "U1", "ilinkai.weixin.qq.com/ilink/bot/sendmessage", "msg"),
    ],
)
async def test_adapters_send_text_with_platform_specific_shape(
    adapter_path, config, target, expected_url_part, expected_payload_key
):
    module_name, _, class_name = adapter_path.rpartition(".")
    module = __import__(module_name, fromlist=[class_name])
    adapter_cls = getattr(module, class_name)
    http = FakeHttpClient()
    adapter = adapter_cls(config, http_client=http)

    result = await adapter.send(target, "hello")

    assert result.success is True
    assert expected_url_part in http.calls[0]["url"]
    assert expected_payload_key in http.calls[0]["payload"]


@pytest.mark.asyncio
async def test_wechat_adapter_accepts_ilink_qr_token_config():
    from dojoagents.gateway.adapters.wechat import WeChatAdapter

    http = FakeHttpClient()
    adapter = WeChatAdapter({"token": "qr-token", "base_url": "https://ilink.example"}, http_client=http)

    result = await adapter.send("U1", "hello")

    assert result.success is True
    call = http.calls[0]
    assert call["url"] == "https://ilink.example/ilink/bot/sendmessage"
    assert call["headers"]["Authorization"] == "Bearer qr-token"
    assert call["headers"]["AuthorizationType"] == "ilink_bot_token"
    assert call["headers"]["iLink-App-Id"] == "bot"
    assert call["headers"]["iLink-App-ClientVersion"] == str((2 << 16) | (2 << 8) | 0)
    expected_body = json.dumps(call["payload"], ensure_ascii=False, separators=(",", ":"))
    assert call["headers"]["Content-Length"] == str(len(expected_body.encode("utf-8")))
    payload = call["payload"]
    assert payload["msg"]["from_user_id"] == ""
    assert payload["msg"]["to_user_id"] == "U1"
    assert payload["msg"]["client_id"].startswith("dojo-wechat-")
    assert payload["msg"]["message_type"] == 2
    assert payload["msg"]["message_state"] == 2
    assert payload["msg"]["item_list"] == [{"type": 1, "text_item": {"text": "hello"}}]
    assert payload["base_info"] == {"channel_version": "2.2.0"}



@pytest.mark.asyncio
async def test_wechat_polling_runs_gateway_agent_and_replies_with_context_token(
    tmp_path,
    monkeypatch,
):
    import dojoagents.gateway.adapters.wechat as wechat

    from dojoagents.agent.models import AgentResponse
    from dojoagents.gateway.adapters.wechat import WeChatAdapter
    from dojoagents.gateway.registry import GatewayRegistry, PlatformEntry
    from dojoagents.gateway.runner import GatewayRunner

    agent_seen = asyncio.Event()
    monkeypatch.setattr(wechat, "_account_dir", lambda: tmp_path / "wechat" / "accounts")

    class FlowHttpClient:
        def __init__(self):
            self.calls = []
            self.polls = 0

        async def post_json(self, url, payload, headers=None):
            self.calls.append({"url": url, "payload": payload, "headers": headers or {}})
            if url.endswith("/ilink/bot/getupdates"):
                self.polls += 1
                if self.polls == 1:
                    return {
                        "sync_buf": "sync-buf-1",
                        "get_updates_buf": "buf-1",
                        "msgs": [
                            {
                                "seq": 1,
                                "message_id": 7464560103419609352,
                                "from_user_id": "U1",
                                "to_user_id": "BOT",
                                "client_id": "client-1",
                                "create_time_ms": 1779689813397,
                                "update_time_ms": 1779689813519,
                                "delete_time_ms": 0,
                                "session_id": "",
                                "group_id": "",
                                "message_type": 1,
                                "message_state": 2,
                                "item_list": [
                                    {
                                        "type": 1,
                                        "create_time_ms": 1779689813397,
                                        "update_time_ms": 1779689813397,
                                        "is_completed": True,
                                        "button_item_list": [],
                                        "text_item": {"text": "hello wechat"},
                                    }
                                ],
                                "context_token": "ctx-1",
                                "root_id": 0,
                                "parent_id": 0,
                            }
                        ],
                    }
                return {"sync_buf": "sync-buf-1", "get_updates_buf": "buf-1", "msgs": []}
            if url.endswith("/ilink/bot/sendmessage"):
                return {"errcode": 0, "message_id": "sent-1"}
            raise AssertionError(f"unexpected url: {url}")

    class FakeAgent:
        async def run(self, request):
            assert request.channel == "wechat"
            assert request.message == "hello wechat"
            assert request.user_id == "U1"
            agent_seen.set()
            return AgentResponse(content="reply from agent", session_id=request.session_id)

    class FakeRuntime:
        agent = FakeAgent()

    http = FlowHttpClient()
    registry = GatewayRegistry()
    registry.register(
        PlatformEntry(
            name="wechat",
            label="WeChat",
            adapter_factory=lambda config: WeChatAdapter(config, http_client=http),
        )
    )
    runner = GatewayRunner(
        runtime=FakeRuntime(),
        registry=registry,
        gateway_config={
            "hooks": {
                "wechat": {
                    "enabled": True,
                    "account_id": "BOT",
                    "token": "bot-token",
                    "base_url": "https://ilink.example",
                    "dm_policy": "open",
                    "poll_interval_seconds": 0.01,
                    "context_token_store": str(tmp_path / "ctx.json"),
                }
            },
            "streaming": {"enabled": False},
            "session_store": str(tmp_path / "sessions.db"),
            "pid_file": str(tmp_path / "gateway.pid"),
            "clean_marker": str(tmp_path / ".clean_shutdown"),
        },
    )

    await runner.start()
    await asyncio.wait_for(agent_seen.wait(), timeout=1.0)
    await runner.stop()

    send_calls = [call for call in http.calls if call["url"].endswith("/ilink/bot/sendmessage")]
    assert len(send_calls) == 1
    assert send_calls[0]["payload"]["msg"]["context_token"] == "ctx-1"
    assert send_calls[0]["payload"]["msg"]["to_user_id"] == "U1"
    assert send_calls[0]["payload"]["msg"]["item_list"][0]["text_item"]["text"] == "reply from agent"
    sync_file = tmp_path / "wechat" / "accounts" / "BOT.sync.json"
    assert json.loads(sync_file.read_text(encoding="utf-8")) == {
        "get_updates_buf": "buf-1",
        "sync_buf": "sync-buf-1",
    }


@pytest.mark.asyncio
async def test_wechat_send_retries_without_stale_context_token(tmp_path):
    from dojoagents.gateway.adapters.wechat import WeChatAdapter

    class RetryHttpClient:
        def __init__(self):
            self.calls = []

        async def post_json(self, url, payload, headers=None):
            self.calls.append(
                {
                    "url": url,
                    "payload": json.loads(json.dumps(payload)),
                    "headers": headers or {},
                }
            )
            if len(self.calls) == 1:
                return {"errcode": -14, "errmsg": "session expired"}
            return {"errcode": 0, "message_id": "sent-2"}

    http = RetryHttpClient()
    adapter = WeChatAdapter(
        {
            "token": "bot-token",
            "base_url": "https://ilink.example",
            "context_token_store": str(tmp_path / "ctx.json"),
        },
        http_client=http,
    )
    adapter.context_tokens.set("U1", "stale-ctx")

    result = await adapter.send("U1", "hello")

    assert result.success is True
    assert len(http.calls) == 2
    assert http.calls[0]["payload"]["msg"]["context_token"] == "stale-ctx"
    assert "context_token" not in http.calls[1]["payload"].get("msg", {})
    assert adapter.context_tokens.get("U1") is None


def test_registry_can_create_default_adapter_instances():
    from dojoagents.gateway.adapters import create_default_gateway_registry
    from dojoagents.gateway.adapters.telegram import TelegramAdapter

    registry = create_default_gateway_registry()
    adapter = registry.create_adapter("telegram", {"bot_token": "token"})

    assert isinstance(adapter, TelegramAdapter)


def test_gateway_server_exposes_platforms_and_normalizes_webhook():
    from fastapi.testclient import TestClient

    from dojoagents.gateway.server import create_app

    client = TestClient(create_app())

    assert client.get("/api/platforms").json()[0]["name"] == "slack"
    response = client.post(
        "/api/webhook/telegram",
        json={
            "message": {
                "text": "hello",
                "chat": {"id": 123},
                "from": {"id": 45},
                "message_id": 7,
            }
        },
    )
    assert response.json()["event"]["text"] == "hello"
    assert response.json()["chat_request"]["channel"] == "telegram"


@pytest.mark.asyncio
async def test_gateway_runner_starts_configured_adapters_runs_agent_and_sends_reply():
    from dojoagents.agent.models import AgentResponse
    from dojoagents.gateway.adapters.base import GatewayEvent, GatewaySendResult
    from dojoagents.gateway.registry import GatewayRegistry, PlatformEntry
    from dojoagents.gateway.runner import GatewayRunner

    class FakeAgent:
        async def run(self, request):
            assert request.message == "hello"
            assert request.channel == "test"
            return AgentResponse(content="reply:hello", session_id=request.session_id)

    class FakeRuntime:
        agent = FakeAgent()

    class FakeAdapter:
        platform = "test"
        label = "Test"

        def __init__(self, config):
            self.config = config
            self.started = False
            self.sent = []

        async def start(self):
            self.started = True

        async def stop(self):
            self.started = False

        def normalize_message(self, payload):
            return GatewayEvent(
                platform="test",
                text=payload["text"],
                target=payload["target"],
                user_id=payload["user_id"],
                message_id="m1",
            )

        async def send(self, target, message, *, thread_id=None):
            self.sent.append((target, message, thread_id))
            return GatewaySendResult(success=True, message_id="sent-1")

    registry = GatewayRegistry()
    registry.register(
        PlatformEntry(name="test", label="Test", adapter_factory=lambda config: FakeAdapter(config))
    )
    runner = GatewayRunner(
        runtime=FakeRuntime(),
        registry=registry,
        gateway_config={"hooks": {"test": {"enabled": True, "home_channel": "T1"}}},
    )

    await runner.start()
    result = await runner.handle_webhook(
        "test",
        {"text": "hello", "target": "T1", "user_id": "U1"},
    )

    assert result["accepted"] is True
    assert runner.adapters["test"].sent == [("T1", "reply:hello", None)]
    assert runner.status()["state"] == "running"
    await runner.stop()
    assert runner.status()["state"] == "stopped"


@pytest.mark.asyncio
async def test_gateway_runner_enforces_allowlist_before_agent_run():
    from dojoagents.gateway.adapters.base import GatewayEvent
    from dojoagents.gateway.registry import GatewayRegistry, PlatformEntry
    from dojoagents.gateway.runner import GatewayRunner

    class FakeAgent:
        calls = 0

        async def run(self, request):
            self.calls += 1
            raise AssertionError("agent should not run")

    class FakeRuntime:
        def __init__(self):
            self.agent = FakeAgent()

    class FakeAdapter:
        platform = "test"
        label = "Test"

        def __init__(self, config):
            pass

        async def start(self):
            pass

        async def stop(self):
            pass

        def normalize_message(self, payload):
            return GatewayEvent(
                platform="test",
                text="blocked",
                target="T1",
                user_id=payload["user_id"],
            )

    registry = GatewayRegistry()
    registry.register(
        PlatformEntry(name="test", label="Test", adapter_factory=lambda config: FakeAdapter(config))
    )
    runtime = FakeRuntime()
    runner = GatewayRunner(
        runtime=runtime,
        registry=registry,
        gateway_config={"hooks": {"test": {"enabled": True, "allow_from": ["U-ok"]}}},
    )
    await runner.start()

    result = await runner.handle_webhook("test", {"user_id": "U-bad"})

    assert result == {"accepted": False, "reason": "unauthorized"}
    assert runtime.agent.calls == 0


def test_gateway_server_uses_runner_for_webhook_and_status():
    from fastapi.testclient import TestClient

    from dojoagents.gateway.server import create_app

    class FakeRunner:
        def status(self):
            return {"state": "running", "platforms": {"test": {"state": "connected"}}}

        async def handle_webhook(self, platform, payload):
            return {"accepted": True, "platform": platform, "payload": payload}

        async def send(self, platform, target, message, thread_id=None):
            return {"success": True, "message_id": "sent"}

    client = TestClient(create_app(runner=FakeRunner()))

    assert client.get("/api/health").json()["state"] == "running"
    assert client.post("/api/webhook/test", json={"text": "hi"}).json()["accepted"] is True
    assert client.post("/api/send/test/T1", json={"message": "hi"}).json()["success"] is True


@pytest.mark.asyncio
async def test_gateway_runner_persists_sessions_commands_redacts_and_delivers_cron(tmp_path):
    from dojoagents.agent.models import AgentResponse
    from dojoagents.gateway.adapters.base import GatewayEvent, GatewaySendResult
    from dojoagents.gateway.registry import GatewayRegistry, PlatformEntry
    from dojoagents.gateway.runner import GatewayRunner

    class FakeAgent:
        async def run(self, request):
            assert request.metadata["media"][0]["type"] == "image"
            return AgentResponse(
                content="token sk-secretsecretsecretsecret",
                session_id=request.session_id,
            )

    class FakeRuntime:
        agent = FakeAgent()

    class FakeAdapter:
        platform = "test"
        label = "Test"

        def __init__(self, config):
            self.sent = []
            self.typing = []

        async def start(self):
            pass

        async def stop(self):
            pass

        def normalize_message(self, payload):
            return GatewayEvent(
                platform="test",
                text=payload["text"],
                target=payload["target"],
                user_id=payload["user_id"],
                raw=payload,
            )

        async def send(self, target, message, *, thread_id=None):
            self.sent.append((target, message, thread_id))
            return GatewaySendResult(success=True, message_id="sent")

        async def send_typing(self, target, enabled=True, *, thread_id=None):
            self.typing.append((target, enabled, thread_id))

    registry = GatewayRegistry()
    registry.register(
        PlatformEntry(name="test", label="Test", adapter_factory=lambda config: FakeAdapter(config))
    )
    runner = GatewayRunner(
        runtime=FakeRuntime(),
        registry=registry,
        gateway_config={
            "hooks": {
                "test": {
                    "enabled": True,
                    "home_channel": "HOME",
                    "gateway_restart_notification": True,
                }
            },
            "session_store": str(tmp_path / "sessions.yaml"),
            "pid_file": str(tmp_path / "gateway.pid"),
            "clean_marker": str(tmp_path / ".clean_shutdown"),
        },
    )

    await runner.start()
    adapter = runner.adapters["test"]
    assert ("HOME", "Gateway started", None) in adapter.sent

    result = await runner.handle_webhook(
        "test",
        {
            "text": "hello",
            "target": "T1",
            "user_id": "U1",
            "attachments": [{"type": "image", "url": "https://example.test/a.png"}],
        },
    )
    assert result["accepted"] is True
    assert adapter.sent[-1][1] == "token [REDACTED]"
    assert adapter.typing == [("T1", True, None), ("T1", False, None)]
    assert (tmp_path / "sessions.yaml").exists()

    status_reply = await runner.handle_webhook(
        "test", {"text": "/status", "target": "T1", "user_id": "U1"}
    )
    assert status_reply["command"] == "status"
    assert "running" in adapter.sent[-1][1]

    model_reply = await runner.handle_webhook(
        "test", {"text": "/model fast-model", "target": "T1", "user_id": "U1"}
    )
    assert model_reply["command"] == "model"
    assert runner.session_store.get("test:T1:U1").model_override == "fast-model"

    sent = await runner.deliver({"platform": "test", "target": "T1"}, "cron brief")
    assert sent["success"] is True
    assert adapter.sent[-1][1] == "cron brief"

    await runner.stop()
    assert (tmp_path / ".clean_shutdown").exists()
    assert not (tmp_path / "gateway.pid").exists()


@pytest.mark.asyncio
async def test_gateway_runner_blocks_wechat_group_when_group_policy_disabled(tmp_path):
    from dojoagents.gateway.adapters.base import GatewayEvent
    from dojoagents.gateway.registry import GatewayRegistry, PlatformEntry
    from dojoagents.gateway.runner import GatewayRunner

    class FakeRuntime:
        class agent:
            @staticmethod
            async def run(request):
                raise AssertionError("agent should not run")

    class FakeAdapter:
        def __init__(self, config):
            pass

        async def start(self):
            pass

        async def stop(self):
            pass

        def normalize_message(self, payload):
            return GatewayEvent(
                platform="wechat",
                text="hello",
                target="room@chatroom",
                user_id="U1",
                raw={"room_id": "room@chatroom"},
            )

    registry = GatewayRegistry()
    registry.register(
        PlatformEntry(name="wechat", label="WeChat", adapter_factory=lambda config: FakeAdapter(config))
    )
    runner = GatewayRunner(
        runtime=FakeRuntime(),
        registry=registry,
        gateway_config={
            "hooks": {"wechat": {"enabled": True, "group_policy": "disabled"}},
            "session_store": str(tmp_path / "sessions.yaml"),
        },
    )
    await runner.start()

    assert await runner.handle_webhook("wechat", {}) == {
        "accepted": False,
        "reason": "unauthorized",
    }


@pytest.mark.asyncio
async def test_gateway_runner_wechat_pairing_policy_requires_approval(tmp_path):
    from dojoagents.gateway.adapters.base import GatewayEvent, GatewaySendResult
    from dojoagents.gateway.registry import GatewayRegistry, PlatformEntry
    from dojoagents.gateway.runner import GatewayRunner

    class FakeRuntime:
        class agent:
            @staticmethod
            async def run(request):
                raise AssertionError("agent should not run before pairing approval")

    class FakeAdapter:
        def __init__(self, config):
            self.sent = []

        async def start(self):
            pass

        async def stop(self):
            pass

        def normalize_message(self, payload):
            return GatewayEvent(
                platform="wechat",
                text="hello",
                target="U1",
                user_id="U1",
                raw=payload,
            )

        async def send(self, target, message, *, thread_id=None):
            self.sent.append((target, message))
            return GatewaySendResult(success=True)

    registry = GatewayRegistry()
    registry.register(
        PlatformEntry(
            name="wechat",
            label="WeChat",
            adapter_factory=lambda config: FakeAdapter(config),
        )
    )
    runner = GatewayRunner(
        runtime=FakeRuntime(),
        registry=registry,
        gateway_config={
            "hooks": {"wechat": {"enabled": True, "dm_policy": "pairing"}},
            "session_store": str(tmp_path / "sessions.db"),
            "pairing_store": str(tmp_path / "pairing.json"),
            "pid_file": str(tmp_path / "gateway.pid"),
        },
    )
    await runner.start()

    result = await runner.handle_webhook("wechat", {"user_name": "Alice"})

    assert result == {"accepted": False, "reason": "unauthorized"}
    assert runner.adapters["wechat"].sent[0][0] == "U1"
    assert "pairing code" in runner.adapters["wechat"].sent[0][1]
    await runner.stop()


@pytest.mark.asyncio
async def test_gateway_runner_wechat_group_allowlist_uses_group_allow_from(tmp_path):
    from dojoagents.agent.models import AgentResponse
    from dojoagents.gateway.adapters.base import GatewayEvent, GatewaySendResult
    from dojoagents.gateway.registry import GatewayRegistry, PlatformEntry
    from dojoagents.gateway.runner import GatewayRunner

    class FakeRuntime:
        class agent:
            @staticmethod
            async def run(request):
                return AgentResponse(content="ok", session_id=request.session_id)

    class FakeAdapter:
        def __init__(self, config):
            self.sent = []

        async def start(self):
            pass

        async def stop(self):
            pass

        def normalize_message(self, payload):
            return GatewayEvent(
                platform="wechat",
                text="hello",
                target=payload["target"],
                user_id="U1",
                raw={"room_id": payload["target"]},
            )

        async def send(self, target, message, *, thread_id=None):
            self.sent.append((target, message))
            return GatewaySendResult(success=True)

    registry = GatewayRegistry()
    registry.register(
        PlatformEntry(
            name="wechat",
            label="WeChat",
            adapter_factory=lambda config: FakeAdapter(config),
        )
    )
    runner = GatewayRunner(
        runtime=FakeRuntime(),
        registry=registry,
        gateway_config={
            "hooks": {
                "wechat": {
                    "enabled": True,
                    "group_policy": "allowlist",
                    "group_allow_from": ["room-ok@chatroom"],
                }
            },
            "session_store": str(tmp_path / "sessions.db"),
            "pid_file": str(tmp_path / "gateway.pid"),
        },
    )
    await runner.start()

    blocked = await runner.handle_webhook("wechat", {"target": "room-bad@chatroom"})
    allowed = await runner.handle_webhook("wechat", {"target": "room-ok@chatroom"})

    assert blocked == {"accepted": False, "reason": "unauthorized"}
    assert allowed["accepted"] is True
    assert runner.adapters["wechat"].sent[-1] == ("room-ok@chatroom", "ok")
    await runner.stop()


@pytest.mark.asyncio
async def test_gateway_runner_wires_adapter_listener_and_hooks(tmp_path):
    from dojoagents.agent.models import AgentResponse
    from dojoagents.gateway.adapters.base import GatewayEvent, GatewaySendResult
    from dojoagents.gateway.registry import GatewayRegistry, PlatformEntry
    from dojoagents.gateway.runner import GatewayRunner

    events = []

    class FakeAgent:
        async def run(self, request):
            return AgentResponse(content="ok", session_id=request.session_id)

    class FakeRuntime:
        agent = FakeAgent()

    class ListenerAdapter:
        def __init__(self, config):
            self.handler = None
            self.sent = []

        def set_message_handler(self, handler):
            self.handler = handler

        async def start(self):
            await self.handler({"text": "from-listener", "target": "T1", "user_id": "U1"})

        async def stop(self):
            pass

        def normalize_message(self, payload):
            return GatewayEvent(
                platform="test",
                text=payload["text"],
                target=payload["target"],
                user_id=payload["user_id"],
            )

        async def send(self, target, message, *, thread_id=None):
            self.sent.append(message)
            return GatewaySendResult(success=True)

    registry = GatewayRegistry()
    registry.register(
        PlatformEntry(name="test", label="Test", adapter_factory=lambda config: ListenerAdapter(config))
    )
    runner = GatewayRunner(
        runtime=FakeRuntime(),
        registry=registry,
        gateway_config={
            "hooks": {"test": {"enabled": True}},
            "session_store": str(tmp_path / "sessions.yaml"),
            "pid_file": str(tmp_path / "gateway.pid"),
        },
    )
    runner.register_hook("message:received", lambda payload: events.append(payload["event"].text))

    await runner.start()

    assert events == ["from-listener"]
    assert runner.adapters["test"].sent == ["ok"]


@pytest.mark.asyncio
async def test_wechat_adapter_file_persistence(tmp_path, monkeypatch):
    import dojoagents.gateway.adapters.wechat as wechat
    from dojoagents.gateway.adapters.wechat import WeChatAdapter

    # Mock _account_dir to point to a temp path
    monkeypatch.setattr(wechat, "_account_dir", lambda: tmp_path / "wechat" / "accounts")

    config = {
        "account_id": "test-bot-acc",
        "token": "token-12345",
        "base_url": "https://ilink.test",
        "home_channel": "wechat-owner",
    }
    
    # 1. Initialize adapter and start it
    adapter = WeChatAdapter(config)
    await adapter.start()
    
    # 2. Check that the credentials file is written
    credentials_file = tmp_path / "wechat" / "accounts" / "test-bot-acc.json"
    assert credentials_file.exists()
    
    # 3. Modify updates_buf and save it
    adapter.save_update_buf("my-sync-buf")
    sync_file = tmp_path / "wechat" / "accounts" / "test-bot-acc.sync.json"
    assert sync_file.exists()
    
    # 4. Stop adapter
    await adapter.stop()

    # 5. Initialize a new adapter instance with only the account_id
    new_adapter = WeChatAdapter({"account_id": "test-bot-acc"})
    
    # Verify updates_buf and config were loaded from disk persistence
    assert new_adapter._updates_buf == "my-sync-buf"
    assert new_adapter.config.get("bot_token") == "token-12345"
    assert new_adapter.config.get("base_url") == "https://ilink.test"
