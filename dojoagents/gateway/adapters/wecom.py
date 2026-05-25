from __future__ import annotations

from typing import Any

from dojoagents.gateway.adapters.base import BaseGatewayAdapter, GatewayEvent


class WeComAdapter(BaseGatewayAdapter):
    platform = "wecom"
    label = "WeCom"

    def normalize_message(self, payload: dict[str, Any]) -> GatewayEvent:
        text = payload.get("text", {})
        target = payload.get("roomid") or payload.get("chatid") or payload.get("from", "")
        return GatewayEvent(
            platform=self.platform,
            text=str(text.get("content", payload.get("content", ""))),
            target=str(target),
            user_id=str(payload.get("from", "")),
            message_id=str(payload.get("msgid", "")),
            raw=payload,
        )

    def send_url(self, target: str) -> str:
        key = self.config.get("webhook_key") or self.config.get("bot_token", "")
        return f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={key}"

    def send_payload(
        self, target: str, message: str, *, thread_id: str | None = None
    ) -> dict[str, Any]:
        return {"chatid": target, "msgtype": "text", "text": {"content": message}}

    def auth_headers(self) -> dict[str, str]:
        return {}
