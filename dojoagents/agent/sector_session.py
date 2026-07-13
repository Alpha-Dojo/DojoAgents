from __future__ import annotations

from typing import Any

from dojoagents.agent.models import ToolResult
from dojoagents.dashboard.services.domain_api import (
    _looks_like_index_guess,
    _parse_sector_path_id,
)

_SECTOR_SEARCH_TOOL = "search_sector_taxonomy"
_SECTOR_FOLLOWUP_TOOLS = frozenset({"get_sector_analysis", "filter_sector_constituents"})
_SECTOR_ID_KEYS = ("sector_path_id", "level1_id", "level2_id", "level3_id")
_INVOCATION_BEST_MATCH_KEY = "_dojo_sector_best_match"
_INVOCATION_SEARCH_QUERY_KEY = "_dojo_sector_search_query"


def extract_sector_best_match(result: ToolResult | None) -> dict[str, Any] | None:
    if result is None or not result.ok or result.name != _SECTOR_SEARCH_TOOL:
        return None
    data = result.data
    if not isinstance(data, dict):
        return None
    best_match = data.get("best_match")
    if not isinstance(best_match, dict):
        return None
    if not str(best_match.get("sector_path_id") or "").strip():
        return None
    return dict(best_match)


def record_sector_search_in_invocation(
    invocation_state: dict[str, Any],
    result: ToolResult | None,
) -> None:
    best_match = extract_sector_best_match(result)
    if best_match is None:
        return
    invocation_state[_INVOCATION_BEST_MATCH_KEY] = best_match
    data = result.data if result is not None and isinstance(result.data, dict) else {}
    query = str(data.get("query") or "").strip()
    if query:
        invocation_state[_INVOCATION_SEARCH_QUERY_KEY] = query


def get_sector_best_match(invocation_state: dict[str, Any]) -> dict[str, Any] | None:
    best_match = invocation_state.get(_INVOCATION_BEST_MATCH_KEY)
    if not isinstance(best_match, dict):
        return None
    if not str(best_match.get("sector_path_id") or "").strip():
        return None
    return dict(best_match)


def _args_match_best_match(args: dict[str, Any], best_match: dict[str, Any]) -> bool:
    arg_path = str(args.get("sector_path_id") or "").strip()
    best_path = str(best_match.get("sector_path_id") or "").strip()
    if arg_path and best_path and arg_path == best_path:
        return True
    for key in ("level1_id", "level2_id", "level3_id"):
        arg_value = str(args.get(key) or "").strip()
        best_value = str(best_match.get(key) or "").strip()
        if arg_value and best_value and arg_value != best_value:
            return False
    has_arg_ids = any(str(args.get(key) or "").strip() for key in ("level1_id", "level2_id", "level3_id"))
    has_best_ids = any(str(best_match.get(key) or "").strip() for key in ("level1_id", "level2_id", "level3_id"))
    return has_arg_ids and has_best_ids


def _sector_args_need_repair(args: dict[str, Any], best_match: dict[str, Any]) -> bool:
    if _args_match_best_match(args, best_match):
        return False

    path_id = str(args.get("sector_path_id") or "").strip()
    if path_id:
        parsed = _parse_sector_path_id(path_id)
        if parsed is None:
            return True
        if _looks_like_index_guess(*parsed):
            return True

    level1_id = str(args.get("level1_id") or "").strip()
    level2_id = str(args.get("level2_id") or "").strip()
    level3_id = str(args.get("level3_id") or "").strip()
    if level1_id and level2_id and level3_id and _looks_like_index_guess(level1_id, level2_id, level3_id):
        return True

    if not any(str(args.get(key) or "").strip() for key in _SECTOR_ID_KEYS):
        return True

    return False


def merge_sector_best_match(args: dict[str, Any], best_match: dict[str, Any]) -> dict[str, Any]:
    merged = dict(args)
    for key in _SECTOR_ID_KEYS:
        value = best_match.get(key)
        if value:
            merged[key] = value
    return merged


def repair_sector_tool_arguments(
    tool_name: str,
    args: dict[str, Any],
    invocation_state: dict[str, Any],
) -> dict[str, Any]:
    if tool_name not in _SECTOR_FOLLOWUP_TOOLS:
        return args
    best_match = get_sector_best_match(invocation_state)
    if best_match is None:
        return args
    if not _sector_args_need_repair(args, best_match):
        return args
    return merge_sector_best_match(args, best_match)
