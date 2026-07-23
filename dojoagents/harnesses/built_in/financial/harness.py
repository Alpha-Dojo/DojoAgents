"""Built-in financial scenario Harness."""

from __future__ import annotations

from typing import Any, Mapping

from dojoagents.harnesses.base import HarnessDescriptor
from dojoagents.harnesses.capabilities import ServiceSpec
from dojoagents.harnesses.capabilities import (
    IdentitySpec,
    FlowPolicySpec,
    MemoryProviderSpec,
    PromptContributorSpec,
    RequestContextCodecSpec,
    ResultArtifactAdapterSpec,
    ResultPresenterSpec,
    PipelineSourceSpec,
    TaskSourceSpec,
    SkillSourceSpec,
    StateCodecSpec,
    SurfaceAdapterSpec,
    ToolAuthorizerSpec,
    ToolProviderSpec,
    ToolTransformerSpec,
)
from dojoagents.harnesses.context import HarnessBuildContext, HarnessRuntimeContext

from .config import FinancialHarnessConfig
from .context import FinancialRequestContextCodec
from .memory import create_skill_summary_provider
from .prompts import (
    FINANCIAL_IDENTITY,
    dashboard_tool_prompt,
    financial_instructions_prompt,
    request_context_prompt,
    task_context_prompt,
    temporal_prompt,
    turn_scope_prompt,
    visualization_prompt,
)
from .policies import (
    ArtifactSynthesisTaskPolicy,
    FinancialTurnCompletionPolicy,
    FinancialTurnScopePolicy,
    FinancialVisualizationPolicy,
    PortfolioEscalationPolicy,
    PortfolioFlowPolicy,
    PortfolioToolRepairPolicy,
    SectorSessionPolicy,
    ToolOrchestratedTaskPolicy,
)
from .presenters import (
    EXECUTE_CODE_RESULT_KINDS,
    MARKET_RESULT_KINDS,
    PORTFOLIO_RESULT_KINDS,
    SECTOR_RESULT_KINDS,
    TICKER_RESULT_KINDS,
    FinancialResultPresenter,
    FinancialResultProjector,
)
from .presenters.artifacts import FinancialArtifactAdapter
from dojoagents.harnesses.registries.presenters import PresenterRegistry
from .services import FinancialServiceContainer
from .state import FinancialSessionStateCodec
from .surfaces import (
    FinancialCliSurface,
    FinancialDashboardSurface,
    FinancialGatewaySurface,
    LegacyFinancialDashboardSurface,
)
from .tasks import TASK_IO_TOOL_NAMES, financial_task_directories, get_task_io_specs
from .pipelines import financial_pipeline_directories
from .tools import (
    DOMAIN_TOOL_NAMES,
    PORTFOLIO_TOOL_NAMES,
    SDK_TOOL_NAMES,
    VISUALIZATION_TOOL_NAMES,
    get_agent_viz_specs,
    get_domain_tool_specs,
    get_portfolio_tool_specs,
    get_sdk_tool_specs,
)

FINANCIAL_SERVICE_ID = "financial-domain"
FINANCIAL_PROJECTOR_SERVICE_ID = "financial-result-projector"


class FinancialHarness:
    descriptor = HarnessDescriptor(
        id="financial",
        version="1.0.0",
        display_name="Dojo Financial Analyst",
        description="Full-market financial research and portfolio workflows.",
        state_schema_version=1,
        supported_channels=("dashboard", "cli", "gateway", "api"),
    )

    def __init__(self, config: FinancialHarnessConfig) -> None:
        self.config = config
        self.service_container = FinancialServiceContainer(config)
        self.context_codec = FinancialRequestContextCodec()
        self.memory_provider = create_skill_summary_provider(config.memory_generated_skill_dir)
        self.state_codec = FinancialSessionStateCodec()
        self.turn_scope_policy = FinancialTurnScopePolicy()
        self.portfolio_flow_policy = PortfolioFlowPolicy()
        self.portfolio_repair_policy = PortfolioToolRepairPolicy()
        self.portfolio_escalation_policy = PortfolioEscalationPolicy()
        self.sector_session_policy = SectorSessionPolicy()
        self.visualization_policy = FinancialVisualizationPolicy()
        self.tool_task_policy = ToolOrchestratedTaskPolicy(task_output_root=str(config.tasks.output_root))
        self.artifact_task_policy = ArtifactSynthesisTaskPolicy(task_output_root=str(config.tasks.output_root))
        self.completion_policy = FinancialTurnCompletionPolicy()
        self.result_presenter = FinancialResultPresenter()
        self.artifact_adapter = FinancialArtifactAdapter()
        self.result_projector = FinancialResultProjector()
        self.dashboard_surface = FinancialDashboardSurface(self.service_container)
        self.cli_surface = FinancialCliSurface(self.service_container)
        self.gateway_surface = FinancialGatewaySurface(self.service_container)

    def configure(self, builder: Any, context: HarnessBuildContext) -> None:
        source = "harness:financial"
        builder.set_identity(IdentitySpec("financial.identity", source, priority=100, identity=FINANCIAL_IDENTITY))
        builder.add_request_context_codec(RequestContextCodecSpec("financial.context-codec", source, priority=100, codec=self.context_codec))
        for spec in (
            PromptContributorSpec("core.temporal", source, phase="temporal", contributor=temporal_prompt),
            PromptContributorSpec(
                "financial.instructions",
                source,
                phase="harness_instructions",
                contributor=financial_instructions_prompt,
            ),
            PromptContributorSpec(
                "financial.memory",
                source,
                phase="memory",
                contributor=lambda _turn: self.memory_provider.system_prompt_block(),
            ),
            PromptContributorSpec(
                "financial.request-context",
                source,
                phase="request_context",
                contributor=request_context_prompt,
            ),
            PromptContributorSpec(
                "financial.dashboard-tools",
                source,
                priority=100,
                phase="channel_policy",
                contributor=dashboard_tool_prompt,
                channel_predicate=lambda channel: channel == "dashboard",
            ),
            PromptContributorSpec(
                "financial.dashboard-visualization",
                source,
                priority=90,
                phase="channel_policy",
                contributor=visualization_prompt,
                channel_predicate=lambda channel: channel == "dashboard",
            ),
            PromptContributorSpec(
                "financial.task-context",
                source,
                phase="task_context",
                contributor=task_context_prompt,
            ),
            PromptContributorSpec(
                "financial.turn-scope",
                source,
                phase="turn_policy",
                contributor=turn_scope_prompt,
            ),
        ):
            builder.add_prompt_contributor(spec)
        builder.add_memory_provider(
            MemoryProviderSpec(
                "financial.memory.skill-summary",
                source,
                provider=lambda _runtime: self.memory_provider,
            )
        )
        built_in_skills = context.workdir / "dojoagents" / "skills" / "built_in"
        builder.add_skill_source(SkillSourceSpec("financial.skills.built-in", source, provider=built_in_skills))
        builder.add_skill_source(SkillSourceSpec("financial.skills.user", source, provider=context.config.skills.dir))
        builder.add_skill_source(
            SkillSourceSpec(
                "financial.skills.generated",
                source,
                provider=context.config.skills.generated_skill_dir,
            )
        )
        for index, directory in enumerate(context.config.skills.external_dirs):
            builder.add_skill_source(SkillSourceSpec(f"financial.skills.external.{index}", source, provider=directory))
        for component_id, names, provider in (
            ("financial.tools.domain", DOMAIN_TOOL_NAMES, get_domain_tool_specs),
            ("financial.tools.portfolio", PORTFOLIO_TOOL_NAMES, get_portfolio_tool_specs),
            ("financial.tools.sdk", SDK_TOOL_NAMES, get_sdk_tool_specs),
        ):
            builder.add_tool_provider(
                ToolProviderSpec(
                    component_id,
                    source,
                    required_services=(FINANCIAL_SERVICE_ID,),
                    provider=lambda runtime, factory=provider: factory(runtime.services[FINANCIAL_SERVICE_ID]),
                    tool_names=names,
                )
            )
        builder.add_tool_provider(
            ToolProviderSpec(
                "financial.tools.visualization",
                source,
                provider=tuple(get_agent_viz_specs()),
                tool_names=VISUALIZATION_TOOL_NAMES,
            )
        )
        builder.add_tool_provider(
            ToolProviderSpec(
                "financial.tools.task-io",
                source,
                provider=get_task_io_specs,
                tool_names=TASK_IO_TOOL_NAMES,
            )
        )
        builder.add_state_codec(StateCodecSpec("financial.state", source, codec=self.state_codec))
        for index, directory in enumerate(financial_task_directories()):
            builder.add_task_source(TaskSourceSpec(f"financial.tasks.{index}", source, provider=directory))
        for index, directory in enumerate(financial_pipeline_directories()):
            builder.add_pipeline_source(PipelineSourceSpec(f"financial.pipelines.{index}", source, provider=directory))
        flow_policies = (
            ("financial.turn-scope", 900, self.turn_scope_policy),
            ("financial.portfolio-flow", 800, self.portfolio_flow_policy),
            ("financial.portfolio-escalation", 750, self.portfolio_escalation_policy),
            ("financial.sector-session", 700, self.sector_session_policy),
            ("financial.visualization", 600, self.visualization_policy),
            ("financial.task.tool-orchestrated", 500, self.tool_task_policy),
            ("financial.task.artifact-synthesis", 400, self.artifact_task_policy),
            ("financial.completion", 100, self.completion_policy),
        )
        for component_id, priority, policy in flow_policies:
            builder.add_flow_policy(FlowPolicySpec(component_id, source, priority=priority, policy=policy))
        builder.add_tool_transformer(
            ToolTransformerSpec(
                "financial.portfolio-repair",
                source,
                priority=800,
                transformer=self.portfolio_repair_policy,
            )
        )
        builder.add_tool_transformer(
            ToolTransformerSpec(
                "financial.sector-repair",
                source,
                priority=700,
                transformer=self.sector_session_policy,
            )
        )
        for component_id, priority, policy in (
            ("financial.portfolio-flow.authorizer", 800, self.portfolio_flow_policy),
            ("financial.portfolio-escalation.authorizer", 750, self.portfolio_escalation_policy),
            ("financial.visualization.authorizer", 600, self.visualization_policy),
            ("financial.task.tool-orchestrated.authorizer", 500, self.tool_task_policy),
            ("financial.task.artifact-synthesis.authorizer", 400, self.artifact_task_policy),
        ):
            builder.add_tool_authorizer(ToolAuthorizerSpec(component_id, source, priority=priority, authorizer=policy))
        presenter_specs = tuple(
            ResultPresenterSpec(
                component_id,
                source,
                priority=priority,
                presenter=self.result_presenter,
                match_kinds=match_kinds,
                exclusive=True,
            )
            for component_id, priority, match_kinds in (
                ("financial.presenter.market", 500, MARKET_RESULT_KINDS),
                ("financial.presenter.sector", 490, SECTOR_RESULT_KINDS),
                ("financial.presenter.ticker", 480, TICKER_RESULT_KINDS),
                ("financial.presenter.portfolio", 470, PORTFOLIO_RESULT_KINDS),
                ("financial.presenter.execute-code", 460, EXECUTE_CODE_RESULT_KINDS),
            )
        )
        self.result_projector = FinancialResultProjector(PresenterRegistry(presenter_specs))
        for presenter_spec in presenter_specs:
            builder.add_result_presenter(presenter_spec)
        builder.set_result_artifact_adapter(
            ResultArtifactAdapterSpec(
                "financial.artifacts",
                source,
                priority=500,
                adapter=self.artifact_adapter,
            )
        )
        builder.add_service(
            ServiceSpec(
                component_id=FINANCIAL_SERVICE_ID,
                source="harness:financial",
                factory=lambda: self.service_container,
                required=True,
            )
        )
        builder.add_surface_adapter(
            SurfaceAdapterSpec(
                "dashboard",
                source,
                required_services=(FINANCIAL_SERVICE_ID,),
                adapter=self.dashboard_surface,
            )
        )
        builder.add_surface_adapter(
            SurfaceAdapterSpec(
                "cli",
                source,
                required_services=(FINANCIAL_SERVICE_ID,),
                adapter=self.cli_surface,
            )
        )
        builder.add_surface_adapter(
            SurfaceAdapterSpec(
                "gateway",
                source,
                required_services=(FINANCIAL_SERVICE_ID,),
                adapter=self.gateway_surface,
            )
        )
        builder.add_service(
            ServiceSpec(
                component_id=FINANCIAL_PROJECTOR_SERVICE_ID,
                source=source,
                factory=lambda: self.result_projector,
                required=True,
            )
        )

    async def startup(self, context: HarnessRuntimeContext) -> None:
        if context.services.get(FINANCIAL_SERVICE_ID) is not self.service_container:
            raise RuntimeError("financial service container identity mismatch")

    async def shutdown(self, context: HarnessRuntimeContext) -> None:
        # Service shutdown is dependency-ordered by LifecycleManager.
        return None

    def legacy_surface(self, surface_id: str, runtime: Any) -> Any:
        """Resolve a host adapter for the deprecated synchronous Runtime."""

        if surface_id != "dashboard":
            raise KeyError(surface_id)
        return LegacyFinancialDashboardSurface.from_runtime(runtime)

    def legacy_runtime_contributions(self, root_config: Any):
        """Bridge the deprecated synchronous Runtime without leaking finance into core."""

        from dojoagents.harnesses.legacy import LegacyRuntimeContributions
        from .tools.sdk_runtime import get_dojo_sdk_specs
        from .tools.visualization_engine import get_agent_viz_specs as legacy_viz_specs

        from .compat import FinancialLegacyBehavior
        from .policies.legacy import (
            ArtifactSynthesisHarness,
            PortfolioTaskHarness,
            ToolOrchestratedHarness,
        )
        from .presenters.artifacts import FinancialArtifactAdapter
        from .presenters.legacy_registry import ToolResultPresenterRegistry

        def task_harnesses(task_manager: Any, config: Any) -> tuple[Any, ...]:
            return (
                PortfolioTaskHarness(),
                ToolOrchestratedHarness(
                    task_manager=task_manager,
                    task_output_root=config.tasks.output_root,
                ),
                ArtifactSynthesisHarness(
                    task_manager=task_manager,
                    task_output_root=config.tasks.output_root,
                ),
            )

        return LegacyRuntimeContributions(
            artifact_adapter=FinancialArtifactAdapter(),
            presenter_factory=ToolResultPresenterRegistry,
            behavior=FinancialLegacyBehavior(),
            additional_tool_specs=(
                *get_dojo_sdk_specs(root_config.dojosdk),
                *legacy_viz_specs(),
            ),
            task_harness_factory=task_harnesses,
            task_directories=financial_task_directories(),
            pipeline_directories=financial_pipeline_directories(),
        )


def create_harness(config: Mapping[str, Any], context: HarnessBuildContext) -> FinancialHarness:
    return FinancialHarness(FinancialHarnessConfig.from_context(context))


__all__ = [
    "FINANCIAL_PROJECTOR_SERVICE_ID",
    "FINANCIAL_SERVICE_ID",
    "FinancialHarness",
    "create_harness",
]
