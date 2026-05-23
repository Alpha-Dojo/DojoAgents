from __future__ import annotations

import base64
import json
import secrets
import struct
from typing import Any

from dojoagents.gateway.adapters.base import (
    BaseGatewayAdapter,
    GatewayEvent,
    GatewaySendResult,
)


ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
ILINK_APP_ID = "bot"
ILINK_APP_CLIENT_VERSION = (2 << 16) | (2 << 8) | 0
CHANNEL_VERSION = "2.2.0"
EP_SEND_MESSAGE = "ilink/bot/sendmessage"
ITEM_TEXT = 1
MSG_TYPE_BOT = 2
MSG_STATE_FINISH = 2


class WeChatAdapter(BaseGatewayAdapter):
    platform = "wechat"
    label = "WeChat"

    def normalize_message(self, payload: dict[str, Any]) -> GatewayEvent:
        return GatewayEvent(
            platform=self.platform,
            text=str(payload.get("Content", payload.get("content", ""))),
            target=str(payload.get("FromUserName", payload.get("from", ""))),
            user_id=str(payload.get("FromUserName", payload.get("from", ""))),
            message_id=str(payload.get("MsgId", payload.get("msgid", ""))),
            raw=payload,
        )

    def send_url(self, target: str) -> str:
        base_url = str(self.config.get("base_url") or ILINK_BASE_URL).rstrip("/")
        return f"{base_url}/{EP_SEND_MESSAGE}"

    def send_payload(
        self, target: str, message: str, *, thread_id: str | None = None
    ) -> dict[str, Any]:
        return {
            "msg": {
                "from_user_id": "",
                "to_user_id": target,
                "client_id": thread_id or target,
                "message_type": MSG_TYPE_BOT,
                "message_state": MSG_STATE_FINISH,
                "item_list": [{"type": ITEM_TEXT, "text_item": {"text": message}}],
            },
            "base_info": {"channel_version": CHANNEL_VERSION},
        }

    def auth_headers(self) -> dict[str, str]:
        token = self.config.get("token") or self.config.get("bot_token")
        payload = self.send_payload("__dojo_target__", "__dojo_message__")
        # BaseGatewayAdapter calls auth_headers before send_payload, so compute
        # Content-Length again in send() below where the real target/message is known.
        headers = _ilink_headers(str(token or ""), _json_dumps(payload))
        headers.pop("Content-Length", None)
        return headers

    async def send(
        self,
        target: str,
        message: str,
        *,
        thread_id: str | None = None,
    ) -> GatewaySendResult:
        if not message.strip():
            return GatewaySendResult(success=False, error="message must not be empty")
        url = self.send_url(target)
        payload = self.send_payload(target, message, thread_id=thread_id)
        token = self.config.get("token") or self.config.get("bot_token")
        headers = _ilink_headers(str(token or ""), _json_dumps(payload))
        try:
            response = await self.http_client.post_json(url, payload, headers=headers)
        except Exception as exc:
            return GatewaySendResult(success=False, error=str(exc))
        return GatewaySendResult(
            success=self._response_success(response),
            message_id=self._response_message_id(response),
            raw_response=response,
        )


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _random_wechat_uin() -> str:
    value = struct.unpack(">I", secrets.token_bytes(4))[0]
    return base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def _ilink_headers(token: str, body: str) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Content-Length": str(len(body.encode("utf-8"))),
        "X-WECHAT-UIN": _random_wechat_uin(),
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers
