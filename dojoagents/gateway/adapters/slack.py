from __future__ import annotations

from typing import Any

from dojoagents.gateway.adapters.base import BaseGatewayAdapter, GatewayEvent


class SlackAdapter(BaseGatewayAdapter):
    platform = "slack"
    label = "Slack"

    def normalize_message(self, payload: dict[str, Any]) -> GatewayEvent:
        event = payload.get("event", payload)
        return GatewayEvent(
            platform=self.platform,
            text=str(event.get("text", "")),
            target=str(event.get("channel", "")),
            user_id=str(event.get("user", "")),
            message_id=str(event.get("ts", "")),
            thread_id=event.get("thread_ts"),
            raw=payload,
        )

    def send_url(self, target: str) -> str:
        return "https://slack.com/api/chat.postMessage"

    def send_payload(
        self, target: str, message: str, *, thread_id: str | None = None
    ) -> dict[str, Any]:
        payload = {"channel": target, "text": message}
        if thread_id:
            payload["thread_ts"] = thread_id
        return payload
