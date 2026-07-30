from __future__ import annotations

from dojoagents.agent.models import ChatRequest, ToolCall
from dojoagents.harnesses.built_in.financial.policies.legacy_harness import HarnessLoopState
from dojoagents.harnesses.built_in.financial.policies.legacy.tool_orchestrated import (
    ToolOrchestratedHarness,
)
from dojoagents.tasks.run_context import (
    PACK_DASHBOARD_PROTOCOL,
    PACK_DASHBOARD_VIZ,
    PACK_TASK_BODY,
    PROFILE_FREEFORM,
    PROFILE_JOB_FREEFORM,
    PROFILE_JOB_TASK,
    PROFILE_PIPELINE_STEP,
    PROFILE_TASK_CONTRACT,
    RunContext,
)


def _request(*, channel: str = "dashboard", metadata: dict | None = None) -> ChatRequest:
    return ChatRequest(
        message="run",
        user_id="u1",
        session_id="s1",
        channel=channel,
        metadata=metadata or {},
    )


def test_run_context_freeform_dashboard_gets_protocol_packs() -> None:
    ctx = RunContext.resolve(_request(channel="dashboard"))
    assert ctx.profile == PROFILE_FREEFORM
    assert ctx.has_prompt_pack(PACK_DASHBOARD_PROTOCOL)
    assert ctx.has_prompt_pack(PACK_DASHBOARD_VIZ)
    assert not ctx.has_prompt_pack(PACK_TASK_BODY)
    assert ctx.allowed_tools is None


def test_run_context_freeform_cli_skips_dashboard_packs() -> None:
    ctx = RunContext.resolve(_request(channel="cli"))
    assert ctx.profile == PROFILE_FREEFORM
    assert ctx.prompt_packs == ()


def test_run_context_task_contract_suppresses_dashboard_packs() -> None:
    ctx = RunContext.resolve(
        _request(
            channel="dashboard",
            metadata={
                "task_mode": True,
                "active_task": {
                    "task_id": "ticker-sector-classify",
                    "harness_profile": "tool_orchestrated",
                    "constraints": {
                        "allowed_tools": [
                            "search_company_ticker",
                            "search_sector_taxonomy",
                            "write_session_file",
                        ]
                    },
                },
            },
        )
    )
    assert ctx.profile == PROFILE_TASK_CONTRACT
    assert ctx.prompt_packs == (PACK_TASK_BODY,)
    assert not ctx.has_prompt_pack(PACK_DASHBOARD_PROTOCOL)
    assert ctx.allowed_tools == frozenset(
        {
            "search_company_ticker",
            "search_sector_taxonomy",
            "write_session_file",
        }
    )


def test_run_context_pipeline_step_profile() -> None:
    ctx = RunContext.resolve(
        _request(
            metadata={
                "active_task": {
                    "task_id": "sector-attribution",
                    "harness_profile": "tool_orchestrated",
                    "constraints": {"allowed_tools": ["web_search", "write_session_file"]},
                },
                "pipeline": {"id": "daily-market-events", "step": 1},
            }
        )
    )
    assert ctx.profile == PROFILE_PIPELINE_STEP
    assert ctx.prompt_packs == (PACK_TASK_BODY,)


def test_run_context_job_freeform_skips_dashboard_protocol() -> None:
    ctx = RunContext.resolve(
        _request(
            channel="dashboard",
            metadata={"job_id": "nightly-brief"},
        )
    )
    assert ctx.profile == PROFILE_JOB_FREEFORM
    assert ctx.prompt_packs == ()


def test_run_context_job_task_profile() -> None:
    ctx = RunContext.resolve(
        _request(
            channel="scheduler",
            metadata={
                "job_id": "nightly-classify",
                "active_task": {
                    "task_id": "ticker-sector-classify",
                    "constraints": {"allowed_tools": ["write_session_file"]},
                },
            },
        )
    )
    assert ctx.profile == PROFILE_JOB_TASK
    assert ctx.prompt_packs == (PACK_TASK_BODY,)


def test_tool_orchestrated_allowlist_blocks_constituent_tools() -> None:
    harness = ToolOrchestratedHarness()
    request = _request(
        metadata={
            "active_task": {
                "task_id": "ticker-sector-classify",
                "harness_profile": "tool_orchestrated",
                "constraints": {
                    "max_tool_calls_per_turn": 1,
                    "allowed_tools": [
                        "search_company_ticker",
                        "dojo.sdk.stock.ystock_info",
                        "search_sector_taxonomy",
                        "write_session_file",
                    ],
                },
            }
        }
    )
    state = HarnessLoopState(request=request)
    blocked = harness.block_tool_call(
        ToolCall(id="1", name="filter_sector_constituents", arguments={"market": "cn"}),
        state,
    )
    assert blocked is not None
    assert "allowlist" in blocked
    assert "filter_sector_constituents" in blocked

    allowed = harness.block_tool_call(
        ToolCall(id="2", name="search_sector_taxonomy", arguments={"q": "半导体"}),
        state,
    )
    assert allowed is None
