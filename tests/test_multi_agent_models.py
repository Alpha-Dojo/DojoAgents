"""Tests for dojoagents.multi_agent.models — AgentRole, TaskStatus, AgentSpec, SubTask, AgentMessage."""

import pytest

from dojoagents.multi_agent.models import (
    AgentRole,
    TaskStatus,
    AgentSpec,
    SubTask,
    AgentMessage,
)


class TestAgentRole:
    def test_enum_values(self):
        assert AgentRole.ORCHESTRATOR == "orchestrator"
        assert AgentRole.ANALYST == "analyst"
        assert AgentRole.IMPLEMENTER == "implementer"
        assert AgentRole.REVIEWER == "reviewer"
        assert AgentRole.SPECIALIST == "specialist"

    def test_all_five_roles(self):
        assert len(AgentRole) == 5


class TestTaskStatus:
    def test_enum_values(self):
        assert TaskStatus.PENDING == "pending"
        assert TaskStatus.IN_PROGRESS == "in_progress"
        assert TaskStatus.COMPLETED == "completed"
        assert TaskStatus.FAILED == "failed"
        assert TaskStatus.CANCELLED == "cancelled"

    def test_all_five_statuses(self):
        assert len(TaskStatus) == 5


class TestAgentSpec:
    def test_defaults(self):
        spec = AgentSpec(role=AgentRole.ANALYST, name="analyst")
        assert spec.system_prompt_override == ""
        assert spec.model is None
        assert spec.allowed_tools == []
        assert spec.disallowed_tools == []
        assert spec.max_iterations == 50

    def test_custom_values(self):
        spec = AgentSpec(
            role=AgentRole.IMPLEMENTER,
            name="coder",
            system_prompt_override="You are a coder.",
            model="gpt-4o",
            allowed_tools=["terminal"],
            disallowed_tools=["code_execution"],
            max_iterations=30,
        )
        assert spec.role == AgentRole.IMPLEMENTER
        assert spec.model == "gpt-4o"
        assert spec.allowed_tools == ["terminal"]


class TestSubTask:
    def test_defaults(self):
        st = SubTask(id="s1", title="Analyze", description="Analyze BTC", assigned_to=AgentRole.ANALYST)
        assert st.status == TaskStatus.PENDING
        assert st.depends_on == []
        assert st.result == ""
        assert st.artifacts == []
        assert st.metadata == {}

    def test_with_dependencies(self):
        st = SubTask(
            id="s2",
            title="Build",
            description="Build strategy",
            assigned_to=AgentRole.IMPLEMENTER,
            depends_on=["s1"],
        )
        assert st.depends_on == ["s1"]


class TestAgentMessage:
    def test_defaults(self):
        msg = AgentMessage(from_agent="orchestrator", to_agent="analyst", content="Analyze BTC")
        assert msg.message_type == "task_result"
        assert msg.metadata == {}

    def test_custom_type(self):
        msg = AgentMessage(
            from_agent="analyst",
            to_agent="orchestrator",
            content="Done",
            message_type="handoff",
        )
        assert msg.message_type == "handoff"
