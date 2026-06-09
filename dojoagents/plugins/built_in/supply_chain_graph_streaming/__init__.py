from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

LOGGER = logging.getLogger("dojo_plugins.built_in.supply_chain_graph_streaming")

StreamEventCallback = Callable[[dict[str, Any]], None]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _event(event_type: str, run_id: str, session_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": event_type,
        "run_id": run_id,
        "session_id": session_id,
        "time": _utc_now_iso(),
        "payload": payload,
    }


def _emit(callback: StreamEventCallback | None, event: dict[str, Any]) -> None:
    if callback is None:
        return
    try:
        callback(event)
    except Exception as exc:
        LOGGER.warning("Stream event callback failed: %s", exc)


def _structured_stream_emitter(
    *,
    callback: StreamEventCallback | None,
    event_type: str,
    run_id: str,
    session_id: str,
    payload: dict[str, Any],
    **_: Any,
) -> dict[str, Any]:
    event = _event(event_type, run_id, session_id, payload)
    _emit(callback, event)
    return event


def register(ctx) -> None:
    ctx.register_stream_event_emitter(_structured_stream_emitter)
