from __future__ import annotations

import asyncio
import os
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml

from dojoagents.agent.models import ChatRequest
from dojoagents.agent.models import AgentResponse
from dojoagents.agent.runtime import Runtime
from dojoagents.config.loader import ConfigStore
from dojoagents.gateway.adapters import create_default_gateway_registry
from dojoagents.gateway.adapters.base import GatewayEvent, GatewaySendResult
from dojoagents.gateway.registry import GatewayRegistry
from dojoagents.logging import LOGGER


_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9][A-Za-z0-9_\-]{12,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{20,}\b"),
    re.compile(r"(?i)\b(Bearer\s+)[A-Za-z0-9._\-]{20,}\b"),
)


from dojoagents.gateway.state import GatewaySession, GatewaySessionStore
from dojoagents.gateway.pairing import PairingStore


class GatewayRunner:
    """Long-lived gateway runtime.

    Hermes' runner owns platform lifecycle, session routing, policy checks, and
    reply delivery. This class keeps same boundary for DojoAgents, but stays
    small: adapters normalize inbound payloads, runner calls agent, runner sends
    final reply through live adapter.
    """

    def __init__(
        self,
        *,
        runtime: Any | None = None,
        registry: GatewayRegistry | None = None,
        gateway_config: dict[str, Any] | None = None,
        config_store: ConfigStore | None = None,
    ) -> None:
        self.config_store = config_store or ConfigStore()
        self.runtime = runtime or Runtime.from_config_store(self.config_store)
        self.registry = registry or create_default_gateway_registry()
        self.gateway_config = gateway_config or asdict(self.runtime.config.gateway)
        self.session_store = GatewaySessionStore(
            self.gateway_config.get("session_store", "~/.dojo/gateway/state.db")
        )
        self.pairing_store = PairingStore(
            self.gateway_config.get("pairing_store", "~/.dojo/gateway/pairing.json")
        )
        self.adapters: dict[str, Any] = {}
        self.platform_status: dict[str, dict[str, Any]] = {}
        self._session_locks: dict[str, asyncio.Lock] = {}
        self._pending_events: dict[str, list[GatewayEvent]] = {}
        self._reconnect_tasks: dict[str, asyncio.Task] = {}
        self._started_at: float | None = None
        self._state = "initialized"
        self._stop_event = asyncio.Event()
        self._hooks: dict[str, list[Any]] = {}
        self._agent_cache: dict[str, Any] = {}
        self._pending_approvals: dict[str, dict[str, Any]] = {}
        self._pid_file = Path(
            self.gateway_config.get("pid_file", "~/.dojo/gateway/gateway.pid")
        ).expanduser()
        self._clean_marker = Path(
            self.gateway_config.get("clean_marker", "~/.dojo/gateway/.clean_shutdown")
        ).expanduser()

    async def start(self) -> bool:
        self._state = "starting"
        self._started_at = time.time()
        self._acquire_pid_lock()
        self._recover_sessions()
        hooks = self.gateway_config.get("hooks", {})
        for platform, hook_config in hooks.items():
            if not isinstance(hook_config, dict) or not hook_config.get("enabled", True):
                continue
            await self._connect_platform(platform, hook_config)
        self._state = "running"
        await self._emit("gateway:startup", self.status())
        await self._send_startup_notifications()
        return True

    async def stop(self) -> None:
        self._state = "stopping"
        await self._emit("gateway:shutdown", self.status())
        for task in self._reconnect_tasks.values():
            task.cancel()
        self._reconnect_tasks.clear()
        for platform, adapter in list(self.adapters.items()):
            try:
                await adapter.stop()
                self._set_platform_status(platform, "stopped")
            except Exception as exc:  # pragma: no cover - defensive shutdown
                self._set_platform_status(platform, "error", error=str(exc))
        self.adapters.clear()
        self._write_clean_marker()
        self._release_pid_lock()
        self._state = "stopped"
        self._stop_event.set()

    async def wait_for_shutdown(self) -> None:
        await self._stop_event.wait()

    def status(self) -> dict[str, Any]:
        return {
            "state": self._state,
            "started_at": self._started_at,
            "platforms": self.platform_status,
            "active_sessions": len(
                [lock for lock in self._session_locks.values() if lock.locked()]
            ),
            "queued_events": sum(len(queue) for queue in self._pending_events.values()),
            "sessions": {
                key: {
                    "status": session.status,
                    "platform": session.platform,
                    "target": session.target,
                    "user_id": session.user_id,
                    "model_override": session.model_override,
                    "resume_pending": session.resume_pending,
                }
                for key, session in self.session_store.sessions.items()
            },
        }

    def register_hook(self, event: str, handler: Any) -> None:
        self._hooks.setdefault(event, []).append(handler)

    async def handle_webhook(
        self, platform: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        adapter = self.adapters.get(platform)
        if adapter is None:
            hook_config = self._hook_config(platform)
            if hook_config is None:
                return {"accepted": False, "reason": "unknown_platform"}
            await self._connect_platform(platform, hook_config)
            adapter = self.adapters.get(platform)
            if adapter is None:
                return {"accepted": False, "reason": "platform_unavailable"}

        event = adapter.normalize_message(payload)
        if not self._authorized(platform, event):
            if not self._is_group_event(event):
                try:
                    user_name = payload.get("user_name") or event.user_id
                    code = self.pairing_store.generate_code(platform, event.user_id, user_name)
                    await adapter.send(
                        event.target,
                        f"Unauthorized. To pair this account, use pairing code: {code}",
                        thread_id=event.thread_id,
                    )
                except Exception:
                    pass
            return {"accepted": False, "reason": "unauthorized"}
        if not event.text.strip():
            return {"accepted": False, "reason": "empty_message"}

        session_key = event.session_key
        self.session_store.ensure(event)
        command_result = await self._handle_command(adapter, event)
        if command_result is not None:
            return command_result
        lock = self._session_locks.setdefault(session_key, asyncio.Lock())
        if lock.locked():
            self._pending_events.setdefault(session_key, []).append(event)
            return {"accepted": True, "queued": True, "session_key": session_key}

        return await self._run_event(adapter, event, lock)

    async def send(
        self,
        platform: str,
        target: str,
        message: str,
        *,
        thread_id: str | None = None,
    ) -> dict[str, Any]:
        adapter = self.adapters.get(platform)
        if adapter is None:
            hook_config = self._hook_config(platform)
            if hook_config is None:
                return asdict(
                    GatewaySendResult(success=False, error=f"Unknown platform: {platform}")
                )
            await self._connect_platform(platform, hook_config)
            adapter = self.adapters.get(platform)
        if adapter is None:
            return asdict(
                GatewaySendResult(success=False, error=f"Platform unavailable: {platform}")
            )
        result = await adapter.send(target, message, thread_id=thread_id)
        return asdict(result)

    async def deliver(self, delivery: dict[str, Any], message: str) -> dict[str, Any]:
        return await self.send(
            str(delivery.get("platform") or delivery.get("adapter") or ""),
            str(delivery.get("target") or delivery.get("channel") or ""),
            message,
            thread_id=delivery.get("thread_id"),
        )

    async def _connect_platform(self, platform: str, hook_config: dict[str, Any]) -> None:
        self._set_platform_status(platform, "connecting")
        try:
            LOGGER.info(f"Connecting to platform: {platform}")
            adapter = self.registry.create_adapter(platform, hook_config)
            setter = getattr(adapter, "set_message_handler", None)
            if setter is not None:
                setter(lambda payload, _platform=platform: self.handle_webhook(_platform, payload))
            self.adapters[platform] = adapter
            await adapter.start()
            LOGGER.info(f"Connected to platform: {platform}")
            self._set_platform_status(platform, "connected")
        except Exception as exc:
            self.adapters.pop(platform, None)
            self._set_platform_status(platform, "retrying", error=str(exc))
            self._schedule_reconnect(platform)

    async def _drain_pending(self, session_key: str) -> None:
        queue = self._pending_events.get(session_key)
        if not queue:
            return
        event = queue.pop(0)
        if not queue:
            self._pending_events.pop(session_key, None)
        adapter = self.adapters.get(event.platform)
        if adapter is None:
            return
        lock = self._session_locks.setdefault(session_key, asyncio.Lock())
        await self._run_event(adapter, event, lock)

    def _authorized(self, platform: str, event: GatewayEvent) -> bool:
        config = self._hook_config(platform) or {}
        if config.get("allow_all") or config.get("allow_all_users"):
            return True
        if platform == "wechat":
            return self._authorized_wechat(event, config)
        allowed = _coerce_list(config.get("allow_from") or config.get("allowed_users"))
        if not allowed:
            static_ok = True
        else:
            static_ok = event.user_id in allowed or event.target in allowed

        if static_ok:
            return True

        return self.pairing_store.is_approved(platform, event.user_id)

    def _authorized_wechat(self, event: GatewayEvent, config: dict[str, Any]) -> bool:
        if self._is_group_event(event):
            group_policy = str(config.get("group_policy", "disabled")).lower()
            if group_policy == "disabled":
                return False
            if group_policy == "open":
                return True
            if group_policy == "allowlist":
                allowed = _coerce_list(
                    config.get("group_allow_from")
                    or config.get("allow_from")
                    or config.get("allowed_users")
                )
                return event.target in allowed
            return False

        dm_policy = str(config.get("dm_policy", "open")).lower()
        if dm_policy == "disabled":
            return False
        if dm_policy == "open":
            return True
        if dm_policy == "allowlist":
            allowed = _coerce_list(config.get("allow_from") or config.get("allowed_users"))
            return event.user_id in allowed or event.target in allowed
        if dm_policy == "pairing":
            return self.pairing_store.is_approved(event.platform, event.user_id)
        return False

    def _is_group_event(self, event: GatewayEvent) -> bool:
        return bool(
            event.raw.get("room_id")
            or event.raw.get("chat_room_id")
            or str(event.target).endswith("@chatroom")
        )

    async def _handle_command(
        self, adapter: Any, event: GatewayEvent
    ) -> dict[str, Any] | None:
        text = event.text.strip()
        if not text.startswith("/"):
            return None
        name, _, arg = text[1:].partition(" ")
        name = name.lower()
        if name in {"reset", "new"}:
            self._pending_events.pop(event.session_key, None)
            self._agent_cache.pop(event.session_key, None)
            self.session_store.clear(event.session_key)
            await adapter.send(event.target, "Session reset", thread_id=event.thread_id)
            return {"accepted": True, "command": name}
        if name == "status":
            await adapter.send(
                event.target,
                _redact_text(str(self.status())),
                thread_id=event.thread_id,
            )
            return {"accepted": True, "command": "status"}
        if name == "model":
            session = self.session_store.ensure(event)
            model = arg.strip() or None
            self.session_store.set_model(session.key, model)
            await adapter.send(
                event.target,
                f"Model override: {model or 'default'}",
                thread_id=event.thread_id,
            )
            return {"accepted": True, "command": "model"}
        if name == "queue":
            queued = GatewayEvent(
                platform=event.platform,
                text=arg.strip(),
                target=event.target,
                user_id=event.user_id,
                raw=event.raw,
                thread_id=event.thread_id,
            )
            self._pending_events.setdefault(event.session_key, []).append(queued)
            await adapter.send(event.target, "Queued", thread_id=event.thread_id)
            return {"accepted": True, "command": "queue"}
        if name in {"approve", "deny"}:
            code = arg.strip()
            if code:
                if name == "approve":
                    try:
                        success = self.pairing_store.approve_code(event.platform, code)
                        if success:
                            msg = f"Successfully approved pairing code: {code}"
                        else:
                            msg = f"Failed to approve pairing code: {code} (not found or invalid)"
                    except Exception as e:
                        msg = f"Error approving pairing code: {str(e)}"
                else:
                    success = self.pairing_store.deny_code(event.platform, code)
                    if success:
                        msg = f"Successfully denied pairing code: {code}"
                    else:
                        msg = f"Failed to deny pairing code: {code} (not found or invalid)"
                await adapter.send(event.target, msg, thread_id=event.thread_id)
                return {"accepted": True, "command": name}

            pending = self._pending_approvals.pop(event.session_key, None)
            if pending is None:
                await adapter.send(event.target, f"{name}: no pending approval", thread_id=event.thread_id)
            else:
                pending["decision"] = name
                await adapter.send(event.target, f"{name}: {pending['command']}", thread_id=event.thread_id)
            return {"accepted": True, "command": name}
        if name == "restart":
            self._state = "restart_requested"
            await adapter.send(event.target, "Gateway restart requested", thread_id=event.thread_id)
            return {"accepted": True, "command": "restart"}
        return None

    def _hook_config(self, platform: str) -> dict[str, Any] | None:
        hooks = self.gateway_config.get("hooks", {})
        config = hooks.get(platform)
        return config if isinstance(config, dict) else None

    def _set_platform_status(
        self, platform: str, state: str, *, error: str | None = None
    ) -> None:
        self.platform_status[platform] = {
            "state": state,
            "error": error,
            "updated_at": time.time(),
        }

    def _schedule_reconnect(self, platform: str, delay: float = 30.0) -> None:
        if platform in self._reconnect_tasks:
            return

        async def _loop() -> None:
            while self._state not in {"stopping", "stopped"}:
                await asyncio.sleep(delay)
                config = self._hook_config(platform)
                if config is None:
                    return
                await self._connect_platform(platform, config)
                if platform in self.adapters:
                    return

        self._reconnect_tasks[platform] = asyncio.create_task(_loop())

    async def _run_event(
        self,
        adapter: Any,
        event: GatewayEvent,
        lock: asyncio.Lock,
    ) -> dict[str, Any]:
        async with lock:
            self.session_store.set_status(event.session_key, "active")
            self.session_store.add_transcript(event.session_key, "user", event.text)
            await self._emit("message:received", {"event": event})
            await self._send_typing(adapter, event, True)
            request = self._build_chat_request(event)
            agent = self._agent_for_session(event.session_key)

            stream_cfg = self.gateway_config.get("streaming") or {}
            consumer = None
            if stream_cfg.get("enabled", False):
                from dojoagents.gateway.stream_consumer import GatewayStreamConsumer
                consumer = GatewayStreamConsumer(
                    adapter=adapter,
                    target=event.target,
                    thread_id=event.thread_id,
                    edit_interval=stream_cfg.get("edit_interval", 0.2),
                )
                await consumer.start()
                agent.stream_delta_callback = consumer.on_delta

            try:
                response: AgentResponse = await agent.run(request)
                content = _redact_text(response.content)
                self.session_store.add_transcript(event.session_key, "assistant", content)
                
                if consumer is not None:
                    await consumer.stop()
                    if consumer.message_id is not None:
                        final_text = consumer._strip_thinking(content)
                        edit_fn = getattr(adapter, "edit", None)
                        if edit_fn is not None:
                            await edit_fn(event.target, consumer.message_id, final_text, thread_id=event.thread_id)
                        send_result = GatewaySendResult(success=True, message_id=consumer.message_id)
                    else:
                        send_result = await adapter.send(
                            event.target,
                            content,
                            thread_id=event.thread_id,
                        )
                else:
                    send_result = await adapter.send(
                        event.target,
                        content,
                        thread_id=event.thread_id,
                    )
                self.session_store.set_status(event.session_key, "idle")
            except Exception as exc:
                if consumer is not None:
                    await consumer.stop()
                content = _user_safe_error(str(exc))
                send_result = await adapter.send(
                    event.target,
                    content,
                    thread_id=event.thread_id,
                )
                self.session_store.set_status(event.session_key, "failed")
                response = AgentResponse(content=content, session_id=event.session_key)
            finally:
                if consumer is not None:
                    await consumer.stop()
                    if hasattr(agent, "stream_delta_callback"):
                        agent.stream_delta_callback = None
                await self._send_typing(adapter, event, False)
        await self._emit("message:replied", {"event": event, "response": response})
        await self._drain_pending(event.session_key)
        return {
            "accepted": True,
            "session_key": event.session_key,
            "agent_response": asdict(response),
            "send_result": asdict(send_result),
        }

    def _build_chat_request(self, event: GatewayEvent) -> ChatRequest:
        history = self.session_store.get_history(event.session_key, limit=20)
        metadata = {
            "target": event.target,
            "message_id": event.message_id,
            "thread_id": event.thread_id,
            "media": _extract_media(event.raw),
            "history": history,
        }
        session = self.session_store.sessions.get(event.session_key)
        if session and session.model_override:
            metadata["model_override"] = session.model_override
        return ChatRequest(
            message=event.text,
            user_id=event.user_id,
            session_id=event.session_key,
            channel=event.platform,
            metadata=metadata,
        )

    def _agent_for_session(self, session_key: str) -> Any:
        if session_key not in self._agent_cache:
            self._agent_cache[session_key] = self.runtime.agent
        return self._agent_cache[session_key]

    async def _send_typing(self, adapter: Any, event: GatewayEvent, enabled: bool) -> None:
        sender = getattr(adapter, "send_typing", None)
        if sender is None:
            return
        await sender(event.target, enabled, thread_id=event.thread_id)

    async def request_approval(
        self, session_key: str, command: str, *, description: str = "dangerous command"
    ) -> None:
        self._pending_approvals[session_key] = {
            "command": command,
            "description": description,
            "created_at": time.time(),
        }

    async def _send_startup_notifications(self) -> None:
        for platform, adapter in self.adapters.items():
            config = self._hook_config(platform) or {}
            if not config.get("gateway_restart_notification", False):
                continue
            home = config.get("home_channel")
            if home:
                await adapter.send(str(home), "Gateway started")

    async def _emit(self, event: str, payload: dict[str, Any]) -> None:
        for handler in self._hooks.get(event, []):
            result = handler(payload)
            if asyncio.iscoroutine(result):
                await result

    def _recover_sessions(self) -> None:
        clean = self._clean_marker.exists()
        if clean:
            self._clean_marker.unlink(missing_ok=True)
            return
        for session in self.session_store.sessions.values():
            if session.status == "active":
                session.resume_pending = True
                session.status = "suspended"
        self.session_store.save()

    def _acquire_pid_lock(self) -> None:
        self._pid_file.parent.mkdir(parents=True, exist_ok=True)
        if self._pid_file.exists():
            try:
                pid = int(self._pid_file.read_text(encoding="utf-8").strip())
            except ValueError:
                pid = 0
            if pid and pid != os.getpid() and _pid_alive(pid):
                raise RuntimeError(f"Gateway already running: {pid}")
        self._pid_file.write_text(str(os.getpid()), encoding="utf-8")

    def _release_pid_lock(self) -> None:
        try:
            if self._pid_file.read_text(encoding="utf-8").strip() == str(os.getpid()):
                self._pid_file.unlink(missing_ok=True)
        except FileNotFoundError:
            pass

    def _write_clean_marker(self) -> None:
        self._clean_marker.parent.mkdir(parents=True, exist_ok=True)
        self._clean_marker.write_text(str(time.time()), encoding="utf-8")


def _coerce_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _redact_text(text: str) -> str:
    redacted = str(text or "")
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: (match.group(1) if match.lastindex else "") + "[REDACTED]", redacted)
    return redacted


def _user_safe_error(text: str) -> str:
    redacted = _redact_text(text)
    lowered = redacted.lower()
    if "401" in lowered or "invalid api key" in lowered or "authentication" in lowered:
        return "Provider authentication failed. Check gateway logs."
    if "429" in lowered or "rate limit" in lowered:
        return "Provider rate limited request. Try later."
    if "policy" in lowered or "moderation" in lowered or "blocked" in lowered:
        return "Provider rejected request. Try rephrasing."
    return "Agent failed. Check gateway logs."


def _extract_media(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = (
        payload.get("attachments")
        or payload.get("files")
        or payload.get("media")
        or payload.get("images")
        or []
    )
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    media = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        media.append(
            {
                "type": item.get("type") or item.get("media_type") or "file",
                "url": item.get("url") or item.get("download_url") or item.get("file_url"),
                "name": item.get("name") or item.get("filename"),
                "mime_type": item.get("mime_type") or item.get("content_type"),
            }
        )
    return media


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
