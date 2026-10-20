"""Fine-grained timing for tool execution.

Tools are the least transparent hop in the agent loop: a single ``tool_result``
only reports end-to-end latency, so a 40s call cannot be attributed to the
upstream HTTP request, the database query, or result post-processing.

This module stays out of the hot path:

* ``collect_tool_timing()`` opens a per-invocation collector in a ContextVar, so
  concurrent ``execute_many`` tasks never share counters.
* ``tool_span(name)`` is a no-op when no collector is active (e.g. unit tests or
  direct ``spec.handler`` calls), so adopting it is always safe.
* Spans are emitted as plain dicts, which is what ``ToolResult.metadata`` and
  the ``tool_result`` event payload already accept — no schema change needed.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Iterator
from contextvars import ContextVar
from typing import Any


class ToolTimingCollector:
    """Collects nested spans for one tool invocation."""

    __slots__ = ("_origin", "_stack", "spans", "wait_ms")

    def __init__(self) -> None:
        self._origin = time.perf_counter()
        self._stack: list[dict[str, Any]] = []
        self.spans: list[dict[str, Any]] = []
        # Time spent waiting for a concurrency slot / semaphore before the
        # handler starts. Callers set it explicitly when they know about it.
        self.wait_ms = 0

    def offset_ms(self) -> int:
        return int((time.perf_counter() - self._origin) * 1000)

    @contextlib.contextmanager
    def span(self, name: str, category: str = "internal") -> Iterator[dict[str, Any]]:
        started = time.perf_counter()
        node: dict[str, Any] = {
            "name": name,
            "category": category,
            "offset_ms": self.offset_ms(),
            "depth": len(self._stack),
        }
        self._stack.append(node)
        try:
            yield node
        finally:
            self._stack.pop()
            node["duration_ms"] = int((time.perf_counter() - started) * 1000)
            self.spans.append(node)

    def snapshot(self, *, handler_ms: int = 0, postprocess_ms: int = 0) -> dict[str, Any]:
        return {
            "wait_ms": self.wait_ms,
            "handler_ms": handler_ms,
            "postprocess_ms": postprocess_ms,
            "total_ms": self.offset_ms(),
            "spans": list(self.spans),
        }


_ACTIVE: ContextVar[ToolTimingCollector | None] = ContextVar("dojo_tool_timing", default=None)


@contextlib.contextmanager
def collect_tool_timing() -> Iterator[ToolTimingCollector]:
    collector = ToolTimingCollector()
    token = _ACTIVE.set(collector)
    try:
        yield collector
    finally:
        _ACTIVE.reset(token)


def tool_span(name: str, category: str = "internal") -> contextlib.AbstractContextManager[Any]:
    """Mark a sub-step inside a tool handler.

    Usage (sync or async handlers are both fine):

        with tool_span("upstream_quote", category="http"):
            data = await client.get(...)
    """
    collector = _ACTIVE.get()
    if collector is None:
        return contextlib.nullcontext()
    return collector.span(name, category)


def record_wait_ms(wait_ms: int) -> None:
    """Attribute queueing time before the handler could start."""
    collector = _ACTIVE.get()
    if collector is not None:
        collector.wait_ms = max(0, int(wait_ms))
