import pytest

from dojoagents.harnesses.base import HarnessDescriptor
from dojoagents.harnesses.builder import HarnessBuilder
from dojoagents.harnesses.capabilities import (
    FlowPolicySpec,
    MCPSourceSpec,
    MemoryProviderSpec,
    PipelineSourceSpec,
    PromptContributorSpec,
    ResultPresenterSpec,
    ServiceSpec,
    SurfaceAdapterSpec,
    TaskSourceSpec,
    ToolProviderSpec,
)
from dojoagents.harnesses.errors import CapabilityConflictError


def builder():
    return HarnessBuilder(HarnessDescriptor("test", "1", "Test"))


@pytest.mark.parametrize(
    ("method", "spec"),
    [
        ("add_tool_provider", ToolProviderSpec("quotes", "harness:a", tool_names=("quote",))),
        ("add_mcp_source", MCPSourceSpec("market", "harness:a")),
        ("add_memory_provider", MemoryProviderSpec("memory", "harness:a")),
        ("add_task_source", TaskSourceSpec("research", "harness:a")),
        ("add_pipeline_source", PipelineSourceSpec("daily", "harness:a")),
        ("add_service", ServiceSpec("data", "harness:a", factory=lambda: object())),
        ("add_surface_adapter", SurfaceAdapterSpec("dashboard", "harness:a")),
        ("add_flow_policy", FlowPolicySpec("risk", "harness:a")),
    ],
)
def test_duplicate_unique_capabilities_report_both_sources(method, spec):
    graph = builder()
    getattr(graph, method)(spec)
    conflicting = type(spec)(**{**spec.__dict__, "source": "plugin:b"})

    with pytest.raises(CapabilityConflictError, match=r"harness:a.*plugin:b"):
        getattr(graph, method)(conflicting)


def test_duplicate_tool_names_conflict_even_when_provider_ids_differ():
    graph = builder()
    graph.add_tool_provider(ToolProviderSpec("one", "harness:a", tool_names=("quote",)))
    with pytest.raises(CapabilityConflictError, match=r"quote.*harness:a.*plugin:b"):
        graph.add_tool_provider(ToolProviderSpec("two", "plugin:b", tool_names=("quote",)))


def test_exclusive_presenter_overlap_and_missing_dependencies_fail():
    graph = builder()
    graph.add_result_presenter(ResultPresenterSpec("chart", "harness:a", match_kinds=("chart",), exclusive=True))
    with pytest.raises(CapabilityConflictError, match=r"chart.*harness:a.*plugin:b"):
        graph.add_result_presenter(ResultPresenterSpec("chart2", "plugin:b", match_kinds=("chart",), exclusive=True))

    missing = builder()
    missing.add_flow_policy(FlowPolicySpec("risk", "harness:a", required_services=("portfolio",)))
    with pytest.raises(CapabilityConflictError, match="portfolio"):
        missing.build()

    missing_tool = builder()
    missing_tool.add_flow_policy(FlowPolicySpec("risk", "harness:a", required_tools=("position",)))
    with pytest.raises(CapabilityConflictError, match="position"):
        missing_tool.build()


def test_prompt_and_policy_order_is_deterministic_and_graph_is_frozen():
    graph = builder()
    graph.add_prompt_contributor(PromptContributorSpec("z", "harness:a", priority=1, phase="skills"))
    graph.add_prompt_contributor(PromptContributorSpec("b", "harness:a", priority=2, phase="identity"))
    graph.add_prompt_contributor(PromptContributorSpec("a", "harness:a", priority=2, phase="identity"))
    graph.add_flow_policy(FlowPolicySpec("low", "harness:a", priority=1))
    graph.add_flow_policy(FlowPolicySpec("high-b", "harness:a", priority=3))
    graph.add_flow_policy(FlowPolicySpec("high-a", "harness:a", priority=3))

    capabilities = graph.build()

    assert [item.component_id for item in capabilities.prompts] == ["a", "b", "z"]
    assert [item.component_id for item in capabilities.flow_policies] == ["high-a", "high-b", "low"]
    with pytest.raises(CapabilityConflictError, match="already built"):
        graph.add_task_source(TaskSourceSpec("later", "harness:a"))
