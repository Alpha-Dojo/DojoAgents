"""Validated one-shot builder for an immutable harness capability graph."""

from __future__ import annotations

from typing import Any, TypeVar

from .base import HarnessDescriptor
from .capabilities import (
    ComponentSpec,
    FlowPolicySpec,
    HarnessCapabilities,
    IdentitySpec,
    MCPSourceSpec,
    MemoryProviderSpec,
    PipelineSourceSpec,
    PromptContributorSpec,
    RequestContextCodecSpec,
    ResultPresenterSpec,
    ServiceSpec,
    SkillSourceSpec,
    StateCodecSpec,
    SurfaceAdapterSpec,
    TaskSourceSpec,
    ToolAuthorizerSpec,
    ToolProviderSpec,
    ToolTransformerSpec,
)
from .errors import CapabilityConflictError

T = TypeVar("T", bound=ComponentSpec)

_PROMPT_PHASES = (
    "identity",
    "temporal",
    "harness_instructions",
    "skills",
    "memory",
    "request_context",
    "channel_policy",
    "task_context",
    "turn_policy",
)
_PHASE_ORDER = {phase: index for index, phase in enumerate(_PROMPT_PHASES)}


class HarnessBuilder:
    """Collects one harness's declarations and freezes them exactly once."""

    def __init__(self, descriptor: HarnessDescriptor) -> None:
        self.descriptor = descriptor
        self._built = False
        self._identity: IdentitySpec | None = None
        self._state_codec: StateCodecSpec | None = None
        self._request_context_codecs: dict[str, RequestContextCodecSpec] = {}
        self._prompts: dict[str, PromptContributorSpec] = {}
        self._skills: dict[str, SkillSourceSpec] = {}
        self._tools: dict[str, ToolProviderSpec] = {}
        self._mcp_sources: dict[str, MCPSourceSpec] = {}
        self._memories: dict[str, MemoryProviderSpec] = {}
        self._tool_transformers: dict[str, ToolTransformerSpec] = {}
        self._tool_authorizers: dict[str, ToolAuthorizerSpec] = {}
        self._presenters: dict[str, ResultPresenterSpec] = {}
        self._flow_policies: dict[str, FlowPolicySpec] = {}
        self._tasks: dict[str, TaskSourceSpec] = {}
        self._pipelines: dict[str, PipelineSourceSpec] = {}
        self._services: dict[str, ServiceSpec] = {}
        self._surfaces: dict[str, SurfaceAdapterSpec] = {}
        self._tool_names: dict[str, ToolProviderSpec] = {}

    def _ensure_mutable(self) -> None:
        if self._built:
            raise CapabilityConflictError("capability graph is already built")

    @property
    def tool_names(self) -> frozenset[str]:
        """Names declared so far, exposed for supplemental source validation."""

        return frozenset(self._tool_names)

    @staticmethod
    def _conflict(kind: str, component_id: str, first: ComponentSpec, second: ComponentSpec) -> None:
        raise CapabilityConflictError(f"duplicate {kind} '{component_id}' from {first.source} conflicts with {second.source}; " "rename or remove one declaration")

    def _add(self, collection: dict[str, T], spec: T, kind: str) -> None:
        self._ensure_mutable()
        existing = collection.get(spec.component_id)
        if existing is not None:
            self._conflict(kind, spec.component_id, existing, spec)
        collection[spec.component_id] = spec

    def set_identity(self, spec: IdentitySpec) -> None:
        self._ensure_mutable()
        if self._identity is not None:
            self._conflict("identity", spec.component_id, self._identity, spec)
        self._identity = spec

    def add_request_context_codec(self, spec: RequestContextCodecSpec) -> None:
        self._add(self._request_context_codecs, spec, "request context codec")

    def add_prompt_contributor(self, spec: PromptContributorSpec) -> None:
        self._add(self._prompts, spec, "prompt contributor")

    def add_skill_source(self, spec: SkillSourceSpec) -> None:
        self._add(self._skills, spec, "skill")

    def add_tool_provider(self, spec: ToolProviderSpec) -> None:
        self._ensure_mutable()
        for tool_name in spec.tool_names:
            existing = self._tool_names.get(tool_name)
            if existing is not None:
                self._conflict("tool", tool_name, existing, spec)
        self._add(self._tools, spec, "tool provider")
        for tool_name in spec.tool_names:
            self._tool_names[tool_name] = spec

    def add_mcp_source(self, spec: MCPSourceSpec) -> None:
        self._add(self._mcp_sources, spec, "MCP source")

    def add_memory_provider(self, spec: MemoryProviderSpec) -> None:
        self._add(self._memories, spec, "memory provider")

    def add_tool_transformer(self, spec: ToolTransformerSpec) -> None:
        self._add(self._tool_transformers, spec, "tool transformer")

    def add_tool_authorizer(self, spec: ToolAuthorizerSpec) -> None:
        self._add(self._tool_authorizers, spec, "tool authorizer")

    def add_result_presenter(self, spec: ResultPresenterSpec) -> None:
        self._ensure_mutable()
        if spec.exclusive:
            kinds = set(spec.match_kinds)
            for existing in self._presenters.values():
                overlap = kinds.intersection(existing.match_kinds)
                if existing.exclusive and overlap:
                    self._conflict("exclusive presenter", sorted(overlap)[0], existing, spec)
        self._add(self._presenters, spec, "result presenter")

    def add_flow_policy(self, spec: FlowPolicySpec) -> None:
        self._add(self._flow_policies, spec, "flow policy")

    def add_task_source(self, spec: TaskSourceSpec) -> None:
        self._add(self._tasks, spec, "task")

    def add_pipeline_source(self, spec: PipelineSourceSpec) -> None:
        self._add(self._pipelines, spec, "pipeline")

    def add_service(self, spec: ServiceSpec) -> None:
        self._add(self._services, spec, "service")

    def add_surface_adapter(self, spec: SurfaceAdapterSpec) -> None:
        self._add(self._surfaces, spec, "surface")

    def add_state_codec(self, spec: StateCodecSpec | Any) -> None:
        self._ensure_mutable()
        if not isinstance(spec, StateCodecSpec):
            spec = StateCodecSpec("state", f"harness:{self.descriptor.id}", codec=spec)
        if self._state_codec is not None:
            self._conflict("state codec", spec.component_id, self._state_codec, spec)
        self._state_codec = spec

    def _all_specs(self) -> tuple[ComponentSpec, ...]:
        collections = (
            self._request_context_codecs,
            self._prompts,
            self._skills,
            self._tools,
            self._mcp_sources,
            self._memories,
            self._tool_transformers,
            self._tool_authorizers,
            self._presenters,
            self._flow_policies,
            self._tasks,
            self._pipelines,
            self._services,
            self._surfaces,
        )
        values = tuple(item for collection in collections for item in collection.values())
        return values + tuple(item for item in (self._identity, self._state_codec) if item is not None)

    def _validate_dependencies(self) -> None:
        specs = self._all_specs()
        component_ids = {spec.component_id for spec in specs}
        service_ids = set(self._services)
        tool_names = set(self._tool_names)
        for spec in specs:
            for dependency in spec.dependencies:
                if dependency not in component_ids:
                    raise CapabilityConflictError(f"component '{spec.component_id}' from {spec.source} requires missing component '{dependency}'")
            for service in spec.required_services:
                if service not in service_ids:
                    raise CapabilityConflictError(f"component '{spec.component_id}' from {spec.source} requires missing service '{service}'")
            for tool in spec.required_tools:
                if tool not in tool_names:
                    raise CapabilityConflictError(f"component '{spec.component_id}' from {spec.source} requires missing tool '{tool}'")

    @staticmethod
    def _ordered(items: dict[str, T]) -> tuple[T, ...]:
        return tuple(sorted(items.values(), key=lambda item: (-item.priority, item.component_id)))

    def build(self) -> HarnessCapabilities:
        self._ensure_mutable()
        self._validate_dependencies()
        self._built = True
        prompts = tuple(
            sorted(
                self._prompts.values(),
                key=lambda item: (_PHASE_ORDER.get(item.phase, len(_PHASE_ORDER)), -item.priority, item.component_id),
            )
        )
        return HarnessCapabilities(
            descriptor=self.descriptor,
            identity=self._identity,
            request_context_codecs=self._ordered(self._request_context_codecs),
            prompts=prompts,
            skills=self._ordered(self._skills),
            tools=self._ordered(self._tools),
            mcp_sources=self._ordered(self._mcp_sources),
            memories=self._ordered(self._memories),
            tool_transformers=self._ordered(self._tool_transformers),
            tool_authorizers=self._ordered(self._tool_authorizers),
            presenters=self._ordered(self._presenters),
            flow_policies=self._ordered(self._flow_policies),
            tasks=self._ordered(self._tasks),
            pipelines=self._ordered(self._pipelines),
            services=self._ordered(self._services),
            surfaces=self._ordered(self._surfaces),
            state_codec=self._state_codec.codec if self._state_codec is not None else None,
        )
