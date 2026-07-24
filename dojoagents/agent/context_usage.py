"""Invocation-level context composition metering.

This module deliberately keeps prompt content in memory only. Persisted
components contain counts, stable source identifiers, and hashes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any, Iterable, Mapping, Protocol, Sequence

from dojoagents.agent.compressor import _estimate_tokens_rough
from dojoagents.sessions.models import (
    ContextCategory,
    ContextComponent,
    ContextUsageSnapshot,
    JsonValue,
    utc_now,
)

_PHASE_CATEGORY: dict[str, ContextCategory] = {
    "identity": "system_prompt",
    "temporal": "system_prompt",
    "core_safety": "rules",
    "harness_instructions": "rules",
    "skills": "skills",
    "memory": "memory",
    "request_context": "rules",
    "channel_policy": "rules",
    "task_context": "rules",
    "turn_policy": "rules",
    "subagent_definitions": "subagent_definitions",
    "attachments": "attachments",
}
_CATEGORY_ORDER = {
    category: index
    for index, category in enumerate(
        (
            "system_prompt",
            "tool_definitions",
            "rules",
            "skills",
            "subagent_definitions",
            "conversation",
            "memory",
            "attachments",
            "protocol_overhead",
            "other",
        )
    )
}


@dataclass(frozen=True)
class PromptContextSource:
    component_id: str
    phase: str
    content: str
    source: str
    category: ContextCategory | None = None

    @property
    def effective_category(self) -> ContextCategory:
        return self.category or _PHASE_CATEGORY.get(self.phase, "other")


def category_for_prompt_phase(phase: str) -> ContextCategory:
    return _PHASE_CATEGORY.get(phase, "other")


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


@dataclass(frozen=True)
class TokenCount:
    tokens: int
    quality: str
    estimator_id: str


class TokenEstimator(Protocol):
    def count_text(self, text: str, *, model: str) -> TokenCount: ...


class RoughTokenEstimator:
    estimator_id = "rough-char-v1"

    def __init__(self, *, max_cache_entries: int = 8192) -> None:
        self.max_cache_entries = max(0, max_cache_entries)
        self._cache: dict[tuple[str, str], int] = {}

    def count_text(self, text: str, *, model: str) -> TokenCount:
        key = (model, content_hash(text))
        tokens = self._cache.get(key)
        if tokens is None:
            tokens = _estimate_tokens_rough([{"role": "system", "content": text}])
            if self.max_cache_entries:
                if len(self._cache) >= self.max_cache_entries:
                    self._cache.pop(next(iter(self._cache)))
                self._cache[key] = tokens
        return TokenCount(
            tokens=tokens,
            quality="rough_estimate",
            estimator_id=self.estimator_id,
        )


DEFAULT_TOKEN_ESTIMATOR: TokenEstimator = RoughTokenEstimator()


def _component(
    component_id: str,
    category: ContextCategory,
    source: str,
    content: str,
    *,
    model: str,
    metadata: Mapping[str, JsonValue] | None = None,
) -> ContextComponent:
    count = DEFAULT_TOKEN_ESTIMATOR.count_text(content, model=model)
    return ContextComponent(
        component_id=component_id,
        category=category,
        source=source,
        content_hash=content_hash(content),
        estimated_tokens=count.tokens,
        character_count=len(content),
        quality="rough_estimate",
        metadata={
            **dict(metadata or {}),
            "estimator_id": count.estimator_id,
        },
    )


def _system_text(messages: Sequence[Mapping[str, Any]]) -> str:
    return "\n\n".join(str(message.get("content") or "") for message in messages if message.get("role") == "system")


def _conversation_source(message: Mapping[str, Any]) -> str:
    role = str(message.get("role") or "unknown")
    if role == "tool":
        return "conversation:history.tool_result"
    if role == "assistant" and message.get("tool_calls"):
        return "conversation:history.tool_call"
    return f"conversation:history.{role}"


def build_context_snapshot(
    *,
    snapshot_id: str,
    session_uid: str,
    run_id: str,
    turn_id: str,
    invocation_id: str,
    invocation_index: int,
    agent_id: str,
    harness_id: str,
    provider: str,
    model: str,
    messages: Sequence[Mapping[str, Any]],
    tools: Sequence[Mapping[str, Any]],
    prompt_sources: Iterable[PromptContextSource] = (),
    context_window_tokens: int = 0,
    reserved_output_tokens: int = 0,
    parent_run_id: str | None = None,
    invocation_category: str = "agent_inference",
    operation: str = "agent_inference",
) -> ContextUsageSnapshot:
    components: list[ContextComponent] = []
    sources = tuple(prompt_sources)
    rendered_manifest = "\n\n".join(source.content for source in sources if source.content)
    rendered_system = _system_text(messages)
    manifest_mismatch = bool(rendered_system) and rendered_manifest != rendered_system

    if sources and not manifest_mismatch:
        components.extend(
            _component(
                source.component_id,
                source.effective_category,
                source.source,
                source.content,
                model=model,
                metadata={"phase": source.phase},
            )
            for source in sources
            if source.content
        )
    elif rendered_system:
        components.append(
            _component(
                "system:unattributed",
                "other",
                "core:model-bridge",
                rendered_system,
                model=model,
                metadata={"manifest_mismatch": manifest_mismatch},
            )
        )

    for index, tool in enumerate(tools):
        serialized = _canonical_json(tool)
        name = str(tool.get("name") or f"tool-{index}")
        components.append(
            _component(
                f"tool:{name}:{index}",
                "tool_definitions",
                str(tool.get("_dojo_source") or f"tool:{name}"),
                serialized,
                model=model,
                metadata={"tool_name": name},
            )
        )

    conversation_index = 0
    for message in messages:
        if message.get("role") == "system":
            continue
        content = message.get("content")
        plugin_marker = "\n\n[Plugin Context]\n"
        if message.get("role") == "user" and isinstance(content, str) and plugin_marker in content:
            base_content, *plugin_blocks = content.split(plugin_marker)
            if base_content:
                base_message = dict(message)
                base_message["content"] = base_content
                serialized = _canonical_json(base_message)
                components.append(
                    _component(
                        f"conversation:{conversation_index}",
                        "conversation",
                        "conversation:history.user",
                        serialized,
                        model=model,
                        metadata={"role": "user"},
                    )
                )
                conversation_index += 1
            for plugin_index, plugin_content in enumerate(plugin_blocks):
                is_subagent = "specialist agents that you can delegate tasks to" in plugin_content
                components.append(
                    _component(
                        ("subagent:plugin:" if is_subagent else "rules:plugin:") + str(plugin_index),
                        ("subagent_definitions" if is_subagent else "rules"),
                        "plugin:pre_llm_call",
                        plugin_content,
                        model=model,
                        metadata={"role": "user"},
                    )
                )
            continue
        attachment_marker = next(
            (
                marker
                for marker in (
                    "\n\n## Attached Files",
                    "\n\n## 用户上传文件",
                )
                if isinstance(content, str) and marker in content
            ),
            None,
        )
        if attachment_marker is not None:
            base_content, attachment_content = content.rsplit(
                attachment_marker,
                1,
            )
            if base_content:
                base_message = dict(message)
                base_message["content"] = base_content
                components.append(
                    _component(
                        f"conversation:{conversation_index}",
                        "conversation",
                        "conversation:history.user",
                        _canonical_json(base_message),
                        model=model,
                        metadata={"role": "user"},
                    )
                )
                conversation_index += 1
            components.append(
                _component(
                    "attachments:current-user",
                    "attachments",
                    "core:session-attachments",
                    attachment_marker.lstrip() + attachment_content,
                    model=model,
                    metadata={"role": "user"},
                )
            )
            continue
        serialized = _canonical_json(message)
        components.append(
            _component(
                f"conversation:{conversation_index}",
                "conversation",
                _conversation_source(message),
                serialized,
                model=model,
                metadata={"role": str(message.get("role") or "unknown")},
            )
        )
        conversation_index += 1

    estimated = sum(item.estimated_tokens for item in components)
    return ContextUsageSnapshot(
        snapshot_id=snapshot_id,
        session_uid=session_uid,
        run_id=run_id,
        turn_id=turn_id,
        invocation_id=invocation_id,
        invocation_index=invocation_index,
        agent_id=agent_id,
        harness_id=harness_id,
        provider=provider,
        model=model,
        context_window_tokens=max(0, int(context_window_tokens or 0)),
        estimated_input_tokens=estimated,
        actual_input_tokens=None,
        reconciliation_delta_tokens=0,
        reserved_output_tokens=max(0, int(reserved_output_tokens or 0)),
        quality="rough_estimate",
        components=tuple(components),
        captured_at=utc_now(),
        idempotency_key=(f"context:{session_uid}:{run_id}:{invocation_id}:1"),
        invocation_category=invocation_category,
        operation=operation,
        parent_run_id=parent_run_id,
        manifest_mismatch=manifest_mismatch,
    )


def reconcile_context_snapshot(
    snapshot: ContextUsageSnapshot,
    *,
    actual_input_tokens: int | None,
    status: str,
) -> ContextUsageSnapshot:
    actual = max(0, int(actual_input_tokens)) if actual_input_tokens is not None else None
    delta = actual - snapshot.estimated_input_tokens if actual is not None else 0
    components = list(snapshot.components)
    if delta > 0:
        components.append(
            ContextComponent(
                component_id="provider:protocol-overhead",
                category="protocol_overhead",
                source="provider:reconciliation",
                content_hash=content_hash(f"{snapshot.provider}:{snapshot.model}:{delta}"),
                estimated_tokens=delta,
                character_count=0,
                quality="provider_reconciled",
                metadata={},
            )
        )
    return replace(
        snapshot,
        actual_input_tokens=actual,
        reconciliation_delta_tokens=delta,
        quality=("provider_reconciled" if actual is not None else snapshot.quality),
        components=tuple(components),
        status=status,
        reconciled_at=utc_now(),
    )


def context_snapshot_projection(
    snapshot: ContextUsageSnapshot | None,
    *,
    detail: str = "category",
) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    denominator = snapshot.used_tokens or snapshot.estimated_input_tokens
    for component in snapshot.components:
        source = component.source if detail == "source" else ""
        key = (component.category, source)
        item = grouped.setdefault(
            key,
            {
                "category": component.category,
                "tokens": 0,
                "character_count": 0,
                "quality": component.quality,
            },
        )
        if source:
            item["source"] = source
        item["tokens"] += component.estimated_tokens
        item["character_count"] += component.character_count
        if item["quality"] != component.quality:
            item["quality"] = "rough_estimate"

    breakdown = []
    for item in sorted(
        grouped.values(),
        key=lambda value: (
            _CATEGORY_ORDER.get(str(value["category"]), 999),
            str(value.get("source") or ""),
        ),
    ):
        item["ratio"] = item["tokens"] / denominator if denominator > 0 else 0.0
        breakdown.append(item)

    used = snapshot.used_tokens
    available = max(0, snapshot.context_window_tokens - used)
    headroom = max(0, available - snapshot.reserved_output_tokens)
    return {
        "snapshot_id": snapshot.snapshot_id,
        "run_id": snapshot.run_id,
        "turn_id": snapshot.turn_id,
        "invocation_id": snapshot.invocation_id,
        "invocation_index": snapshot.invocation_index,
        "invocation_category": snapshot.invocation_category,
        "operation": snapshot.operation,
        "agent_id": snapshot.agent_id,
        "harness_id": snapshot.harness_id,
        "provider": snapshot.provider,
        "model": snapshot.model,
        "captured_at": snapshot.captured_at.isoformat(),
        "reconciled_at": (snapshot.reconciled_at.isoformat() if snapshot.reconciled_at is not None else None),
        "status": snapshot.status,
        "context_window_tokens": snapshot.context_window_tokens,
        "used_tokens": used,
        "used_tokens_source": ("provider_actual" if snapshot.actual_input_tokens is not None else "local_estimate"),
        "available_tokens": available,
        "reserved_output_tokens": snapshot.reserved_output_tokens,
        "headroom_after_output_reserve": headroom,
        "utilization_ratio": (used / snapshot.context_window_tokens if snapshot.context_window_tokens > 0 else 0.0),
        "is_over_limit": (snapshot.context_window_tokens > 0 and used > snapshot.context_window_tokens),
        "categorized_estimated_tokens": snapshot.estimated_input_tokens,
        "reconciliation_delta_tokens": (snapshot.reconciliation_delta_tokens),
        "quality": snapshot.quality,
        "manifest_mismatch": snapshot.manifest_mismatch,
        "ratio_basis": ("actual_input_tokens" if snapshot.actual_input_tokens is not None else "estimated_input_tokens"),
        "breakdown": breakdown,
    }


__all__ = [
    "PromptContextSource",
    "RoughTokenEstimator",
    "TokenCount",
    "TokenEstimator",
    "build_context_snapshot",
    "category_for_prompt_phase",
    "content_hash",
    "context_snapshot_projection",
    "reconcile_context_snapshot",
]
