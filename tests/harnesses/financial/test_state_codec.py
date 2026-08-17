from __future__ import annotations

import pytest

from dojoagents.agent.models import ChatRequest, ToolResult
from dojoagents.harnesses.built_in.financial.state import (
    FinancialSessionStateCodec,
    FinancialTurnState,
    financial_turn_state,
)
from dojoagents.harnesses.context import HarnessSessionContext, HarnessTurnContext
from dojoagents.harnesses.state import HarnessSessionState
from dojoagents.sessions.errors import HarnessSessionIncompatibleError
from dojoagents.sessions.models import SessionPrincipal


def _turn(session_id: str) -> HarnessTurnContext:
    request = ChatRequest(
        "创建组合" if session_id == "a" else "清仓",
        session_id=session_id,
        principal=SessionPrincipal("alice"),
        channel="dashboard",
    )
    return HarnessTurnContext(
        request,
        HarnessSessionContext(request.principal, session_id, HarnessSessionState()),
    )


def test_financial_turn_state_isolated_across_concurrent_turns_and_tracks_facts():
    first = _turn("a")
    second = _turn("b")
    first.tool_results.extend(
        [
            ToolResult("c1", "portfolio_write_create", True, data={"id": "p-1"}),
            ToolResult(
                "c2",
                "portfolio_read_detail",
                True,
                data={
                    "id": "p-1",
                    "candidates": [{"ticker": "AAPL"}],
                    "positions": [{"ticker": "AAPL", "shares": 3}],
                },
            ),
            ToolResult("c3", "portfolio_eval_submit", True, data={"portfolio_id": "p-1"}),
        ]
    )

    state_a = FinancialTurnState.from_context(first)
    state_b = FinancialTurnState.from_context(second)
    first.turn_state.values["financial"] = state_a
    second.turn_state.values["financial"] = state_b

    assert state_a.target_portfolio_id == "p-1"
    assert state_a.candidate_count == 1
    assert state_a.position_count == 1
    assert state_a.last_eval_submission == {"portfolio_id": "p-1"}
    assert state_b.target_portfolio_id is None
    assert state_b.liquidation_intent is True
    assert financial_turn_state(first) is not financial_turn_state(second)


def test_financial_session_state_codec_upgrades_old_schema_and_denies_downgrade():
    codec = FinancialSessionStateCodec()
    migrated = codec.migrate(
        {"portfolio_id": "p-old", "sector_context": {"sector_path_id": "1/2/3"}},
        from_version="0.9.0",
        from_schema_version=0,
        to_version="1.0.0",
        to_schema_version=1,
    )
    decoded = codec.decode(migrated)

    assert decoded.values["financial"]["target_portfolio_id"] == "p-old"
    assert decoded.values["financial"]["sector_context"]["sector_path_id"] == "1/2/3"
    assert codec.encode(decoded) == migrated

    with pytest.raises(HarnessSessionIncompatibleError, match="newer"):
        codec.migrate(
            {},
            from_version="2.0.0",
            from_schema_version=2,
            to_version="1.0.0",
            to_schema_version=1,
        )
