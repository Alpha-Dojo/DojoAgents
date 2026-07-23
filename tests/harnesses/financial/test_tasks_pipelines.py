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
    assert manager.list_tasks() == ["event-trigger", "sector-attribution"]
    assert manager.list_pipelines() == ["daily-market-events"]
    sector = manager.get_task("sector-attribution")
    event = manager.get_task("event-trigger")
    pipeline = manager.get_pipeline("daily-market-events")
    assert sector.contract.outputs[0].filename == "market_news_raw_pack.json"
    assert event.contract.inputs[0].schema.endswith("market_news_raw_pack.schema.json")
    assert event.contract.constraints["must_read_input_before_write"] is True
    assert [step.task for step in pipeline.steps] == ["sector-attribution", "event-trigger"]
    assert sector.contract.constraints["max_tool_calls_per_turn"] == 1


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
    active = activator.activate_task(request, task_id="sector-attribution")
    payload = active.metadata["active_task"]
    assert payload["harness_profile"] == "tool_orchestrated"
    assert payload["outputs"][0]["filename"] == "market_news_raw_pack_2026-07-22.json"
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
