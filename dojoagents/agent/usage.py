from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator

from dojoagents.agent.compressor import _estimate_tokens_rough
from dojoagents.agent.context_usage import (
    PromptContextSource,
    build_context_snapshot,
    context_snapshot_projection,
    reconcile_context_snapshot,
)
from dojoagents.logging import LOGGER
from dojoagents.sessions.models import (
    ContextUsageSnapshot,
    UsageRecord,
    utc_now,
)


@dataclass(frozen=True)
class UsageScope:
    category: str = "agent_inference"
    operation: str = "agent_inference"
    agent_id: str = ""
    parent_run_id: str | None = None


@dataclass(frozen=True)
class PendingInvocation:
    index: int
    invocation_id: str
    context_snapshot: ContextUsageSnapshot
    event_sink: Any = None


_active_collector: ContextVar["UsageCollector | None"] = ContextVar(
    "dojo_active_usage_collector",
    default=None,
)
_active_scope: ContextVar[UsageScope] = ContextVar(
    "dojo_active_usage_scope",
    default=UsageScope(),
)


def active_usage_collector() -> "UsageCollector | None":
    return _active_collector.get()


@contextmanager
def bind_usage_collector(collector: "UsageCollector") -> Iterator["UsageCollector"]:
    token = _active_collector.set(collector)
    try:
        yield collector
    finally:
        _active_collector.reset(token)


@contextmanager
def usage_scope(
    category: str,
    operation: str = "",
    *,
    agent_id: str = "",
    parent_run_id: str | None = None,
) -> Iterator[UsageScope]:
    scope = UsageScope(
        category=category,
        operation=operation or category,
        agent_id=agent_id,
        parent_run_id=parent_run_id,
    )
    token = _active_scope.set(scope)
    try:
        yield scope
    finally:
        _active_scope.reset(token)


def _integer(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _normalize_usage(
    metadata: dict[str, Any] | None,
    *,
    messages: list[dict[str, Any]],
    content: str,
    estimate_missing: bool,
) -> tuple[dict[str, int], str]:
    raw = (metadata or {}).get("usage")
    if isinstance(raw, dict):
        input_tokens = _integer(raw.get("prompt_tokens", raw.get("input_tokens")))
        output_tokens = _integer(raw.get("completion_tokens", raw.get("output_tokens")))
        total_tokens = _integer(raw.get("total_tokens")) or input_tokens + output_tokens
        available = raw.get("usage_available")
        quality = "estimated" if available is False else "actual"
        return (
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "reasoning_tokens": _integer(raw.get("reasoning_tokens", raw.get("reasoning_token_count"))),
                "cache_read_tokens": _integer(raw.get("cache_read_tokens", raw.get("cached_tokens"))),
                "cache_write_tokens": _integer(raw.get("cache_write_tokens")),
            },
            quality,
        )

    input_tokens = _estimate_tokens_rough(messages) if estimate_missing else 0
    output_tokens = _estimate_tokens_rough([{"role": "assistant", "content": content or ""}]) if estimate_missing else 0
    if input_tokens or output_tokens:
        return (
            {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": input_tokens + output_tokens,
                "reasoning_tokens": 0,
                "cache_read_tokens": 0,
                "cache_write_tokens": 0,
            },
            "estimated",
        )
    return (
        {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "reasoning_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        },
        "unavailable",
    )


class UsageCollector:
    """Run-scoped recorder whose invocation records are the usage source of truth."""

    def __init__(
        self,
        *,
        session_uid: str,
        run_id: str,
        turn_id: str,
        harness_id: str = "",
        agent_id: str = "dojo-agent",
        coordinator: Any | None = None,
    ) -> None:
        self.session_uid = session_uid
        self.run_id = run_id
        self.turn_id = turn_id
        self.harness_id = harness_id
        self.agent_id = agent_id
        self.coordinator = coordinator
        self.records: list[UsageRecord] = []
        self.context_snapshots: list[ContextUsageSnapshot] = []
        self._next_index = 1

    @property
    def last_record(self) -> UsageRecord | None:
        return self.records[-1] if self.records else None

    def begin_invocation(
        self,
        *,
        provider: str,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        metadata: dict[str, Any] | None,
    ) -> PendingInvocation:
        scope = _active_scope.get()
        index = self._next_index
        self._next_index += 1
        invocation_id = f"{self.run_id}:invocation:{index}"
        raw_sources = (metadata or {}).get("_dojo_context_sources") or ()
        sources = tuple(item for item in raw_sources if isinstance(item, PromptContextSource))
        snapshot = build_context_snapshot(
            snapshot_id=f"context-{uuid.uuid4().hex}",
            session_uid=self.session_uid,
            run_id=self.run_id,
            turn_id=self.turn_id,
            invocation_id=invocation_id,
            invocation_index=index,
            agent_id=scope.agent_id or self.agent_id,
            harness_id=self.harness_id,
            provider=provider or "unknown",
            model=model or "unknown",
            messages=messages,
            tools=tools,
            prompt_sources=sources,
            context_window_tokens=int((metadata or {}).get("_dojo_context_window") or 0),
            reserved_output_tokens=int((metadata or {}).get("_dojo_reserved_output_tokens") or 0),
            parent_run_id=scope.parent_run_id,
            invocation_category=scope.category,
            operation=scope.operation,
        )
        if snapshot.manifest_mismatch:
            LOGGER.warning(
                "Context usage prompt manifest mismatch: " "run_id=%s turn_id=%s invocation_id=%s",
                self.run_id,
                self.turn_id,
                invocation_id,
            )
        sink = (metadata or {}).get("_dojo_event_sink")
        if sink is not None and hasattr(sink, "context_usage_snapshot"):
            sink.context_usage_snapshot(
                context_snapshot_projection(snapshot) or {},
                state="estimated",
            )
        return PendingInvocation(index, invocation_id, snapshot, sink)

    async def record(
        self,
        *,
        provider: str,
        model: str,
        metadata: dict[str, Any] | None,
        messages: list[dict[str, Any]],
        content: str,
        status: str = "succeeded",
        started_at: Any = None,
        estimate_missing: bool = True,
        pending: PendingInvocation | None = None,
    ) -> UsageRecord:
        scope = _active_scope.get()
        usage, quality = _normalize_usage(
            metadata,
            messages=messages,
            content=content,
            estimate_missing=estimate_missing,
        )
        if pending is None:
            pending = self.begin_invocation(
                provider=provider,
                model=model,
                messages=messages,
                tools=[],
                metadata=None,
            )
        index = pending.index
        completed_at = utc_now()
        record = UsageRecord(
            usage_id=f"usage-{uuid.uuid4().hex}",
            session_uid=self.session_uid,
            run_id=self.run_id,
            provider=provider or "unknown",
            model=model or "unknown",
            input_tokens=usage["input_tokens"],
            output_tokens=usage["output_tokens"],
            cache_tokens=usage["cache_read_tokens"],
            idempotency_key=f"usage:{self.session_uid}:{self.run_id}:{index}:1",
            created_at=completed_at,
            schema_version=2,
            turn_id=self.turn_id,
            invocation_id=pending.invocation_id,
            invocation_index=index,
            category=scope.category,
            operation=scope.operation,
            total_tokens=usage["total_tokens"],
            reasoning_tokens=usage["reasoning_tokens"],
            cache_read_tokens=usage["cache_read_tokens"],
            cache_write_tokens=usage["cache_write_tokens"],
            quality=quality,
            status=status,
            agent_id=scope.agent_id or self.agent_id,
            harness_id=self.harness_id,
            parent_run_id=scope.parent_run_id,
            started_at=started_at or completed_at,
            completed_at=completed_at,
        )
        if self.coordinator is not None:
            await self.coordinator.append_usage((record,))
        self.records.append(record)
        actual_input = record.input_tokens if record.quality == "actual" else None
        context_snapshot = reconcile_context_snapshot(
            pending.context_snapshot,
            actual_input_tokens=actual_input,
            status=status,
        )
        if self.coordinator is not None:
            try:
                await self.coordinator.append_context_usage((context_snapshot,))
            except Exception:
                LOGGER.exception(
                    "Context usage persistence failed: " "run_id=%s turn_id=%s invocation_id=%s",
                    self.run_id,
                    self.turn_id,
                    pending.invocation_id,
                )
        self.context_snapshots.append(context_snapshot)
        if pending.event_sink is not None and hasattr(
            pending.event_sink,
            "context_usage_snapshot",
        ):
            pending.event_sink.context_usage_snapshot(
                context_snapshot_projection(context_snapshot) or {},
                state="reconciled",
            )
        return record

    def summary(self) -> dict[str, Any]:
        totals = {
            "prompt_tokens": sum(item.input_tokens for item in self.records),
            "completion_tokens": sum(item.output_tokens for item in self.records),
            "total_tokens": sum(item.effective_total_tokens for item in self.records),
            "reasoning_tokens": sum(item.reasoning_tokens for item in self.records),
            "cache_read_tokens": sum(item.cache_read_tokens for item in self.records),
            "cache_write_tokens": sum(item.cache_write_tokens for item in self.records),
            "calls": len(self.records),
        }
        grouped: dict[str, list[UsageRecord]] = {}
        for record in self.records:
            grouped.setdefault(record.category, []).append(record)
        groups = []
        for category, records in sorted(grouped.items()):
            groups.append(
                {
                    "dimensions": {"category": category},
                    "totals": {
                        "input_tokens": sum(item.input_tokens for item in records),
                        "output_tokens": sum(item.output_tokens for item in records),
                        "total_tokens": sum(item.effective_total_tokens for item in records),
                        "calls": len(records),
                    },
                }
            )
        return {
            "run_id": self.run_id,
            "turn_id": self.turn_id,
            "totals": totals,
            "groups": groups,
            "coverage": {
                "actual_calls": sum(item.quality == "actual" for item in self.records),
                "estimated_calls": sum(item.quality == "estimated" for item in self.records),
                "unavailable_calls": sum(item.quality == "unavailable" for item in self.records),
            },
        }


class MeteredLLMProvider:
    """Transparent provider wrapper that records each provider invocation once."""

    def __init__(self, provider: Any) -> None:
        self._provider = provider

    def __getattr__(self, name: str) -> Any:
        return getattr(self._provider, name)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        model: str,
        **kwargs: Any,
    ) -> Any:
        collector = active_usage_collector()
        started_at = utc_now()
        started = time.perf_counter()
        provider_name = str(
            getattr(
                self._provider,
                "name",
                type(self._provider).__name__,
            )
        )
        metadata = kwargs.get("metadata")
        pending = (
            collector.begin_invocation(
                provider=provider_name,
                model=model,
                messages=messages,
                tools=tools,
                metadata=metadata if isinstance(metadata, dict) else None,
            )
            if collector is not None
            else None
        )
        try:
            result = await self._provider.chat(
                messages,
                tools,
                model=model,
                **kwargs,
            )
        except BaseException as exc:
            if collector is not None:
                await collector.record(
                    provider=provider_name,
                    model=model,
                    metadata=None,
                    messages=messages,
                    content="",
                    status="cancelled" if isinstance(exc, asyncio.CancelledError) else "failed",
                    started_at=started_at,
                    estimate_missing=False,
                    pending=pending,
                )
            raise
        if collector is not None:
            await collector.record(
                provider=provider_name,
                model=model,
                metadata=getattr(result, "metadata", None),
                messages=messages,
                content=str(getattr(result, "content", "") or ""),
                started_at=started_at,
                pending=pending,
            )
            LOGGER.debug(
                "LLM usage recorded: run_id=%s turn_id=%s model=%s latency_ms=%d",
                collector.run_id,
                collector.turn_id,
                model,
                int((time.perf_counter() - started) * 1000),
            )
        return result


def ensure_metered_provider(provider: Any) -> MeteredLLMProvider:
    return provider if isinstance(provider, MeteredLLMProvider) else MeteredLLMProvider(provider)
