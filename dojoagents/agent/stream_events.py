from __future__ import annotations

import json
from typing import Any


def _json_size(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return len(str(value))


def _sanitize_tool_arguments(args: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in (args or {}).items():
        size = _json_size(value)
        if size > 1200:
            sanitized[key] = {"omitted": True, "reason": "large_argument", "size": size}
        else:
            sanitized[key] = value
    return sanitized


def _tool_result_stats(metadata: dict[str, Any]) -> dict[str, int]:
    stats = metadata.get("result_stats")
    if isinstance(stats, dict):
        return {
            "entities": int(stats.get("entities") or 0),
            "edges": int(stats.get("edges") or 0),
        }

    graph = metadata.get("graph")
    if isinstance(graph, dict):
        entities = graph.get("entities")
        edges = graph.get("edges")
        return {
            "entities": len(entities) if isinstance(entities, list) else 0,
            "edges": len(edges) if isinstance(edges, list) else 0,
        }

    return {"entities": 0, "edges": 0}


def _compact_tool_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key, value in metadata.items():
        if key in {"graph", "tool_meta"}:
            continue
        size = _json_size(value)
        if size <= 2000:
            compact[key] = value
        else:
            compact[key] = {"omitted": True, "reason": "large_metadata", "size": size}
    return compact


def _valid_graph_payload(metadata: dict[str, Any]) -> dict[str, Any] | None:
    if metadata.get("graph_visible") is not True or metadata.get("graph_contract_valid") is not True:
        return None

    graph = metadata.get("graph")
    if not isinstance(graph, dict):
        return None

    entities = graph.get("entities")
    edges = graph.get("edges")
    if not isinstance(entities, list) or not isinstance(edges, list):
        return None

    entity_ids: set[str] = set()
    for entity in entities:
        if not isinstance(entity, dict):
            return None
        node_id = str(entity.get("node_id") or "").strip()
        if not node_id:
            return None
        entity_ids.add(node_id)

    for edge in edges:
        if not isinstance(edge, dict):
            return None
        from_id = str(edge.get("from") or "").strip()
        to_id = str(edge.get("to") or "").strip()
        if not from_id or not to_id or from_id not in entity_ids or to_id not in entity_ids:
            return None

    return graph


def tool_started_payload(tool_name: str, tool_call_id: str, args: dict[str, Any]) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "tool_call_id": tool_call_id,
        "arguments": _sanitize_tool_arguments(args),
    }


def tool_completed_payload(
    tool_name: str,
    tool_call_id: str,
    status: str,
    duration_ms: int,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "tool_call_id": tool_call_id,
        "status": status,
        "duration_ms": duration_ms,
        "result_stats": _tool_result_stats(metadata),
        "metadata": _compact_tool_metadata(metadata),
    }


def graph_payload(tool_name: str, tool_call_id: str, metadata: dict[str, Any]) -> dict[str, Any] | None:
    graph = _valid_graph_payload(metadata)
    if graph is None:
        return None

    return {
        "tool_name": tool_name,
        "tool_call_id": tool_call_id,
        "graph": graph,
        "result_stats": _tool_result_stats(metadata),
        "tool_meta": metadata.get("tool_meta", {}),
    }
