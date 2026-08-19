from __future__ import annotations

from typing import Any

from dojoagents.agent.models import ToolResult

_SECTOR_SEARCH_TOOL = "search_sector_taxonomy"
_SECTOR_FOLLOWUP_TOOLS = frozenset({"filter_sector_constituents"})
_SECTOR_ID_KEYS = ("sector_path_id", "level1_id", "level2_id", "level3_id")
_INVOCATION_BEST_MATCH_KEY = "_dojo_sector_best_match"
_INVOCATION_SEARCH_QUERY_KEY = "_dojo_sector_search_query"
_INVOCATION_SEARCH_HIT_PATHS_KEY = "_dojo_sector_search_hit_paths"


def _parse_sector_path_id(value: str) -> tuple[str, str, str] | None:
    text = str(value or "").strip()
    if not text or text.count("/") != 2:
        return None
    parts = tuple(part.strip() for part in text.split("/", 2))
    return parts if all(parts) else None


def _format_path(level1_id: str, level2_id: str, level3_id: str) -> str:
    return f"{level1_id}/{level2_id}/{level3_id}"


def _resolved_arg_path(args: dict[str, Any]) -> str | None:
    path_id = str(args.get("sector_path_id") or "").strip()
    if path_id:
        parsed = _parse_sector_path_id(path_id)
        if parsed is None:
            return None
        return _format_path(*parsed)
    level1_id = str(args.get("level1_id") or "").strip()
    level2_id = str(args.get("level2_id") or "").strip()
    level3_id = str(args.get("level3_id") or "").strip()
    if level1_id and level2_id and level3_id:
        return _format_path(level1_id, level2_id, level3_id)
    return None


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


def _extract_search_hit_paths(data: dict[str, Any]) -> tuple[str, ...]:
    paths: list[str] = []
    seen: set[str] = set()
    for item in data.get("items") or ():
        if not isinstance(item, dict):
            continue
        path_id = str(item.get("sector_path_id") or "").strip()
        if not path_id:
            l1 = str(item.get("level1_id") or "").strip()
            l2 = str(item.get("level2_id") or "").strip()
            l3 = str(item.get("level3_id") or "").strip()
            if l1 and l2 and l3:
                path_id = _format_path(l1, l2, l3)
        if path_id and path_id not in seen:
            seen.add(path_id)
            paths.append(path_id)
    return tuple(paths)


def record_sector_search_in_invocation(
    invocation_state: dict[str, Any],
    result: ToolResult | None,
) -> None:
    if result is None or not result.ok or result.name != _SECTOR_SEARCH_TOOL:
        return
    data = result.data if isinstance(result.data, dict) else {}
    hit_paths = _extract_search_hit_paths(data)
    if hit_paths:
        invocation_state[_INVOCATION_SEARCH_HIT_PATHS_KEY] = hit_paths
    query = str(data.get("query") or "").strip()
    if query:
        invocation_state[_INVOCATION_SEARCH_QUERY_KEY] = query
    best_match = extract_sector_best_match(result)
    if best_match is not None:
        invocation_state[_INVOCATION_BEST_MATCH_KEY] = best_match


def get_sector_best_match(invocation_state: dict[str, Any]) -> dict[str, Any] | None:
    best_match = invocation_state.get(_INVOCATION_BEST_MATCH_KEY)
    if not isinstance(best_match, dict):
        return None
    if not str(best_match.get("sector_path_id") or "").strip():
        return None
    return dict(best_match)


def get_sector_search_hit_paths(invocation_state: dict[str, Any]) -> frozenset[str]:
    raw = invocation_state.get(_INVOCATION_SEARCH_HIT_PATHS_KEY)
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(str(item).strip() for item in raw if str(item).strip())


def _args_match_best_match(args: dict[str, Any], best_match: dict[str, Any]) -> bool:
    arg_path = _resolved_arg_path(args)
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


def _sector_args_need_repair(
    args: dict[str, Any],
    best_match: dict[str, Any],
    hit_paths: frozenset[str],
) -> bool:
    """Rescue missing/invalid/unknown paths only — never clobber a search hit."""
    if _args_match_best_match(args, best_match):
        return False

    path_id = str(args.get("sector_path_id") or "").strip()
    if path_id and _parse_sector_path_id(path_id) is None:
        return True

    resolved = _resolved_arg_path(args)
    if resolved is None:
        return True

    # Well-formed path that appeared in the latest taxonomy search: keep it.
    if resolved in hit_paths:
        return False

    # Well-formed but not in search hits: only rewrite when we have hit context
    # (unknown relative to the search). Without hits, do not overwrite digits.
    if hit_paths:
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
    hit_paths = get_sector_search_hit_paths(invocation_state)
    if not _sector_args_need_repair(args, best_match, hit_paths):
        return args
    return merge_sector_best_match(args, best_match)
