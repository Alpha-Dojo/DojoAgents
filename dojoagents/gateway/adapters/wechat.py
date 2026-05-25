from __future__ import annotations

import asyncio
import base64
import contextlib
import hashlib
import inspect
import json
import secrets
import struct
import time
from pathlib import Path
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
EP_GET_UPDATES = "ilink/bot/getupdates"
ITEM_TEXT = 1
MSG_TYPE_BOT = 2
MSG_STATE_FINISH = 2
ERR_CONTEXT_EXPIRED = -14
WECHAT_TEXT_LIMIT = 1900


def _account_dir() -> Path:
    path = Path("~/.dojo/wechat/accounts").expanduser()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _account_file(account_id: str) -> Path:
    return _account_dir() / f"{account_id}.json"


def _sync_buf_path(account_id: str) -> Path:
    return _account_dir() / f"{account_id}.sync.json"


def _context_tokens_path(account_id: str) -> Path:
    return _account_dir() / f"{account_id}.context-tokens.json"


def save_wechat_account(
    *,
    account_id: str,
    token: str,
    base_url: str,
    user_id: str = "",
) -> None:
    payload = {
        "token": token,
        "base_url": base_url,
        "user_id": user_id,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path = _account_file(account_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def load_wechat_account(account_id: str) -> dict[str, Any] | None:
    path = _account_file(account_id)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


class WeChatAdapter(BaseGatewayAdapter):
    platform = "wechat"
    label = "WeChat"

    def __init__(
        self,
        config: dict[str, Any] | None = None,
        *,
        http_client: Any | None = None,
    ) -> None:
        super().__init__(config, http_client=http_client)
        self._message_handler: Any | None = None
        self._poll_task: asyncio.Task | None = None

        self._account_id = str(self.config.get("account_id") or "").strip()
        token = self.config.get("token") or self.config.get("bot_token")

        # Load account credentials if token is missing
        if self._account_id and not token:
            persisted = load_wechat_account(self._account_id)
            if persisted:
                if "token" in self.config:
                    self.config["token"] = persisted.get("token")
                else:
                    self.config["bot_token"] = persisted.get("token")
                self.config["base_url"] = persisted.get("base_url") or self.config.get("base_url")

        # Load get_updates_buf from file if exists, otherwise config.
        self._updates_buf = ""
        if self._account_id:
            sync_path = _sync_buf_path(self._account_id)
            if sync_path.exists():
                try:
                    data = json.loads(sync_path.read_text(encoding="utf-8"))
                    self._updates_buf = str(data["get_updates_buf"])
                except Exception:
                    pass
        if not self._updates_buf:
            self._updates_buf = str(self.config.get("get_updates_buf") or "")

        self._deduplicator = MessageDeduplicator()

        # Initialize ContextTokenStore with account-specific path
        context_store_path = self.config.get("context_token_store")
        if not context_store_path:
            if self._account_id:
                context_store_path = str(_context_tokens_path(self._account_id))
            else:
                context_store_path = "~/.dojo/wechat/context_tokens.json"
        self.context_tokens = ContextTokenStore(context_store_path)

    def set_message_handler(self, handler: Any) -> None:
        self._message_handler = handler

    async def start(self) -> None:
        await super().start()
        # Save credentials to ~/.dojo/wechat/accounts/
        if self._account_id:
            token = self.config.get("token") or self.config.get("bot_token") or ""
            base_url = self.config.get("base_url") or ILINK_BASE_URL
            user_id = self.config.get("home_channel") or ""
            if token:
                save_wechat_account(
                    account_id=self._account_id,
                    token=token,
                    base_url=base_url,
                    user_id=user_id,
                )
        self.context_tokens.load()
        if self.config.get("polling_enabled", True):
            self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        await super().stop()
        if self._poll_task is not None:
            self._poll_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poll_task
            self._poll_task = None
        self.context_tokens.save()

    def save_update_buf(self, get_updates_buf: str) -> None:
        self.save_update_state(get_updates_buf=get_updates_buf)

    def save_update_state(
        self,
        *,
        get_updates_buf: str,
        sync_buf: str | None = None,
    ) -> None:
        if self._account_id:
            path = _sync_buf_path(self._account_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {"get_updates_buf": get_updates_buf}
            if sync_buf is not None:
                payload["sync_buf"] = sync_buf
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def normalize_message(self, payload: dict[str, Any]) -> GatewayEvent:
        return GatewayEvent(
            platform=self.platform,
            text=str(payload.get("Content", payload.get("content", ""))),
            target=str(payload.get("FromUserName", payload.get("from", ""))),
            user_id=str(payload.get("FromUserName", payload.get("from", ""))),
            message_id=str(payload.get("MsgId", payload.get("msgid", ""))),
            raw=payload,
        )

    @staticmethod
    def _response_success(response: dict[str, Any]) -> bool:
        err = _errcode(response)
        if err is not None:
            return err == 0
        return BaseGatewayAdapter._response_success(response)


    async def _poll_loop(self) -> None:
        interval = float(self.config.get("poll_interval_seconds", 1.0))
        while self._running:
            try:
                await self._poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(float(self.config.get("poll_error_sleep", 3.0)))
                continue
            await asyncio.sleep(interval)

    async def _poll_once(self) -> None:
        response = await self._post_ilink(
            EP_GET_UPDATES,
            {
                "get_updates_buf": self._updates_buf,
                "base_info": {"channel_version": CHANNEL_VERSION},
            },
        )
        messages = _extract_update_messages(response)
        new_updates_buf = _require_string(response, "get_updates_buf")
        sync_buf = _require_string(response, "sync_buf")
        if new_updates_buf != self._updates_buf:
            self.save_update_state(
                get_updates_buf=new_updates_buf,
                sync_buf=sync_buf,
            )
            self._updates_buf = new_updates_buf
        for message in messages:
            await self._process_update(message)

    async def _process_update(self, update: dict[str, Any]) -> None:
        payload = self._payload_from_update(update)
        if payload is None:
            return
        message_id = str(payload.get("MsgId") or "")
        text = str(payload.get("Content") or "")
        if self._deduplicator.seen(message_id, text):
            return
        peer_id = str(payload.get("FromUserName") or "")
        context_token = _require_string(update, "context_token")
        if peer_id and context_token:
            self.context_tokens.set(peer_id, context_token)
        if self._message_handler is None:
            return
        result = self._message_handler(payload)
        if inspect.isawaitable(result):
            await result

    def _payload_from_update(self, update: dict[str, Any]) -> dict[str, Any] | None:
        message = update
        text = _extract_text_item(message)
        attachments = _extract_media_items(message)
        if not text.strip() and not attachments:
            return None
        from_user_id = _require_string(message, "from_user_id")
        to_user_id = _require_string(message, "to_user_id")
        message_id = _require_string(message, "message_id")
        group_id = _require_string(message, "group_id")
        session_id = _require_string(message, "session_id")
        context_token = _require_string(message, "context_token")
        target = group_id if group_id else from_user_id
        if not target:
            return None
        return {
            "Content": text,
            "FromUserName": target,
            "ToUserName": to_user_id,
            "MsgId": message_id,
            "context_token": context_token,
            "attachments": attachments,
            "room_id": group_id,
            "session_id": session_id,
            "message_type": message["message_type"],
            "message_state": message["message_state"],
            "create_time_ms": message["create_time_ms"],
            "_wechat_sender": from_user_id,
            "_ilink_raw": update,
        }

    def send_url(self, target: str) -> str:
        base_url = str(self.config.get("base_url") or ILINK_BASE_URL).rstrip("/")
        return f"{base_url}/{EP_SEND_MESSAGE}"

    def send_payload(
        self, target: str, message: str, *, thread_id: str | None = None
    ) -> dict[str, Any]:
        import uuid
        client_id = thread_id if (thread_id and thread_id != target) else f"dojo-wechat-{uuid.uuid4().hex}"
        return {
            "msg": {
                "from_user_id": "",
                "to_user_id": target,
                "client_id": client_id,
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
        chunks = _split_text_for_wechat_delivery(_format_wechat_text(message))
        last_result: GatewaySendResult | None = None
        for chunk in chunks:
            last_result = await self._send_text_chunk(
                target,
                chunk,
                thread_id=thread_id,
            )
            if not last_result.success:
                return last_result
        return last_result or GatewaySendResult(success=False, error="message must not be empty")

    async def _send_text_chunk(
        self,
        target: str,
        message: str,
        *,
        thread_id: str | None = None,
    ) -> GatewaySendResult:
        payload = self.send_payload(target, message, thread_id=thread_id)
        context_token = self.context_tokens.get(target)
        if context_token:
            payload.setdefault("msg", {})["context_token"] = context_token
        try:
            response = await self._post_ilink(EP_SEND_MESSAGE, payload)
            if _errcode(response) == ERR_CONTEXT_EXPIRED and context_token:
                self.context_tokens.pop(target)
                payload.setdefault("msg", {}).pop("context_token", None)
                response = await self._post_ilink(EP_SEND_MESSAGE, payload)
        except Exception as exc:
            return GatewaySendResult(success=False, error=str(exc))
        return GatewaySendResult(
            success=self._response_success(response),
            message_id=self._response_message_id(response),
            raw_response=response,
        )


    async def _post_ilink(
        self,
        endpoint: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        base_url = str(self.config.get("base_url") or ILINK_BASE_URL).rstrip("/")
        url = f"{base_url}/{endpoint.lstrip('/')}"
        token = self.config.get("token") or self.config.get("bot_token")
        headers = _ilink_headers(str(token or ""), _json_dumps(payload))
        return await self.http_client.post_json(url, payload, headers=headers)


class ContextTokenStore:
    def __init__(self, path: str) -> None:
        self.path = Path(path).expanduser()
        self.tokens: dict[str, str] = {}

    def load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if isinstance(data, dict):
            self.tokens = {str(key): str(value) for key, value in data.items()}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.tokens, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def get(self, peer_id: str) -> str | None:
        return self.tokens.get(peer_id)

    def set(self, peer_id: str, token: str) -> None:
        self.tokens[peer_id] = token
        self.save()

    def pop(self, peer_id: str) -> None:
        self.tokens.pop(peer_id, None)
        self.save()


class MessageDeduplicator:
    def __init__(self, ttl_seconds: float = 300.0) -> None:
        self.ttl_seconds = ttl_seconds
        self._seen: dict[str, float] = {}

    def seen(self, message_id: str, text: str) -> bool:
        now = time.time()
        self._seen = {
            key: timestamp
            for key, timestamp in self._seen.items()
            if now - timestamp < self.ttl_seconds
        }
        digest = hashlib.md5(text.encode("utf-8")).hexdigest()
        key = f"{message_id}:{digest}"
        if key in self._seen:
            return True
        self._seen[key] = now
        return False


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


def _errcode(response: dict[str, Any]) -> int | None:
    for key in ("errcode", "ret", "code"):
        value = response.get(key)
        if value is not None:
            try:
                return int(value)
            except (TypeError, ValueError):
                pass
    return None



def _require_string(payload: dict[str, Any], field_name: str) -> str:
    value = payload.get(field_name)
    if value is None:
        raise ValueError(f"WeChat field '{field_name}' must not be null")
    return str(value)


def _extract_update_messages(response: dict[str, Any]) -> list[dict[str, Any]]:
    messages = response.get("msgs") or []
    return [message for message in messages if isinstance(message, dict)]


def _extract_text_item(message: dict[str, Any]) -> str:
    for item in message["item_list"]:
        if item["type"] != ITEM_TEXT:
            continue
        return str(item["text_item"]["text"])
    return ""


def _extract_media_items(message: dict[str, Any]) -> list[dict[str, Any]]:
    media: list[dict[str, Any]] = []
    for item in message["item_list"]:
        if item["type"] == ITEM_TEXT:
            continue
        media.append(
            {
                "type": item["type"],
                "raw": item,
            }
        )
    return media


def _format_wechat_text(message: str) -> str:
    lines: list[str] = []
    for line in str(message).splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            title = stripped.lstrip("#").strip()
            lines.append(f"【{title}】" if title else "")
        else:
            lines.append(line.rstrip())
    return "\n".join(lines).strip()


def _split_text_for_wechat_delivery(
    message: str,
    *,
    limit: int = WECHAT_TEXT_LIMIT,
) -> list[str]:
    text = message.strip()
    if not text:
        return []
    chunks: list[str] = []
    current: list[str] = []
    size = 0
    for line in text.splitlines(keepends=True):
        if len(line) > limit:
            if current:
                chunks.append("".join(current).strip())
                current = []
                size = 0
            for index in range(0, len(line), limit):
                chunks.append(line[index : index + limit].strip())
            continue
        if current and size + len(line) > limit:
            chunks.append("".join(current).strip())
            current = []
            size = 0
        current.append(line)
        size += len(line)
    if current:
        chunks.append("".join(current).strip())
    return [chunk for chunk in chunks if chunk]
