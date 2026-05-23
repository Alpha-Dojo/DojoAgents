from __future__ import annotations

from typing import Any

from dojoagents.gateway.adapters.base import BaseGatewayAdapter, GatewayEvent


class TelegramAdapter(BaseGatewayAdapter):
    platform = "telegram"
    label = "Telegram"

    def normalize_message(self, payload: dict[str, Any]) -> GatewayEvent:
        message = payload.get("message") or payload.get("edited_message") or payload
        chat = message.get("chat", {})
        sender = message.get("from", {})
        return GatewayEvent(
            platform=self.platform,
            text=str(message.get("text") or message.get("caption") or ""),
            target=str(chat.get("id", "")),
            user_id=str(sender.get("id", "")),
            message_id=str(message.get("message_id", "")),
            thread_id=(
                str(message.get("message_thread_id"))
                if message.get("message_thread_id") is not None
                else None
            ),
            raw=payload,
        )

    def send_url(self, target: str) -> str:
        token = self.config.get("bot_token", "")
        return f"https://api.telegram.org/bot{token}/sendMessage"

    def send_payload(
        self, target: str, message: str, *, thread_id: str | None = None
    ) -> dict[str, Any]:
        payload = {"chat_id": target, "text": message}
        if thread_id:
            payload["message_thread_id"] = thread_id
        return payload

    def auth_headers(self) -> dict[str, str]:
        return {}
