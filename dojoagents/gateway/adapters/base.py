from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

from dojoagents.agent.models import ChatRequest


@dataclass(frozen=True)
class GatewayEvent:
    platform: str
    text: str
    target: str
    user_id: str
    message_id: str = ""
    raw: dict[str, Any] = field(default_factory=dict)
    thread_id: str | None = None

    def to_chat_request(self, *, session_id: str | None = None) -> ChatRequest:
        return ChatRequest(
            message=self.text,
            user_id=self.user_id,
            session_id=session_id or self.session_key,
            channel=self.platform,
            metadata={
                "target": self.target,
                "message_id": self.message_id,
                "thread_id": self.thread_id,
            },
        )

    @property
    def session_key(self) -> str:
        return f"{self.platform}:{self.target}:{self.user_id}"


@dataclass(frozen=True)
class GatewaySendResult:
    success: bool
    message_id: str | None = None
    error: str | None = None
    raw_response: Any = None


class AsyncHttpClient(Protocol):
    async def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        ...


class HttpxAsyncHttpClient:
    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._client = client
        self._timeout = timeout

    async def post_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        request_headers = {"Content-Type": "application/json", **(headers or {})}
        if self._client is not None:
            response = await self._client.post(
                url,
                content=body.encode("utf-8"),
                headers=request_headers,
            )
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(
                    url,
                    content=body.encode("utf-8"),
                    headers=request_headers,
                )
        response.raise_for_status()
        if not response.content:
            return {}
        parsed = response.json()
        if isinstance(parsed, dict):
            return parsed
        return {"data": parsed}


class BaseGatewayAdapter:
    platform = "base"
    label = "Base"

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        http_client: AsyncHttpClient | None = None,
    ) -> None:
        self.config = config or {}
        self.http_client = http_client or HttpxAsyncHttpClient()
        self._running = False

    async def start(self) -> None:
        self._running = True

    async def stop(self) -> None:
        self._running = False

    def normalize_message(self, payload: dict[str, Any]) -> GatewayEvent:
        raise NotImplementedError

    async def send(
        self,
        target: str,
        message: str,
        *,
        thread_id: str | None = None,
    ) -> GatewaySendResult:
        url = self.send_url(target)
        payload = self.send_payload(target, message, thread_id=thread_id)
        headers = self.auth_headers()
        try:
            response = await self.http_client.post_json(url, payload, headers=headers)
        except Exception as exc:
            return GatewaySendResult(success=False, error=str(exc))
        return GatewaySendResult(
            success=self._response_success(response),
            message_id=self._response_message_id(response),
            raw_response=response,
        )

    def send_url(self, target: str) -> str:
        raise NotImplementedError

    def send_payload(
        self, target: str, message: str, *, thread_id: str | None = None
    ) -> dict[str, Any]:
        raise NotImplementedError

    def auth_headers(self) -> dict[str, str]:
        token = self.config.get("bot_token") or self.config.get("access_token")
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}

    @staticmethod
    def _response_success(response: dict[str, Any]) -> bool:
        if "ok" in response:
            return bool(response["ok"])
        if "errcode" in response:
            return int(response["errcode"]) == 0
        if "code" in response:
            return int(response["code"]) == 0
        return True

    @staticmethod
    def _response_message_id(response: dict[str, Any]) -> str | None:
        for key in ("message_id", "msgid", "id", "open_message_id"):
            value = response.get(key)
            if value is not None:
                return str(value)
        data = response.get("data")
        if isinstance(data, dict):
            for key in ("message_id", "msgid", "id"):
                value = data.get(key)
                if value is not None:
                    return str(value)
        return None


def text_from_json_content(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("text") or value.get("content") or "")
    if not isinstance(value, str):
        return ""
    stripped = value.strip()
    if not stripped:
        return ""
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return value
    if isinstance(parsed, dict):
        return str(parsed.get("text") or parsed.get("content") or value)
    return value
