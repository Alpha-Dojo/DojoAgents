from __future__ import annotations

from dojoagents.gateway.adapters.discord import DiscordAdapter
from dojoagents.gateway.adapters.feishu import FeishuAdapter
from dojoagents.gateway.adapters.slack import SlackAdapter
from dojoagents.gateway.adapters.telegram import TelegramAdapter
from dojoagents.gateway.adapters.wechat import WeChatAdapter
from dojoagents.gateway.adapters.wecom import WeComAdapter
from dojoagents.gateway.registry import GatewayRegistry, PlatformEntry


def create_default_gateway_registry() -> GatewayRegistry:
    registry = GatewayRegistry()
    for adapter_cls in (
        SlackAdapter,
        WeChatAdapter,
        WeComAdapter,
        FeishuAdapter,
        DiscordAdapter,
        TelegramAdapter,
    ):
        registry.register(
            PlatformEntry(
                name=adapter_cls.platform,
                label=adapter_cls.label,
                adapter_factory=lambda config, cls=adapter_cls: cls(config),
                required_env=[],
            )
        )
    return registry


__all__ = [
    "DiscordAdapter",
    "FeishuAdapter",
    "SlackAdapter",
    "TelegramAdapter",
    "WeChatAdapter",
    "WeComAdapter",
    "create_default_gateway_registry",
]
