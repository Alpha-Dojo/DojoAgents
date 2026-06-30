from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any, cast

from strands.types.exceptions import SessionException
from strands.types.session import Session, SessionAgent, SessionMessage
from strands.session.session_repository import SessionRepository

SESSION_PREFIX = "session_"
AGENT_PREFIX = "agent_"
MESSAGE_PREFIX = "message_"
MULTI_AGENT_PREFIX = "multi_agent_"


def _validate_identifier(value: str, kind: str) -> str:
    try:
        from strands import _identifier

        identifier = getattr(_identifier.Identifier, kind.upper())
        return cast(str, _identifier.validate(value, identifier))
    except Exception as exc:
        if not value or "/" in value or "\\" in value or value in {".", ".."} or ".." in Path(value).parts:
            raise ValueError(f"invalid {kind} id: {value!r}") from exc
        return value


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


class DojoSessionRepository(SessionRepository):
    """Strands SessionRepository backed by the Strands file layout."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _session_path(self, session_id: str) -> Path:
        session_id = _validate_identifier(session_id, "session")
        return self.root / f"{SESSION_PREFIX}{session_id}"

    def _agent_path(self, session_id: str, agent_id: str) -> Path:
        agent_id = _validate_identifier(agent_id, "agent")
        return self._session_path(session_id) / "agents" / f"{AGENT_PREFIX}{agent_id}"

    def _message_path(self, session_id: str, agent_id: str, message_id: int) -> Path:
        if not isinstance(message_id, int):
            raise ValueError("message id must be an integer")
        return self._agent_path(session_id, agent_id) / "messages" / f"{MESSAGE_PREFIX}{message_id}.json"

    def _multi_agent_path(self, session_id: str, multi_agent_id: str) -> Path:
        multi_agent_id = _validate_identifier(multi_agent_id, "agent")
        return self._session_path(session_id) / "multi_agents" / f"{MULTI_AGENT_PREFIX}{multi_agent_id}"

    @staticmethod
    def _read_json(path: Path, key: str) -> dict[str, Any]:
        try:
            return cast(dict[str, Any], json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError as exc:
            raise SessionException(f"{key}: invalid JSON") from exc
        except OSError as exc:
            raise SessionException(f"{key}: unable to read") from exc

    @staticmethod
    def _write_json(path: Path, data: dict[str, Any]) -> None:
        _atomic_write_json(path, data)

    def create_session(self, session: Session, **kwargs: Any) -> Session:
        session_dir = self._session_path(session.session_id)
        session_file = session_dir / "session.json"
        if session_file.exists():
            raise SessionException(f"Session {session.session_id} already exists")
        (session_dir / "agents").mkdir(parents=True, exist_ok=True)
        (session_dir / "multi_agents").mkdir(parents=True, exist_ok=True)
        self._write_json(session_file, session.to_dict())
        return session

    def read_session(self, session_id: str, **kwargs: Any) -> Session | None:
        session_file = self._session_path(session_id) / "session.json"
        if not session_file.exists():
            return None
        return Session.from_dict(self._read_json(session_file, session_id))

    def delete_session(self, session_id: str, **kwargs: Any) -> None:
        session_dir = self._session_path(session_id)
        if not session_dir.exists():
            raise SessionException(f"Session {session_id} does not exist")
        shutil.rmtree(session_dir)

    def create_agent(self, session_id: str, session_agent: SessionAgent, **kwargs: Any) -> None:
        agent_dir = self._agent_path(session_id, session_agent.agent_id)
        (agent_dir / "messages").mkdir(parents=True, exist_ok=True)
        self._write_json(agent_dir / "agent.json", session_agent.to_dict())

    def read_agent(self, session_id: str, agent_id: str, **kwargs: Any) -> SessionAgent | None:
        agent_file = self._agent_path(session_id, agent_id) / "agent.json"
        if not agent_file.exists():
            return None
        return SessionAgent.from_dict(self._read_json(agent_file, f"{session_id}/{agent_id}"))

    def update_agent(self, session_id: str, session_agent: SessionAgent, **kwargs: Any) -> None:
        previous = self.read_agent(session_id, session_agent.agent_id)
        if previous is None:
            raise SessionException(f"Agent {session_agent.agent_id} in session {session_id} does not exist")
        session_agent.created_at = previous.created_at
        self._write_json(self._agent_path(session_id, session_agent.agent_id) / "agent.json", session_agent.to_dict())

    def create_message(
        self,
        session_id: str,
        agent_id: str,
        session_message: SessionMessage,
        **kwargs: Any,
    ) -> None:
        self._write_json(
            self._message_path(session_id, agent_id, session_message.message_id),
            session_message.to_dict(),
        )

    def read_message(self, session_id: str, agent_id: str, message_id: int, **kwargs: Any) -> SessionMessage | None:
        message_path = self._message_path(session_id, agent_id, message_id)
        if not message_path.exists():
            return None
        return SessionMessage.from_dict(self._read_json(message_path, f"{session_id}/{agent_id}/{message_id}"))

    def update_message(
        self,
        session_id: str,
        agent_id: str,
        session_message: SessionMessage,
        **kwargs: Any,
    ) -> None:
        previous = self.read_message(session_id, agent_id, session_message.message_id)
        if previous is None:
            raise SessionException(f"Message {session_message.message_id} does not exist")
        session_message.created_at = previous.created_at
        self._write_json(self._message_path(session_id, agent_id, session_message.message_id), session_message.to_dict())

    def list_messages(
        self,
        session_id: str,
        agent_id: str,
        limit: int | None = None,
        offset: int = 0,
        **kwargs: Any,
    ) -> list[SessionMessage]:
        messages_dir = self._agent_path(session_id, agent_id) / "messages"
        if not messages_dir.exists():
            raise SessionException(f"Messages directory missing from agent: {agent_id} in session {session_id}")
        indexed: list[tuple[int, Path]] = []
        for path in messages_dir.iterdir():
            if not path.name.startswith(MESSAGE_PREFIX) or path.suffix != ".json":
                continue
            indexed.append((int(path.stem[len(MESSAGE_PREFIX) :]), path))
        paths = [path for _, path in sorted(indexed)]
        if limit is not None:
            paths = paths[offset : offset + limit]
        else:
            paths = paths[offset:]
        return [SessionMessage.from_dict(self._read_json(path, f"{session_id}/{agent_id}/{path.name}")) for path in paths]

    def list_session_ids(self) -> list[str]:
        ids: list[str] = []
        for path in self.root.iterdir():
            if path.is_dir() and path.name.startswith(SESSION_PREFIX):
                ids.append(path.name[len(SESSION_PREFIX) :])
        return sorted(ids)

    def create_multi_agent(self, session_id: str, multi_agent: Any, **kwargs: Any) -> None:
        multi_agent_dir = self._multi_agent_path(session_id, multi_agent.id)
        multi_agent_dir.mkdir(parents=True, exist_ok=True)
        self._write_json(multi_agent_dir / "multi_agent.json", multi_agent.serialize_state())

    def read_multi_agent(self, session_id: str, multi_agent_id: str, **kwargs: Any) -> dict[str, Any] | None:
        path = self._multi_agent_path(session_id, multi_agent_id) / "multi_agent.json"
        if not path.exists():
            return None
        return self._read_json(path, f"{session_id}/{multi_agent_id}")

    def update_multi_agent(self, session_id: str, multi_agent: Any, **kwargs: Any) -> None:
        path = self._multi_agent_path(session_id, multi_agent.id) / "multi_agent.json"
        if not path.exists():
            raise SessionException(f"MultiAgent state {multi_agent.id} in session {session_id} does not exist")
        self._write_json(path, multi_agent.serialize_state())
