from __future__ import annotations

import json
from typing import Any

from dojoagents.gateway.adapters.base import (
    BaseGatewayAdapter,
    GatewayEvent,
    text_from_json_content,
)


class FeishuAdapter(BaseGatewayAdapter):
    platform = "feishu"
    label = "Feishu"

    def normalize_message(self, payload: dict[str, Any]) -> GatewayEvent:
        event = payload.get("event", payload)
        message = event.get("message", event)
        sender_id = event.get("sender", {}).get("sender_id", {})
        return GatewayEvent(
            platform=self.platform,
            text=text_from_json_content(message.get("content", "")),
            target=str(message.get("chat_id", "")),
            user_id=str(sender_id.get("open_id") or sender_id.get("user_id") or ""),
            message_id=str(message.get("message_id", "")),
            thread_id=message.get("thread_id"),
            raw=payload,
        )

    def send_url(self, target: str) -> str:
        receive_id_type = self.config.get("receive_id_type", "chat_id")
        return (
            "https://open.feishu.cn/open-apis/im/v1/messages"
            f"?receive_id_type={receive_id_type}"
        )

    def send_payload(
        self, target: str, message: str, *, thread_id: str | None = None
    ) -> dict[str, Any]:
        payload = {
            "receive_id": target,
            "msg_type": "text",
            "content": json.dumps({"text": message}, ensure_ascii=False),
        }
        if thread_id:
            payload["thread_id"] = thread_id
        return payload
