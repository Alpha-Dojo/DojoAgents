"""Verify public exports of multi_agent and planning modules."""


class TestPackageVersion:
    def test_dojoagents_version(self):
        import dojoagents
        from importlib.metadata import version

        assert dojoagents.__version__
        assert dojoagents.__version__ == version("dojoagents")
        assert dojoagents.__all__ == ["__version__"]


class TestMultiAgentExports:
    def test_all_public_symbols_importable(self):
        from dojoagents.multi_agent import (
            AgentMessage,
            AgentPool,
            AgentRole,
            AgentSpec,
            MultiAgentTriggerHook,
            Orchestrator,
            SubTask,
            TaskStatus,
            get_delegation_tool_spec,
        )

        # Each should be a real class/function, not None
        assert AgentMessage is not None
        assert AgentPool is not None
        assert AgentRole is not None
        assert AgentSpec is not None
        assert MultiAgentTriggerHook is not None
        assert Orchestrator is not None
        assert SubTask is not None
        assert TaskStatus is not None
        assert callable(get_delegation_tool_spec)

    def test_all_list_matches_exports(self):
        import dojoagents.multi_agent as mod

        assert set(mod.__all__) == {
            "AgentMessage",
            "AgentPool",
            "AgentRole",
            "AgentSpec",
            "MultiAgentTriggerHook",
            "Orchestrator",
            "SubTask",
            "TaskStatus",
            "get_delegation_tool_spec",
        }


class TestPlanningExports:
    def test_all_public_symbols_importable(self):
        from dojoagents.planning import (
            Plan,
            PlanActivationHook,
            PlanExecutionEngine,
            PlanStateStore,
            PlanStatus,
            PlanStep,
            StepType,
            get_plan_tools,
        )

        assert Plan is not None
        assert PlanActivationHook is not None
        assert PlanExecutionEngine is not None
        assert PlanStateStore is not None
        assert PlanStatus is not None
        assert PlanStep is not None
        assert StepType is not None
        assert callable(get_plan_tools)

    def test_all_list_matches_exports(self):
        import dojoagents.planning as mod

        assert set(mod.__all__) == {
            "Plan",
            "PlanActivationHook",
            "PlanExecutionEngine",
            "PlanStateStore",
            "PlanStatus",
            "PlanStep",
            "StepType",
            "get_plan_tools",
        }


class TestHarnessExports:
    def test_formal_namespace_exports_core_contracts(self):
        import dojoagents.harnesses as mod

        assert set(mod.__all__) == {
            "AgentHarness",
            "HarnessBuildContext",
            "HarnessBuilder",
            "HarnessCapabilities",
            "HarnessDescriptor",
            "HarnessLoader",
            "HarnessRuntime",
            "HarnessRuntimeContext",
            "HarnessSessionContext",
            "HarnessTurnContext",
        }
