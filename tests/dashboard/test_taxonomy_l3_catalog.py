from __future__ import annotations

from types import SimpleNamespace

import pytest

from dojoagents.dashboard.integrations import financial_domain_tools as domain_tools
from dojoagents.dashboard.services.domain_api import project_taxonomy_l3_catalog
from dojoagents.dashboard.services.sector_store import SectorStore
from dojoagents.harnesses.built_in.financial.backends.http import HTTPFinancialToolBackend
from dojoagents.tools.registry import ToolRegistry
from tests.dashboard.stores.test_gateway_backed_base_stores import BaseGateway


def test_project_taxonomy_l3_catalog_from_tree_payload() -> None:
    payload = {
        "tree": [
            {
                "level1_id": "1",
                "name": {"zh": "科技", "en": "Technology"},
                "children": [
                    {
                        "level2_id": "2",
                        "name": {"zh": "软件", "en": "Software"},
                        "children": [
                            {
                                "level3_id": "3",
                                "name": {"zh": "应用软件", "en": "Application Software"},
                                "definition": {
                                    "zh": "做企业应用软件的公司",
                                    "en": "Companies that build enterprise applications",
                                },
                            }
                        ],
                    }
                ],
            }
        ]
    }

    zh = project_taxonomy_l3_catalog(payload, locale="zh")
    assert zh == {
        "locale": "zh",
        "count": 1,
        "items": [
            {
                "sector_path_id": "1/2/3",
                "name": "应用软件",
                "description": "做企业应用软件的公司",
            }
        ],
    }

    en = project_taxonomy_l3_catalog(payload, locale="en")
    assert en["items"][0]["name"] == "Application Software"
    assert "enterprise applications" in en["items"][0]["description"]


def test_project_taxonomy_l3_catalog_from_level_1_document() -> None:
    payload = {
        "level_1": [
            {
                "id": "10",
                "level_2": [
                    {
                        "id": "20",
                        "level_3": [
                            {
                                "id": "30",
                                "name": {"zh": "材料", "en": "Materials"},
                                "definition": {"zh": "半导体材料", "en": "Semi materials"},
                            }
                        ],
                    }
                ],
            }
        ]
    }
    result = project_taxonomy_l3_catalog(payload, locale="zh")
    assert result["count"] == 1
    assert result["items"][0]["sector_path_id"] == "10/20/30"
    assert result["items"][0]["name"] == "材料"


@pytest.mark.asyncio
async def test_get_taxonomy_tree_tool_returns_flat_catalog() -> None:
    store = SectorStore(BaseGateway())
    await store.load()
    registry = SimpleNamespace(
        sector_store=store,
        stock_store=object(),
        benchmark_store=object(),
    )

    tools = ToolRegistry()
    domain_tools.register_dashboard_domain_tools(tools, registry)
    spec = tools.get("get_taxonomy_tree")
    assert spec is not None
    assert "locale" in spec.parameters["properties"]
    assert "sector_path_id" in spec.description

    result = await spec.handler({})
    payload = result["data"]
    assert payload["locale"] == "zh"
    assert payload["count"] >= 1
    first = payload["items"][0]
    assert first["sector_path_id"].count("/") == 2
    assert first["name"]
    assert "description" in first

    en_result = await spec.handler({"locale": "en"})
    assert en_result["data"]["locale"] == "en"
    assert en_result["data"]["count"] == payload["count"]


@pytest.mark.asyncio
async def test_http_backend_projects_taxonomy_tree(monkeypatch) -> None:
    backend = HTTPFinancialToolBackend("http://example.test")
    nested = {
        "version": "api",
        "id_scheme": "sector_id",
        "tree": [
            {
                "level1_id": "1",
                "children": [
                    {
                        "level2_id": "2",
                        "children": [
                            {
                                "level3_id": "3",
                                "name": {"zh": "应用软件", "en": "Application Software"},
                                "definition": {"zh": "描述", "en": "Desc"},
                            }
                        ],
                    }
                ],
            }
        ],
    }

    class _Resp:
        status_code = 200

        def json(self):
            return nested

    class _Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def request(self, method, url, headers=None, params=None, json=None):
            assert method == "GET"
            assert url.endswith("/api/v1/utility/taxonomy/tree")
            assert params == {}
            return _Resp()

    monkeypatch.setattr(
        "dojoagents.harnesses.built_in.financial.backends.http.httpx.AsyncClient",
        _Client,
    )

    principal = SimpleNamespace(user_id="u1", tenant_id="t1")
    result = await backend.execute(
        "get_taxonomy_tree",
        {"locale": "zh"},
        principal=principal,
        session_id="s1",
    )
    data = result["data"]
    assert data["locale"] == "zh"
    assert data["count"] == 1
    assert data["items"][0]["sector_path_id"] == "1/2/3"
    assert data["items"][0]["name"] == "应用软件"
    assert "sector_path_id" in result["content"]
