from __future__ import annotations

from typing import Any

from dojoagents.gateway.adapters.base import BaseGatewayAdapter, GatewayEvent


class DiscordAdapter(BaseGatewayAdapter):
    platform = "discord"
    label = "Discord"

    def normalize_message(self, payload: dict[str, Any]) -> GatewayEvent:
        author = payload.get("author", {})
        return GatewayEvent(
            platform=self.platform,
            text=str(payload.get("content", "")),
            target=str(payload.get("channel_id", "")),
            user_id=str(author.get("id", "")),
            message_id=str(payload.get("id", "")),
            thread_id=payload.get("thread_id"),
            raw=payload,
        )

    def send_url(self, target: str) -> str:
        return f"https://discord.com/api/v10/channels/{target}/messages"

    def send_payload(
        self, target: str, message: str, *, thread_id: str | None = None
    ) -> dict[str, Any]:
        return {"content": message}

    def auth_headers(self) -> dict[str, str]:
        token = self.config.get("bot_token", "")
        return {"Authorization": f"Bot {token}"} if token else {}
