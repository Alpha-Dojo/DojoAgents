"""Immutable, source-aware harness capability specifications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .base import HarnessDescriptor


@dataclass(frozen=True)
class ComponentSpec:
    component_id: str
    source: str
    priority: int = 0
    dependencies: tuple[str, ...] = ()
    required_services: tuple[str, ...] = ()
    required_tools: tuple[str, ...] = ()
    channel_predicate: Callable[[str], bool] | None = None

    def __post_init__(self) -> None:
        if not self.component_id.strip():
            raise ValueError("component_id must not be blank")
        if not self.source.strip():
            raise ValueError("source must not be blank")
        for field_name in ("dependencies", "required_services", "required_tools"):
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))


@dataclass(frozen=True)
class IdentitySpec(ComponentSpec):
    identity: Any = None


@dataclass(frozen=True)
class RequestContextCodecSpec(ComponentSpec):
    codec: Any = None


@dataclass(frozen=True)
class PromptContributorSpec(ComponentSpec):
    phase: str = "harness_instructions"
    contributor: Any = None


@dataclass(frozen=True)
class SkillSourceSpec(ComponentSpec):
    provider: Any = None
    skill_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolProviderSpec(ComponentSpec):
    provider: Any = None
    tool_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class MCPSourceSpec(ComponentSpec):
    config: Any = None


@dataclass(frozen=True)
class MemoryProviderSpec(ComponentSpec):
    provider: Any = None


@dataclass(frozen=True)
class ToolTransformerSpec(ComponentSpec):
    transformer: Any = None


@dataclass(frozen=True)
class ToolAuthorizerSpec(ComponentSpec):
    authorizer: Any = None


@dataclass(frozen=True)
class ResultPresenterSpec(ComponentSpec):
    presenter: Any = None
    match_kinds: tuple[str, ...] = ()
    exclusive: bool = False


@dataclass(frozen=True)
class ResultArtifactAdapterSpec(ComponentSpec):
    adapter: Any = None


@dataclass(frozen=True)
class FlowPolicySpec(ComponentSpec):
    policy: Any = None


@dataclass(frozen=True)
class TaskSourceSpec(ComponentSpec):
    provider: Any = None


@dataclass(frozen=True)
class PipelineSourceSpec(ComponentSpec):
    provider: Any = None


@dataclass(frozen=True)
class ServiceSpec(ComponentSpec):
    factory: Callable[..., Any] | None = None
    startup: Callable[[Any], Any] | None = None
    shutdown: Callable[[Any], Any] | None = None
    health_check: Callable[[Any], Any] | None = None
    required: bool = True


@dataclass(frozen=True)
class SurfaceAdapterSpec(ComponentSpec):
    adapter: Any = None


@dataclass(frozen=True)
class StateCodecSpec(ComponentSpec):
    codec: Any = None


@dataclass(frozen=True)
class HarnessCapabilities:
    descriptor: HarnessDescriptor
    identity: IdentitySpec | None = None
    request_context_codecs: tuple[RequestContextCodecSpec, ...] = ()
    prompts: tuple[PromptContributorSpec, ...] = ()
    skills: tuple[SkillSourceSpec, ...] = ()
    tools: tuple[ToolProviderSpec, ...] = ()
    mcp_sources: tuple[MCPSourceSpec, ...] = ()
    memories: tuple[MemoryProviderSpec, ...] = ()
    tool_transformers: tuple[ToolTransformerSpec, ...] = ()
    tool_authorizers: tuple[ToolAuthorizerSpec, ...] = ()
    presenters: tuple[ResultPresenterSpec, ...] = ()
    artifact_adapter: ResultArtifactAdapterSpec | None = None
    flow_policies: tuple[FlowPolicySpec, ...] = ()
    tasks: tuple[TaskSourceSpec, ...] = ()
    pipelines: tuple[PipelineSourceSpec, ...] = ()
    services: tuple[ServiceSpec, ...] = ()
    surfaces: tuple[SurfaceAdapterSpec, ...] = ()
    state_codec: Any | None = None
