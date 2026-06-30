from __future__ import annotations

import json
from typing import Any

from dojoagents.logging import get_logger
from dojoagents.tools.agent_viz import build_viz_blocks

LOGGER = get_logger(__name__)

_LIST_MAPPABLE_TOOLS = {
    "search_company_ticker",
    "screen_market_stocks",
    "filter_sector_constituents",
    "portfolio_read_list",
    "portfolio_read_search",
}
_MAX_AUTO_VIZ_BLOCKS = 6


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

        if not result["viz_blocks"]:
            try:
                viz_input: dict[str, Any] | None = None
                if isinstance(data, dict):
                    viz_input = data
                elif isinstance(data, list) and tool_name in _LIST_MAPPABLE_TOOLS:
                    viz_input = {"items": data}
                if viz_input is not None:
                    blocks = build_viz_blocks(
                        viz_input,
                        kind="auto",
                        source_tool=tool_name,
                        truncated=bool(result.get("truncated", False)),
                    )
                    if len(blocks) > _MAX_AUTO_VIZ_BLOCKS:
                        blocks = blocks[:_MAX_AUTO_VIZ_BLOCKS]
                        result["truncated"] = True
                    result["viz_blocks"] = blocks
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("Failed to auto-build viz blocks for %s: %s", tool_name, exc)

        if not result["resource_changes"]:
            inferred = _infer_portfolio_resource_changes(
                tool_name,
                data,
                result.get("arguments") or {},
            )
            if inferred:
                result["resource_changes"] = inferred

        return result
