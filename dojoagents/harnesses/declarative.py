"""Conversion from a constrained manifest to the normal HarnessBuilder API."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .base import HarnessDescriptor, validate_harness
from .capabilities import (
    IdentitySpec,
    MCPSourceSpec,
    MemoryProviderSpec,
    PipelineSourceSpec,
    PromptContributorSpec,
    ServiceSpec,
    SkillSourceSpec,
    StateCodecSpec,
    SurfaceAdapterSpec,
    TaskSourceSpec,
    ToolAuthorizerSpec,
    ToolProviderSpec,
    ToolTransformerSpec,
    FlowPolicySpec,
    ResultPresenterSpec,
)
from .loader import HarnessLoader


def _predicate(channels):
    allowed = frozenset(str(channel) for channel in channels or ())
    return (lambda channel: channel in allowed) if allowed else None


class DeclarativeHarness:
    def __init__(self, manifest: dict[str, Any], context: Any) -> None:
        self.manifest = manifest
        self.path = Path(manifest["_manifest_path"])
        metadata = manifest["metadata"]
        self.descriptor = HarnessDescriptor(
            str(metadata["id"]),
            str(metadata["version"]),
            str(metadata["display_name"]),
            str(metadata.get("description") or ""),
            int(metadata.get("state_schema_version", 1)),
            tuple(metadata.get("supported_channels") or ()),
        )
        self.delegate = None
        implementation = manifest.get("implementation") or {}
        if implementation:
            factory = HarnessLoader._resolve(str(implementation["factory"]))
            self.delegate = validate_harness(HarnessLoader._instantiate(factory, manifest.get("config") or {}, context))
            if self.delegate.descriptor.id != self.descriptor.id:
                raise ValueError("declarative metadata id differs from implementation descriptor")

    def _common(self, entry: dict[str, Any]) -> dict[str, Any]:
        return {
            "priority": int(entry.get("priority", 0)),
            "dependencies": tuple(entry.get("dependencies") or ()),
            "required_services": tuple(entry.get("required_services") or ()),
            "required_tools": tuple(entry.get("required_tools") or ()),
            "channel_predicate": _predicate(entry.get("channels")),
        }

    def _factory_value(self, entry: dict[str, Any]) -> Any:
        return HarnessLoader._resolve(str(entry["factory"])) if entry.get("factory") else None

    def configure(self, builder: Any, context: Any) -> None:
        if self.delegate is not None:
            self.delegate.configure(builder, context)
            return
        source = f"manifest:{self.path}"
        components = self.manifest.get("components") or {}
        identity = components.get("identity")
        if identity:
            builder.set_identity(IdentitySpec(identity["id"], source, identity=identity.get("value"), **self._common(identity)))
        for entry in components.get("prompts") or ():
            contributor = self._factory_value(entry)
            if entry.get("path"):
                prompt_path = (self.path.parent / str(entry["path"])).resolve()

                def path_contributor(_ctx, path=prompt_path):
                    return path.read_text(encoding="utf-8")

                contributor = path_contributor
            elif contributor is None:
                prompt_value = str(entry.get("value") or "")

                def value_contributor(_ctx, value=prompt_value):
                    return value

                contributor = value_contributor
            builder.add_prompt_contributor(
                PromptContributorSpec(entry["id"], source, phase=str(entry.get("phase") or "harness_instructions"), contributor=contributor, **self._common(entry))
            )
        for kind, method, spec_type, value_key in (
            ("skills", builder.add_skill_source, SkillSourceSpec, "provider"),
            ("tasks", builder.add_task_source, TaskSourceSpec, "provider"),
            ("pipelines", builder.add_pipeline_source, PipelineSourceSpec, "provider"),
        ):
            for entry in components.get(kind) or ():
                value = self._factory_value(entry) or (self.path.parent / str(entry.get("path") or ".")).resolve()
                method(spec_type(entry["id"], source, **{value_key: value}, **self._common(entry)))
        for entry in components.get("tools") or ():
            builder.add_tool_provider(
                ToolProviderSpec(entry["id"], source, provider=self._factory_value(entry), tool_names=tuple(entry.get("tool_names") or ()), **self._common(entry))
            )
        for entry in components.get("mcp") or ():
            builder.add_mcp_source(MCPSourceSpec(entry["id"], source, config=dict(entry.get("config") or {}), **self._common(entry)))
        for entry in components.get("memory") or ():
            builder.add_memory_provider(MemoryProviderSpec(entry["id"], source, provider=self._factory_value(entry), **self._common(entry)))
        policy_types = {
            "flow": (builder.add_flow_policy, FlowPolicySpec, "policy"),
            "authorizer": (builder.add_tool_authorizer, ToolAuthorizerSpec, "authorizer"),
            "transformer": (builder.add_tool_transformer, ToolTransformerSpec, "transformer"),
            "presenter": (builder.add_result_presenter, ResultPresenterSpec, "presenter"),
        }
        for entry in components.get("policies") or ():
            policy_kind = str((entry.get("config") or {}).get("kind") or "flow")
            method, spec_type, field = policy_types[policy_kind]
            extra = {}
            if policy_kind == "presenter":
                extra = {"match_kinds": tuple(entry.get("match_kinds") or ()), "exclusive": bool(entry.get("exclusive", False))}
            method(spec_type(entry["id"], source, **{field: self._factory_value(entry)}, **extra, **self._common(entry)))
        for entry in components.get("services") or ():
            builder.add_service(ServiceSpec(entry["id"], source, factory=self._factory_value(entry), required=bool(entry.get("required", True)), **self._common(entry)))
        for entry in components.get("surfaces") or ():
            builder.add_surface_adapter(SurfaceAdapterSpec(entry["id"], source, adapter=self._factory_value(entry), **self._common(entry)))
        state = components.get("state") or ()
        if state:
            entry = state[0]
            builder.add_state_codec(StateCodecSpec(entry["id"], source, codec=self._factory_value(entry), **self._common(entry)))

    async def startup(self, context: Any) -> None:
        if self.delegate is not None:
            await self.delegate.startup(context)

    async def shutdown(self, context: Any) -> None:
        if self.delegate is not None:
            await self.delegate.shutdown(context)


__all__ = ["DeclarativeHarness"]
