from __future__ import annotations

import json
from typing import Any


def _parse_json_content(content: str) -> Any:
    text = content.strip()
    if not text or text[:1] not in ("{", "["):
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _infer_portfolio_resource_changes(
    tool_name: str,
    data: Any,
    arguments: dict[str, Any],
) -> list[dict[str, Any]]:
    if not tool_name.startswith("portfolio_write_"):
        return []

    action = tool_name.removeprefix("portfolio_write_")
    portfolio_id = None
    if isinstance(data, dict):
        portfolio_id = data.get("id") or data.get("portfolio_id")
    if not portfolio_id:
        portfolio_id = arguments.get("portfolio_id")

    change = {
        "resource": "portfolio",
        "action": action,
    }
    if portfolio_id:
        change["portfolio_id"] = str(portfolio_id)
    return [change]


class ToolResultPresenterRegistry:
    def normalize(self, tool_name: str, raw: dict[str, Any]) -> dict[str, Any]:
        result = dict(raw)
        data = result.get("data")
        if data is None and isinstance(result.get("content"), str):
            data = _parse_json_content(result["content"])
            if data is not None:
                result["data"] = data

        result.setdefault("viz_blocks", [])
        result.setdefault("artifacts", [])
        result.setdefault("resource_changes", [])

        if not result["resource_changes"]:
            inferred = _infer_portfolio_resource_changes(
                tool_name,
                data,
                result.get("arguments") or {},
            )
            if inferred:
                result["resource_changes"] = inferred

        return result
