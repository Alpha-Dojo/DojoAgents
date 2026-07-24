from __future__ import annotations

from dojoagents.agent.models import ToolResult
from dojoagents.harnesses.built_in.financial.policies.sector_context import (
    extract_sector_best_match,
    get_sector_best_match,
    record_sector_search_in_invocation,
    repair_sector_tool_arguments,
)


def _best_match_payload() -> dict:
    return {
        "sector_path_id": "1/2/3",
        "level1_id": "1",
        "level2_id": "2",
        "level3_id": "3",
    }


def test_extract_sector_best_match_from_tool_result() -> None:
    result = ToolResult(
        call_id="c1",
        name="search_sector_taxonomy",
        ok=True,
        content="",
        data={"query": "软件", "best_match": _best_match_payload()},
    )
    assert extract_sector_best_match(result) == _best_match_payload()


def test_record_sector_search_in_invocation_stores_best_match() -> None:
    invocation_state: dict = {}
    result = ToolResult(
        call_id="c1",
        name="search_sector_taxonomy",
        ok=True,
        content="",
        data={"query": "电子元器件", "best_match": _best_match_payload()},
    )
    record_sector_search_in_invocation(invocation_state, result)
    assert get_sector_best_match(invocation_state) == _best_match_payload()
    assert invocation_state["_dojo_sector_search_query"] == "电子元器件"


def test_repair_sector_tool_arguments_replaces_guessed_path() -> None:
    invocation_state: dict = {"_dojo_sector_best_match": _best_match_payload()}
    repaired = repair_sector_tool_arguments(
        "filter_sector_constituents",
        {"sector_path_id": "1/12/120", "market": "us"},
        invocation_state,
    )
    assert repaired["sector_path_id"] == "1/2/3"
    assert repaired["level1_id"] == "1"
    assert repaired["market"] == "us"


def test_repair_sector_tool_arguments_keeps_matching_ids() -> None:
    invocation_state: dict = {"_dojo_sector_best_match": _best_match_payload()}
    original = {
        "sector_path_id": "1/2/3",
        "level1_id": "1",
        "level2_id": "2",
        "level3_id": "3",
        "market": "cn",
    }
    repaired = repair_sector_tool_arguments(
        "get_sector_analysis",
        dict(original),
        invocation_state,
    )
    assert repaired == original


def test_repair_sector_tool_arguments_injects_missing_ids() -> None:
    invocation_state: dict = {"_dojo_sector_best_match": _best_match_payload()}
    repaired = repair_sector_tool_arguments(
        "get_sector_analysis",
        {"scope": "L3"},
        invocation_state,
    )
    assert repaired["sector_path_id"] == "1/2/3"
    assert repaired["scope"] == "L3"
