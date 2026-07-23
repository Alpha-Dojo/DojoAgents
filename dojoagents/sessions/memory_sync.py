from __future__ import annotations

import json
from typing import Any

from dojoagents.memory.manager import MemoryManager
from dojoagents.sessions.models import CheckpointWrite, SessionPrincipal, TurnQuery
from dojoagents.sessions.service import SessionService


def _turn_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        if "text" in value:
            return str(value.get("text") or "")
        content = value.get("content")
        if isinstance(content, list):
            return "".join(str(block.get("text") or "") for block in content if isinstance(block, dict) and "text" in block)
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


class SessionMemorySyncWorker:
    def __init__(self, service: SessionService, memory_manager: MemoryManager) -> None:
        self.service = service
        self.memory_manager = memory_manager

    async def sync_pending(self, principal: SessionPrincipal, session_id: str) -> int:
        checkpoint = await self.service.get_checkpoint(
            principal,
            session_id,
            "memory",
            "sync_watermark",
        )
        last_sequence = 0
        checkpoint_version = None
        if checkpoint is not None:
            checkpoint_version = checkpoint.version
            if isinstance(checkpoint.payload, dict):
                last_sequence = int(checkpoint.payload.get("last_turn_sequence") or 0)
        turns = await self.service.turns(principal, session_id, TurnQuery(limit=10_000))
        pending = sorted(
            (turn for turn in turns.items if turn.sequence > last_sequence),
            key=lambda turn: turn.sequence,
        )
        synced = 0
        for turn in pending:
            context = {"idempotency_key": turn.turn_id, "turn_id": turn.turn_id}
            await self.memory_manager.sync_turn(
                _turn_text(turn.input),
                _turn_text(turn.output),
                session_id=session_id,
                idempotency_context=context,
            )
            checkpoint = await self.service.put_checkpoint(
                principal,
                CheckpointWrite(
                    session_id,
                    "memory",
                    "sync_watermark",
                    {"last_turn_id": turn.turn_id, "last_turn_sequence": turn.sequence},
                ),
                checkpoint_version,
            )
            checkpoint_version = checkpoint.version
            synced += 1
        return synced
