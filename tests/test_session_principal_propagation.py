from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from dojoagents.agent.models import AgentResponse, ChatRequest
from dojoagents.cron.jobs import ScheduledJob
from dojoagents.gateway.adapters.base import GatewayEvent
from dojoagents.multi_agent.models import AgentRole, AgentSpec
from dojoagents.multi_agent.pool import AgentPool
from dojoagents.sessions.models import SessionPrincipal


def test_gateway_maps_verified_platform_identity_to_stable_principal():
    event = GatewayEvent("slack", "hello", "C1", "U1")
    first = event.to_chat_request()
    second = event.to_chat_request(session_id="other")
    assert first.principal == second.principal == SessionPrincipal("U1", tenant_id="gateway:slack")


def test_scheduled_job_owner_round_trips_and_drives_request():
    owner = SessionPrincipal("svc-market", tenant_id="ops", roles=frozenset({"service"}))
    job = ScheduledJob("j1", "market", {}, "run", owner=owner)
    restored = ScheduledJob.from_record(job.to_record())
    assert restored.owner == owner
    assert restored.to_chat_request().principal == owner


@pytest.mark.asyncio
async def test_child_agent_inherits_parent_principal_without_role_escalation():
    runtime = MagicMock()
    parent = SessionPrincipal("alice", roles=frozenset({"analyst"}))
    pool = AgentPool(runtime, principal=parent)
    pool.register_agent(AgentSpec(AgentRole.ANALYST, "worker"))
    child = MagicMock()
    child.run = AsyncMock(return_value=AgentResponse("ok", "sub-1"))
    pool._agents["worker"] = child
    spoofed = ChatRequest(
        "work",
        session_id="sub-1",
        principal=SessionPrincipal("mallory", roles=frozenset({"admin"})),
    )
    await pool.invoke("worker", spoofed)
    actual = child.run.await_args.args[0]
    assert actual.principal == parent
    assert "admin" not in actual.principal.roles
