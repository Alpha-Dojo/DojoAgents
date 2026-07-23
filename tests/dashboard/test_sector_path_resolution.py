from __future__ import annotations

import pytest

from dojoagents.agent.models import ToolCall
from dojoagents.harnesses.built_in.financial.services import domain_api
from dojoagents.harnesses.built_in.financial.services.sector_store import SectorStore
from dojoagents.harnesses.built_in.financial.tools import domain_runtime as domain_tools
from dojoagents.tools.executor import ToolExecutor
from dojoagents.tools.registry import ToolRegistry
from dojoagents.tools.sandbox import SandboxPolicy
from tests.dashboard.stores.test_gateway_backed_base_stores import BaseGateway


@pytest.fixture
def sector_registry():
    async def _setup():
        gateway = BaseGateway()
        store = SectorStore(gateway)
        await store.load()
        return store

    import asyncio

    store = asyncio.run(_setup())
    return type(
        "Registry",
        (),
        {
            "sector_store": store,
            "stock_store": object(),
            "benchmark_store": object(),
            "sector_precomputed_store": None,
        },
    )()


def test_resolve_sector_path_accepts_taxonomy_ids(sector_registry) -> None:
    path = domain_api.resolve_sector_path(
        sector_registry,
        level1_id="1",
        level2_id="2",
        level3_id="3",
    )
    assert path.level3_en == "Application Software"


def test_resolve_sector_path_rejects_guessed_numeric_path_id(sector_registry) -> None:
    with pytest.raises(domain_api.SectorPathResolutionError) as exc:
        domain_api.resolve_sector_path(sector_registry, sector_path_id="1/12/120")
    assert "Rejected guessed sector_path_id" in str(exc.value)
    assert "1/12/120" in str(exc.value)


def test_build_sector_taxonomy_search_usage_forbids_constructing_ids(sector_registry) -> None:
    payload = domain_api.build_sector_taxonomy_search(sector_registry, query="软件")
    assert "do NOT construct sector_path_id" in payload["usage"]


def test_resolve_sector_path_rejects_unknown_ids(sector_registry) -> None:
    with pytest.raises(domain_api.SectorPathResolutionError) as exc:
        domain_api.resolve_sector_path(
            sector_registry,
            level1_id="9",
            level2_id="9",
            level3_id="9",
        )
    assert "Rejected guessed sector path" in str(exc.value)


def test_resolve_sector_path_accepts_level3_name(sector_registry) -> None:
    path = domain_api.resolve_sector_path(
        sector_registry,
        sector_name="应用软件",
    )
    assert path.level3_id == "3"


def test_resolve_sector_path_accepts_english_level3_name(sector_registry) -> None:
    path = domain_api.resolve_sector_path(
        sector_registry,
        level3_name="Application Software",
    )
    assert path.level2_id == "2"


def test_build_sector_taxonomy_search_returns_filter_examples(sector_registry) -> None:
    payload = domain_api.build_sector_taxonomy_search(sector_registry, query="软件")
    assert payload["count"] >= 1
    first = payload["items"][0]
    assert first["level1_id"]
    assert first["sector_path_id"] == f"{first['level1_id']}/{first['level2_id']}/{first['level3_id']}"
    assert first["next_call"]["arguments"]["level3_id"] == first["level3_id"]
    assert payload["best_match"]["level3_id"] == first["level3_id"]
    assert first["match_score"] >= 1

    payload = domain_api.build_taxonomy_tree(sector_registry)
    assert payload.get("example_l3_paths")
    assert payload.get("filter_sector_constituents_example")
    first = payload["example_l3_paths"][0]
    assert first["level1_id"] == "1"
    assert first["level2_id"] == "2"
    assert first["level3_id"] == "3"


def test_resolve_sector_path_accepts_sector_path_id(sector_registry) -> None:
    path = domain_api.resolve_sector_path(sector_registry, sector_path_id="1/2/3")
    assert path.level3_en == "Application Software"


def test_resolve_sector_path_rejects_invalid_sector_path_id(sector_registry) -> None:
    with pytest.raises(domain_api.SectorPathResolutionError, match="Invalid sector_path_id"):
        domain_api.resolve_sector_path(sector_registry, sector_path_id="bad-format")


def test_resolve_sector_path_rejects_two_segment_sector_path_id(sector_registry) -> None:
    with pytest.raises(domain_api.SectorPathResolutionError, match="three segments") as exc:
        domain_api.resolve_sector_path(sector_registry, sector_path_id="1/2")
    assert "scope=L2" in str(exc.value)


def test_resolve_sector_path_accepts_level1_level2_anchor(sector_registry) -> None:
    path = domain_api.resolve_sector_path(
        sector_registry,
        level1_id="1",
        level2_id="2",
    )
    assert path.level1_id == "1"
    assert path.level2_id == "2"
    assert path.level3_id == "3"


def test_resolve_sector_path_rejects_unknown_level1_level2_pair(sector_registry) -> None:
    with pytest.raises(domain_api.SectorPathResolutionError, match="unknown sector path: 9/9"):
        domain_api.resolve_sector_path(
            sector_registry,
            level1_id="9",
            level2_id="9",
        )


def test_expand_sector_search_queries_includes_synonyms() -> None:
    expanded = domain_api._expand_sector_search_queries("具身智能")
    assert "机器人" in expanded
    assert "robotics" in expanded


def test_enrich_indicator_valuation_merges_quote_pe_pb() -> None:
    rows = [{"std_report_date": "2026-03-31", "total_operating_revenue": 100}]
    enriched = domain_api._enrich_indicator_valuation(rows, pe=35.2, pb=8.1)
    assert enriched[-1]["pe_ttm"] == 35.2
    assert enriched[-1]["pb_ttm"] == 8.1


def test_enrich_indicator_valuation_preserves_existing_pe_pb() -> None:
    rows = [{"pe_ttm": 10.0, "pb_ttm": 2.0, "total_operating_revenue": 100}]
    enriched = domain_api._enrich_indicator_valuation(rows, pe=35.2, pb=8.1)
    assert enriched[-1]["pe_ttm"] == 10.0
    assert enriched[-1]["pb_ttm"] == 2.0


def test_reject_guessed_sector_ids_before_api_call(sector_registry) -> None:
    import asyncio

    registry = ToolRegistry()
    domain_tools.register_dashboard_domain_tools(registry, sector_registry)
    spec = registry.get("filter_sector_constituents")
    assert spec is not None

    with pytest.raises(RuntimeError, match="Rejected guessed sector path"):
        asyncio.run(spec.handler({"level1_id": "2", "level2_id": "2", "level3_id": "2", "market": "us"}))


@pytest.mark.asyncio
async def test_sector_tools_resolve_by_name(monkeypatch, sector_registry) -> None:
    async def fake_analysis(registry, path, *, scope):
        return {"scope": scope, "level3_id": path.level3_id}

    async def fake_constituents(registry, **kwargs):
        path = domain_api.resolve_sector_path(
            registry,
            level1_id=str(kwargs.get("level1_id") or ""),
            level2_id=str(kwargs.get("level2_id") or ""),
            level3_id=str(kwargs.get("level3_id") or ""),
            sector_name=kwargs.get("sector_name"),
            level1_name=kwargs.get("level1_name"),
            level2_name=kwargs.get("level2_name"),
            level3_name=kwargs.get("level3_name"),
            market=kwargs.get("market"),
        )
        return {"count": 1, "level3_id": path.level3_id, "items": []}

    monkeypatch.setattr(domain_tools, "build_sector_analysis", fake_analysis)
    monkeypatch.setattr(domain_tools, "build_sector_constituents_v1", fake_constituents)

    registry = ToolRegistry()
    domain_tools.register_dashboard_domain_tools(registry, sector_registry)
    executor = ToolExecutor(registry, SandboxPolicy(timeout_seconds=5))

    analysis = await executor.execute_one(
        ToolCall(
            id="a1",
            name="get_sector_analysis",
            arguments={"sector_name": "应用软件"},
        )
    )
    assert analysis.ok is True
    assert analysis.data["level3_id"] == "3"

    constituents = await executor.execute_one(
        ToolCall(
            id="a2",
            name="filter_sector_constituents",
            arguments={"sector_name": "Application Software", "market": "us"},
        )
    )
    assert constituents.ok is True
    assert constituents.data["level3_id"] == "3"
