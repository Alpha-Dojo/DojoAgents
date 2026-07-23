from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from dojoagents.sessions.atomic import AtomicJsonStore


@dataclass
class SessionTokenState:
    schema_version: int = 1
    session_id: str = ""
    provider: str = ""
    model_id: str = ""
    model_context_window: int = 0
    session_max_tokens: int = 0
    compression_threshold_ratio: float = 0.8
    cumulative_prompt_tokens: int = 0
    cumulative_completion_tokens: int = 0
    cumulative_total_tokens: int = 0
    loop_count: int = 0
    last_prompt_tokens: int = 0
    last_completion_tokens: int = 0
    last_total_tokens: int = 0
    compression_count: int = 0
    updated_at: float = field(default_factory=time.time)

    def record_loop(self, usage: dict[str, int]) -> None:
        prompt = int(usage.get("prompt_tokens", 0))
        completion = int(usage.get("completion_tokens", 0))
        total = int(usage.get("total_tokens", prompt + completion))
        self.cumulative_prompt_tokens += prompt
        self.cumulative_completion_tokens += completion
        self.cumulative_total_tokens += total
        self.last_prompt_tokens = prompt
        self.last_completion_tokens = completion
        self.last_total_tokens = total
        self.loop_count += 1
        self.updated_at = time.time()

    def note_compression(self, estimated_prompt_tokens: int) -> None:
        self.compression_count += 1
        self.last_prompt_tokens = estimated_prompt_tokens
        self.updated_at = time.time()

    def update_context_window(self, context_window: int) -> None:
        if context_window <= 0:
            return
        self.model_context_window = context_window
        self.session_max_tokens = context_window
        self.updated_at = time.time()

    def snapshot(self) -> dict[str, Any]:
        return {
            "last_prompt_tokens": self.last_prompt_tokens,
            "last_completion_tokens": self.last_completion_tokens,
            "last_total_tokens": self.last_total_tokens,
            "session_max_tokens": self.session_max_tokens,
            "compression_threshold_ratio": self.compression_threshold_ratio,
            "utilization_ratio": (self.last_prompt_tokens / self.session_max_tokens if self.session_max_tokens > 0 else 0.0),
            "cumulative_prompt_tokens": self.cumulative_prompt_tokens,
            "cumulative_completion_tokens": self.cumulative_completion_tokens,
            "cumulative_total_tokens": self.cumulative_total_tokens,
            "compression_count": self.compression_count,
            "model_context_window": self.model_context_window,
            "loop_count": self.loop_count,
        }


class SessionTokenLedger:
    def __init__(self, root: str | Path = "~/.dojo/agents/sessions") -> None:
        self._store = AtomicJsonStore(Path(root).expanduser(), schema_version=1)
        self.state: SessionTokenState | None = None
        self._session_id = ""

    @property
    def session_id(self) -> str:
        return self._session_id

    def load_or_create(
        self,
        session_id: str,
        *,
        provider: str,
        model_id: str,
        model_context_window: int,
        session_max_tokens: int,
        compression_threshold_ratio: float,
    ) -> SessionTokenState:
        self._session_id = session_id
        path = self._store.path_for(session_id)
        if path.exists():
            raw = self._store._read_sync(path, session_id)
            if isinstance(raw, dict):
                self.state = SessionTokenState(**{**raw, "session_id": session_id})
                return self.state
        self.state = SessionTokenState(
            session_id=session_id,
            provider=provider,
            model_id=model_id,
            model_context_window=model_context_window,
            session_max_tokens=session_max_tokens,
            compression_threshold_ratio=compression_threshold_ratio,
        )
        return self.state

    def save(self) -> None:
        if self.state is None or not self._session_id:
            return
        path = self._store.path_for(self._session_id)
        self._store._write_sync(path, asdict(self.state))
