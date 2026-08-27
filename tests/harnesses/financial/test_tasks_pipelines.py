from __future__ import annotations

import json

import pytest

from dojoagents.agent.models import ChatRequest
from dojoagents.config.models import SessionsConfig
from dojoagents.harnesses.built_in.financial.pipelines import financial_pipeline_directories
from dojoagents.harnesses.built_in.financial.tasks import financial_task_directories
from dojoagents.sessions.blobs.file import FileBlobStore
from dojoagents.sessions.models import SessionCreateSpec, SessionPrincipal
from dojoagents.sessions.service import SessionService
from dojoagents.sessions.stores.file import FileSessionStore
from dojoagents.tasks.activator import TaskActivator
from dojoagents.tasks.manager import TaskPromptManager
from dojoagents.tools.process_registry import active_session_id, active_session_principal
from dojoagents.tools.session_file_tool import get_read_session_output_spec, get_write_session_file_spec


def _manager():
    return TaskPromptManager(
        task_dirs=list(financial_task_directories()),
        pipeline_dirs=list(financial_pipeline_directories()),
    )


def test_financial_task_and_pipeline_sources_preserve_contracts(tmp_path):
    manager = _manager()
    assert manager.list_tasks() == [
        "attribution-factor-crawl",
        "event-trigger",
        "sector-attribution",
        "sector-brief-extract",
        "ticker-sector-classify",
    ]
    assert manager.list_pipelines() == ["daily-market-events"]
    sector = manager.get_task("sector-attribution")
    event = manager.get_task("event-trigger")
    classify = manager.get_task("ticker-sector-classify")
    crawl = manager.get_task("attribution-factor-crawl")
    brief = manager.get_task("sector-brief-extract")
    pipeline = manager.get_pipeline("daily-market-events")
    assert sector.contract.outputs[0].filename == "market_news_raw_pack_{market}_{trading_date}.json"
    assert event.contract.inputs == []
    assert event.contract.outputs[0].filename == "market_event_triggers_{market}_{trading_date}.jsonl"
    assert "get_sector_movers" in event.contract.required_tools
    assert "get_sector_return_curve" in event.contract.required_tools
    assert "web_search" in event.contract.required_tools
    assert "read_session_output" not in event.contract.required_tools
    assert [step.task for step in pipeline.steps] == ["event-trigger"]
    assert sector.contract.constraints["max_tool_calls_per_turn"] == 1
    assert classify.contract.outputs[0].filename == "ticker_sector_labels_{ticker}.json"
    assert classify.contract.harness_profile == "tool_orchestrated"
    assert "search_company_ticker" in classify.contract.required_tools
    assert "web_search" in classify.contract.required_tools
    assert "web_extract" in classify.contract.required_tools
    assert crawl is not None
    assert crawl.contract.harness_profile == "tool_orchestrated"
    assert crawl.contract.outputs[0].filename == "attribution_factors_{market}_{sector_id}_{trading_date}.jsonl"
    assert crawl.contract.outputs[0].format == "jsonl"
    assert "get_sector_movers" in crawl.contract.required_tools
    assert "web_search" in crawl.contract.required_tools
    assert "web_extract" in crawl.contract.required_tools
    assert "get_ticker_news_and_events" not in crawl.contract.required_tools
    assert brief is not None
    assert brief.contract.harness_profile == "tool_orchestrated"
    assert brief.contract.outputs[0].filename == ("sector_theme_brief_{market}_{sector_id}_{as_of_date}.json")
    assert brief.contract.outputs[0].format == "json"
    assert "get_sector_attribution_factors" in brief.contract.required_tools
    assert "web_search" not in brief.contract.required_tools
    assert "web_extract" not in brief.contract.required_tools
    assert "filter_sector_constituents" not in brief.contract.required_tools
    assert brief.contract.required_tools == [
        "search_sector_taxonomy",
        "get_sector_attribution_factors",
        "execute_code",
        "write_session_file",
    ]
    assert brief.prompt_body
    schema_path = brief.task_dir / "schema" / "sector_theme_brief.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    assert "news_events" not in schema["properties"]
    assert set(schema["required"]) == {
        "market",
        "sector_id",
        "as_of_date",
        "key_drivers",
        "key_risks",
        "top_components",
    }
    driver_props = schema["properties"]["key_drivers"]["items"]["properties"]
    assert "title" in driver_props
    assert "detail" in driver_props
    assert driver_props["title"]["type"] == "object"
    assert "zh" in driver_props["title"]["properties"]
    assert "en" in driver_props["title"]["properties"]
    assert "summary" not in driver_props
    assert brief.contract.constraints["tool_budget"]["get_sector_attribution_factors"] == 1


def test_ticker_sector_classify_activation(tmp_path):
    manager = _manager()
    activator = TaskActivator(
        manager=manager,
        sessions_root=str(tmp_path / "sessions"),
        task_output_root=str(tmp_path / "exports"),
    )
    request = ChatRequest("classify", session_id="s-1", principal=SessionPrincipal("alice"))
    active = activator.activate_task(
        request,
        task_id="ticker-sector-classify",
        params={"ticker": "0700.HK", "market": "hk"},
    )
    payload = active.metadata["active_task"]
    assert payload["task_id"] == "ticker-sector-classify"
    assert payload["params"]["ticker"] == "0700.HK"
    assert payload["harness_profile"] == "tool_orchestrated"
    assert payload["outputs"][0]["filename"] == "ticker_sector_labels_0700_HK.json"
    assert payload["outputs"][0]["base_filename"] == "ticker_sector_labels_{ticker}.json"


def test_attribution_factor_crawl_activation_and_schema(tmp_path):
    from dojoagents.tasks.schema_validator import validate_jsonl_payload

    manager = _manager()
    activator = TaskActivator(
        manager=manager,
        sessions_root=str(tmp_path / "sessions"),
        task_output_root=str(tmp_path / "exports"),
    )
    request = ChatRequest("crawl", session_id="s-1", principal=SessionPrincipal("alice"))
    active = activator.activate_task(
        request,
        task_id="attribution-factor-crawl",
        params={"market": "cn", "trading_date": "2026-07-22", "q": "白酒"},
    )
    payload = active.metadata["active_task"]
    assert payload["task_id"] == "attribution-factor-crawl"
    assert payload["harness_profile"] == "tool_orchestrated"
    # sector_id unknown at activation → placeholder remains (resolved after taxonomy).
    assert payload["outputs"][0]["filename"] == "attribution_factors_cn_{sector_id}_2026-07-22.jsonl"
    assert payload["params"]["window_start_date"] == "2026-07-22"

    active_resolved = activator.activate_task(
        request,
        task_id="attribution-factor-crawl",
        params={
            "market": "cn",
            "trading_date": "2026-07-22",
            "sector_id": "1/2/6",
            "sector_path_id": "1/2/6",
            "sector_name": "芯片设计",
            "change_percent": "3.2",
        },
    )
    assert active_resolved.metadata["active_task"]["outputs"][0]["filename"] == "attribution_factors_cn_1_2_6_2026-07-22.jsonl"
    injection = active_resolved.metadata["active_task_prompt"]
    assert "sector_name: 芯片设计" in injection
    assert "change_percent: 3.2" in injection
    crawl = manager.get_task("attribution-factor-crawl")
    assert crawl is not None
    schema_path = manager.resolve_schema_path(crawl, crawl.contract.outputs[0].schema or "")
    assert schema_path is not None
    row = {
        "event_time": "2026-07-22T15:30:00+08:00",
        "claim": {"zh": "龙头业绩不及预期拖累板块"},
        "sector_id": "1/2/3",
        "market": "cn",
        "factor_topic": "earnings",
        "role": "explains_move",
        "price_direction": "down",
        "importance": "high",
        "mechanism": {"zh": "龙头下调预期压制板块估值"},
        "evidence": [{"quote": "公司公告显示二季度营收低于市场预期", "url": "https://example.com/a"}],
        "affected_tickers": ["600519.SS"],
    }
    assert validate_jsonl_payload(json.dumps(row, ensure_ascii=False) + "\n", schema_path) == []


def test_command_activation_keeps_task_profile_and_output_schema(tmp_path):
    manager = _manager()
    activator = TaskActivator(
        manager=manager,
        sessions_root=str(tmp_path / "sessions"),
        task_output_root=str(tmp_path / "exports"),
    )
    request = ChatRequest(
        "run attribution",
        session_id="s-1",
        principal=SessionPrincipal("alice"),
        metadata={"trading_date": "2026-07-22"},
    )
    active = activator.activate_task(
        request,
        task_id="sector-attribution",
        params={"market": "us"},
    )
    payload = active.metadata["active_task"]
    assert payload["harness_profile"] == "tool_orchestrated"
    assert payload["outputs"][0]["filename"] == "market_news_raw_pack_us_2026-07-22.json"
    assert payload["params"]["window_start_date"] == "2026-07-22"


@pytest.mark.asyncio
async def test_task_output_round_trip_uses_principal_scoped_session_object(tmp_path):
    store = FileSessionStore(tmp_path / "sessions", cursor_secret=b"task-secret")
    blobs = FileBlobStore(tmp_path / "blobs")
    await store.startup()
    await blobs.startup()
    service = SessionService(store=store, blob_store=blobs, config=SessionsConfig())
    principal = SessionPrincipal("alice")
    await service.create_session(
        principal,
        SessionCreateSpec("s-1", "financial", "1.0.0", 1),
    )
    session_token = active_session_id.set("s-1")
    principal_token = active_session_principal.set(principal)
    try:
        write = get_write_session_file_spec(tmp_path, session_service=service)
        read = get_read_session_output_spec(tmp_path, session_service=service)
        written = await write.handler({"filename": "market_news_raw_pack.json", "content": {"trading_date": "2026-07-22"}, "format": "json"})
        loaded = await read.handler({"filename": "market_news_raw_pack.json"})
    finally:
        active_session_principal.reset(principal_token)
        active_session_id.reset(session_token)
        await blobs.shutdown()
        await store.shutdown()

    assert written["data"]["storage_kind"] == "session_object"
    assert "path" not in written["data"]
    assert json.loads(loaded["data"]["content"])["trading_date"] == "2026-07-22"
    assert loaded["data"]["object_id"] == written["data"]["object_id"]
