from __future__ import annotations

import asyncio
import json
import shutil
import time
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from strands.session import FileSessionManager, RepositorySessionManager
from strands.types.exceptions import SessionException
from strands.types.session import SessionMessage

from dojoagents.agent.models import AgentResponse, ChatRequest
from dojoagents.agent.session_models import (
    DojoProjectedMessage,
    DojoSessionExportResult,
    DojoSessionListResult,
    DojoSessionMessagesResult,
    DojoSessionRunHandle,
    DojoSessionSummary,
)
from dojoagents.agent.session_repository import DojoSessionRepository
from dojoagents.logging import get_logger

LOGGER = get_logger(__name__)


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, data: dict[str, Any]) -> None:
    from dojoagents.agent.session_repository import _atomic_write_json

    _atomic_write_json(path, data)


def _append_jsonl(path: Path, row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def _text_from_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict):
                continue
            if "text" in block:
                parts.append(str(block.get("text") or ""))
            elif "toolResult" in block:
                result = block.get("toolResult") or {}
                for item in result.get("content") or []:
                    if isinstance(item, dict) and "text" in item:
                        parts.append(str(item.get("text") or ""))
        return "".join(parts)
    return str(content or "")


class DojoAgentSessionManager:
    def __init__(
        self,
        *,
        root: str | Path,
        memory_manager: Any = None,
        agent_id: str = "dojo-agent",
        provider: str = "dojo_repository",
        sync_memory: bool = True,
        export_default_dir: str = "~/Desktop/dojo-chat-export",
        enabled: bool = True,
    ) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.memory_manager = memory_manager
        self.agent_id = agent_id
        self.provider = provider
        self.sync_memory = sync_memory
        self.export_default_dir = export_default_dir
        self.enabled = enabled
        self.repository = DojoSessionRepository(self.root)

    def for_strands(self, session_id: str, *, agent_id: str | None = None):
        if not self.enabled:
            return None
        if self.provider == "strands_file":
            return FileSessionManager(session_id=session_id, storage_dir=str(self.root))
        return RepositorySessionManager(
            session_id=session_id,
            session_repository=self.repository,
        )

    def session_exists(self, session_id: str, *, agent_id: str | None = None) -> bool:
        resolved_agent = agent_id or self.agent_id
        try:
            return self.repository.read_agent(session_id, resolved_agent) is not None
        except (SessionException, ValueError):
            return False

    def message_from_text(self, role: str, text: str, message_id: int) -> SessionMessage:
        return SessionMessage.from_message({"role": role, "content": [{"text": text}]}, message_id)

    def _session_dir(self, session_id: str) -> Path:
        return self.repository._session_path(session_id)

    def _sidecar_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "dojo_session.json"

    def _turns_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "dojo_turns.jsonl"

    def _memory_path(self, session_id: str) -> Path:
        return self._session_dir(session_id) / "dojo_memory.json"

    def _load_sidecar(self, session_id: str) -> dict[str, Any]:
        path = self._sidecar_path(session_id)
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            LOGGER.exception("Failed to read session sidecar: %s", path)
            return {}

    def _save_sidecar(self, session_id: str, data: dict[str, Any]) -> None:
        _atomic_write(self._sidecar_path(session_id), data)

    def _message_count(self, session_id: str, agent_id: str) -> int:
        try:
            return len(self.repository.list_messages(session_id, agent_id))
        except SessionException:
            return 0

    def begin_run_sync(
        self,
        request: ChatRequest,
        *,
        model: str,
        run_id: str | None = None,
        agent_id: str | None = None,
    ) -> DojoSessionRunHandle:
        resolved_agent = agent_id or self.agent_id
        turn_id = str(request.metadata.get("turn_id") or f"turn-{uuid.uuid4().hex[:8]}")
        now = _utc()
        existing = self._load_sidecar(request.session_id)
        data = {
            "schema_version": 1,
            "session_id": request.session_id,
            "agent_id": resolved_agent,
            "title": existing.get("title") or request.message.strip().replace("\n", " ")[:48],
            "user_id": request.user_id,
            "channel": request.channel,
            "model": model,
            "locale": str(request.metadata.get("locale") or existing.get("locale") or "zh"),
            "created_at": existing.get("created_at") or now,
            "updated_at": now,
            "message_count": self._message_count(request.session_id, resolved_agent),
            "turn_count": int(existing.get("turn_count") or 0),
            "run_count": int(existing.get("run_count") or 0) + 1,
            "last_run_id": run_id,
            "status": "running",
            "archived": bool(existing.get("archived", False)),
            "token_state": dict(existing.get("token_state") or {}),
            "memory_state": dict(existing.get("memory_state") or {}),
        }
        self._session_dir(request.session_id).mkdir(parents=True, exist_ok=True)
        self._save_sidecar(request.session_id, data)
        return DojoSessionRunHandle(
            session_id=request.session_id,
            agent_id=resolved_agent,
            turn_id=turn_id,
            run_id=run_id,
            model=model,
        )

    async def begin_run(self, request: ChatRequest, *, model: str, run_id: str | None = None) -> DojoSessionRunHandle:
        return self.begin_run_sync(request, model=model, run_id=run_id)

    def _latest_pair(self, session_id: str, agent_id: str) -> tuple[str, str, int | None]:
        try:
            messages = self.repository.list_messages(session_id, agent_id)
        except SessionException:
            return "", "", None
        user_text = ""
        assistant_text = ""
        latest_id: int | None = None
        for message in reversed(messages):
            raw = message.to_message()
            role = str(raw.get("role") or "")
            text = _text_from_content(raw.get("content"))
            if latest_id is None:
                latest_id = message.message_id
            if role == "assistant" and not assistant_text:
                assistant_text = text
            elif role == "user" and assistant_text and not user_text:
                user_text = text
                break
        return user_text, assistant_text, latest_id

    def finish_run_sync(
        self,
        handle: DojoSessionRunHandle,
        response: AgentResponse,
        *,
        events: list[dict[str, Any]] | None = None,
    ) -> None:
        sidecar = self._load_sidecar(handle.session_id)
        token_snapshot = response.metadata.get("session_tokens")
        usage = response.metadata.get("usage") or {}
        if isinstance(token_snapshot, dict):
            sidecar["token_state"] = token_snapshot
        sidecar["message_count"] = self._message_count(handle.session_id, handle.agent_id)
        sidecar["turn_count"] = int(sidecar.get("turn_count") or 0) + 1
        sidecar["updated_at"] = _utc()
        sidecar["status"] = "idle"
        self._save_sidecar(handle.session_id, sidecar)
        _append_jsonl(
            self._turns_path(handle.session_id),
            {
                "schema_version": 1,
                "turn_id": handle.turn_id,
                "run_id": handle.run_id,
                "events": list(events or []),
                "tool_trace": list(response.metadata.get("tool_trace") or []),
                "usage": usage,
                "created_at": _utc(),
                "updated_at": _utc(),
            },
        )
        if self.sync_memory:
            self._sync_memory_sync(handle)

    async def finish_run(
        self,
        handle: DojoSessionRunHandle,
        response: AgentResponse,
        *,
        events: list[dict[str, Any]] | None = None,
    ) -> None:
        self.finish_run_sync(handle, response, events=events)

    def fail_run_sync(self, handle: DojoSessionRunHandle, message: str, *, code: str = "runtime_error") -> None:
        sidecar = self._load_sidecar(handle.session_id)
        sidecar["status"] = "error"
        sidecar["updated_at"] = _utc()
        sidecar["last_error"] = {"message": message, "code": code}
        self._save_sidecar(handle.session_id, sidecar)

    async def fail_run(self, handle: DojoSessionRunHandle, message: str, *, code: str = "runtime_error") -> None:
        self.fail_run_sync(handle, message, code=code)

    def cancel_run_sync(self, handle: DojoSessionRunHandle) -> None:
        sidecar = self._load_sidecar(handle.session_id)
        sidecar["status"] = "cancelled"
        sidecar["updated_at"] = _utc()
        self._save_sidecar(handle.session_id, sidecar)

    async def cancel_run(self, handle: DojoSessionRunHandle) -> None:
        self.cancel_run_sync(handle)

    def _sync_memory_sync(self, handle: DojoSessionRunHandle) -> None:
        if self.memory_manager is None:
            return
        user_text, assistant_text, latest_id = self._latest_pair(handle.session_id, handle.agent_id)
        if not user_text or not assistant_text:
            return
        existing_turns = getattr(self.memory_manager, "turns", None)
        if isinstance(existing_turns, list) and existing_turns:
            last = existing_turns[-1]
            if isinstance(last, dict) and last.get("session_id") == handle.session_id and last.get("user") == user_text and last.get("assistant") == assistant_text:
                return
        result = self.memory_manager.sync_turn(user_text, assistant_text, session_id=handle.session_id)
        if asyncio.iscoroutine(result):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                asyncio.run(result)
            else:
                loop.create_task(result)
        _atomic_write(
            self._memory_path(handle.session_id),
            {
                "schema_version": 1,
                "session_id": handle.session_id,
                "last_synced_message_id": latest_id,
                "updated_at": _utc(),
            },
        )

    def _project(self, message: SessionMessage) -> DojoProjectedMessage:
        raw = message.to_message()
        return DojoProjectedMessage(
            message_id=message.message_id,
            role=str(raw.get("role") or ""),
            content=_text_from_content(raw.get("content")),
            created_at=message.created_at,
            updated_at=message.updated_at,
            raw=raw,
        )

    def _summary_for(self, session_id: str) -> DojoSessionSummary:
        sidecar = self._load_sidecar(session_id)
        agent_id = str(sidecar.get("agent_id") or self.agent_id)
        message_count = self._message_count(session_id, agent_id)
        return DojoSessionSummary(
            session_id=session_id,
            agent_id=agent_id,
            title=str(sidecar.get("title") or session_id),
            user_id=str(sidecar.get("user_id") or "anonymous"),
            channel=str(sidecar.get("channel") or "dashboard"),
            model=str(sidecar.get("model") or ""),
            locale=str(sidecar.get("locale") or "zh"),
            created_at=str(sidecar.get("created_at") or ""),
            updated_at=str(sidecar.get("updated_at") or ""),
            message_count=message_count,
            turn_count=int(sidecar.get("turn_count") or 0),
            run_count=int(sidecar.get("run_count") or 0),
            last_run_id=sidecar.get("last_run_id"),
            status=str(sidecar.get("status") or "idle"),
            archived=bool(sidecar.get("archived", False)),
            token_state=dict(sidecar.get("token_state") or {}),
            memory_state=dict(sidecar.get("memory_state") or {}),
        )

    def list_sessions_sync(
        self,
        *,
        limit: int = 50,
        cursor: str | None = None,
        include_archived: bool = False,
    ) -> DojoSessionListResult:
        summaries = [self._summary_for(session_id) for session_id in self.repository.list_session_ids()]
        if not include_archived:
            summaries = [summary for summary in summaries if not summary.archived]
        summaries.sort(key=lambda item: item.updated_at or item.created_at, reverse=True)
        return DojoSessionListResult(sessions=summaries[:limit], next_cursor=None)

    async def list_sessions(self, **kwargs: Any) -> DojoSessionListResult:
        return self.list_sessions_sync(**kwargs)

    def get_session_sync(self, session_id: str) -> DojoSessionSummary | None:
        if self.repository.read_session(session_id) is None and not self._sidecar_path(session_id).exists():
            return None
        return self._summary_for(session_id)

    async def get_session(self, session_id: str) -> DojoSessionSummary | None:
        return self.get_session_sync(session_id)

    def get_messages_sync(
        self,
        session_id: str,
        *,
        agent_id: str | None = None,
        limit: int = 200,
        offset: int = 0,
    ) -> DojoSessionMessagesResult:
        resolved_agent = agent_id or self._load_sidecar(session_id).get("agent_id") or self.agent_id
        messages = self.repository.list_messages(session_id, str(resolved_agent), limit=limit, offset=offset)
        return DojoSessionMessagesResult(
            session_id=session_id,
            agent_id=str(resolved_agent),
            messages=[self._project(message) for message in messages],
            next_offset=(offset + len(messages) if len(messages) == limit else None),
        )

    async def get_messages(self, session_id: str, **kwargs: Any) -> DojoSessionMessagesResult:
        return self.get_messages_sync(session_id, **kwargs)

    def archive_session_sync(self, session_id: str) -> bool:
        if self.get_session_sync(session_id) is None:
            return False
        sidecar = self._load_sidecar(session_id)
        sidecar["archived"] = True
        sidecar["updated_at"] = _utc()
        self._save_sidecar(session_id, sidecar)
        return True

    async def archive_session(self, session_id: str) -> bool:
        return self.archive_session_sync(session_id)

    def export_all_sync(self, request: dict[str, Any] | None = None) -> DojoSessionExportResult:
        payload = dict(request or {})
        root = Path(str(payload.get("output_dir") or self.export_default_dir)).expanduser().resolve()
        if root.exists() and root.is_file():
            raise ValueError(f"Export output_dir is a file: {root}")
        root.mkdir(parents=True, exist_ok=True)
        export_dir = root / f"chat-export-{time.strftime('%Y%m%d-%H%M%S')}"
        export_dir.mkdir()
        (export_dir / "transcripts").mkdir()
        files: list[str] = []
        sessions = self.list_sessions_sync(include_archived=bool(payload.get("include_archived", False))).sessions
        all_rows: list[dict[str, Any]] = []
        for summary in sessions:
            messages = self.get_messages_sync(summary.session_id, agent_id=summary.agent_id).messages
            transcript_lines = [f"# {summary.title or summary.session_id}", ""]
            for message in messages:
                row = {
                    "session_id": summary.session_id,
                    "agent_id": summary.agent_id,
                    "message_id": message.message_id,
                    "role": message.role,
                    "content": message.content,
                    "created_at": message.created_at,
                    "raw": message.raw,
                }
                all_rows.append(row)
                transcript_lines.append(f"## {message.role} {message.message_id}")
                transcript_lines.append("")
                transcript_lines.append(message.content)
                transcript_lines.append("")
            transcript_path = export_dir / "transcripts" / f"{summary.session_id}.md"
            transcript_path.write_text("\n".join(transcript_lines), encoding="utf-8")
            files.append(str(transcript_path.relative_to(export_dir)))
        sessions_path = export_dir / "sessions.json"
        sessions_path.write_text(json.dumps([asdict(summary) for summary in sessions], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        files.append("sessions.json")
        messages_path = export_dir / "messages.jsonl"
        messages_path.write_text(
            "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in all_rows),
            encoding="utf-8",
        )
        files.append("messages.jsonl")
        manifest_path = export_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "created_at": _utc(),
                    "session_count": len(sessions),
                    "message_count": len(all_rows),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        files.append("manifest.json")
        strands_dir = export_dir / "strands"
        strands_dir.mkdir()
        for session_id in self.repository.list_session_ids():
            src = self._session_dir(session_id)
            dst = strands_dir / src.name
            if src.exists():
                shutil.copytree(src, dst, dirs_exist_ok=True)
        files.append("strands")
        return DojoSessionExportResult(
            ok=True,
            export_dir=str(export_dir),
            session_count=len(sessions),
            message_count=len(all_rows),
            files=files,
        )

    async def export_all(self, request: dict[str, Any] | None = None) -> DojoSessionExportResult:
        return self.export_all_sync(request)
