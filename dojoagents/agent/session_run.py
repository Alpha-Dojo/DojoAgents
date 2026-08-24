"""Canonical session/run envelope around one AgentLoop invocation."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field, replace
from typing import Any

from dojoagents.agent.events import AgentEvent, AgentEventSink
from dojoagents.agent.models import AgentResponse, ChatRequest
from dojoagents.harnesses.base import HarnessDescriptor
from dojoagents.logging import LOGGER
from dojoagents.sessions.errors import SessionNotFoundError
from dojoagents.sessions.memory_sync import SessionMemorySyncWorker
from dojoagents.sessions.models import (
    HistoryQuery,
    SessionCreateSpec,
    SessionMessageRecord,
    TurnQuery,
    TurnRecord,
)
from dojoagents.sessions.compat.strands import (
    canonical_to_strands,
    strands_to_canonical,
)
from dojoagents.sessions.run_coordinator import RunCoordinator
from dojoagents.sessions.service import SessionService


def _history_message(record: SessionMessageRecord) -> dict[str, Any]:
    message = canonical_to_strands(record)
    if record.message_id:
        message["message_id"] = record.message_id
    return message


def _durable_run_id(*, event_sink: AgentEventSink | None, metadata: dict[str, Any]) -> str:
    """Resolve the durable session-store run id for one agent.invoke.

    Dashboard AgentRunManager reuses one outer ``event_sink.run_id`` across
    pipeline steps for SSE. Each ``agent.run`` still commits the durable run as
    completed, so continuation steps must mint a distinct durable id or
    ``begin_run_with_lease`` raises SessionConflictError on the completed id.
    """
    base = str((event_sink.run_id if event_sink is not None else None) or metadata.get("run_id") or f"run-{uuid.uuid4().hex}").strip()
    pipeline = metadata.get("pipeline")
    if not isinstance(pipeline, dict):
        return base
    try:
        step = int(pipeline.get("step") or 1)
    except (TypeError, ValueError):
        step = 1
    if step <= 1:
        return base
    return f"{base}:step:{step}"


class _DurableEventWriter:
    """Persist AgentEventSink output in order while the run is still active."""

    def __init__(self, coordinator: RunCoordinator, sink: AgentEventSink) -> None:
        self.coordinator = coordinator
        self.sink = sink
        self.queue: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
        self._closed = False
        self.sink.add_listener(self._enqueue)
        self.task = asyncio.create_task(
            self._run(),
            name=f"dojo-events:{coordinator.run_id}",
        )

    def _enqueue(self, event: AgentEvent) -> None:
        if not self._closed:
            self.queue.put_nowait(event)

    async def _persist(self, events: list[AgentEvent]) -> None:
        if not events:
            return
        from dojoagents.sessions.errors import SessionLeaseLostError

        last_exc: Exception | None = None
        for attempt in range(1, 5):
            try:
                await self.coordinator.append_events(tuple((event.type, event.to_dict()) for event in events))
                # RunCoordinator's size threshold reduces store calls for bursts, while
                # this explicit flush guarantees that an idle SSE reader sees the burst
                # before the Agent turn finishes.
                await self.coordinator.flush()
                LOGGER.debug(
                    "Canonical run events persisted: run_id=%s count=%d first_seq=%d last_seq=%d",
                    self.coordinator.run_id,
                    len(events),
                    events[0].seq,
                    events[-1].seq,
                )
                return
            except SessionLeaseLostError:
                LOGGER.exception(
                    "Canonical run event persist lost lease: run_id=%s count=%d",
                    self.coordinator.run_id,
                    len(events),
                )
                raise
            except Exception as exc:
                last_exc = exc
                LOGGER.warning(
                    "Canonical run event persist retry %d/4: run_id=%s error=%s",
                    attempt,
                    self.coordinator.run_id,
                    exc,
                )
                await asyncio.sleep(min(0.05 * (2 ** (attempt - 1)), 0.8))
        assert last_exc is not None
        raise last_exc

    async def _run(self) -> None:
        from dojoagents.sessions.errors import SessionLeaseLostError

        while True:
            item = await self.queue.get()
            if item is None:
                return
            pending = [item]
            await asyncio.sleep(0)
            while len(pending) < self.coordinator.service.config.runtime.event_batch_size:
                try:
                    queued = self.queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if queued is None:
                    try:
                        await self._persist(pending)
                    except SessionLeaseLostError:
                        return
                    return
                pending.append(queued)
            try:
                await self._persist(pending)
            except SessionLeaseLostError:
                return

    async def close(self) -> None:
        if self._closed:
            await self.task
            return
        self._closed = True
        self.sink.remove_listener(self._enqueue)
        self.queue.put_nowait(None)
        await self.task


class _RunHeartbeat:
    """Renew the session lease and convert durable cancellation into task cancellation."""

    def __init__(self, coordinator: RunCoordinator, owner_task: asyncio.Task[Any]) -> None:
        self.coordinator = coordinator
        self.owner_task = owner_task
        configured = float(coordinator.service.config.runtime.heartbeat_seconds)
        self.interval = max(0.1, configured)
        self._transient_failures = 0
        self.task = asyncio.create_task(
            self._run(),
            name=f"dojo-heartbeat:{coordinator.run_id}",
        )

    async def _run(self) -> None:
        from dojoagents.sessions.errors import SessionLeaseLostError

        try:
            while True:
                try:
                    # Renew first, then sleep — do not burn the first interval unprotected.
                    result = await self.coordinator.heartbeat()
                except SessionLeaseLostError:
                    LOGGER.exception(
                        "Canonical run lost session lease during heartbeat: run_id=%s session_id=%s",
                        self.coordinator.run_id,
                        self.coordinator.session_id,
                    )
                    self.owner_task.cancel()
                    return
                except Exception:
                    self._transient_failures += 1
                    LOGGER.exception(
                        "Canonical run heartbeat failed (attempt %d): run_id=%s session_id=%s",
                        self._transient_failures,
                        self.coordinator.run_id,
                        self.coordinator.session_id,
                    )
                    # Store/lock blips should not kill long pipeline runs. Retry until
                    # the next interval; only hard-cancel after repeated failures.
                    if self._transient_failures >= 3:
                        self.owner_task.cancel()
                        return
                    await asyncio.sleep(self.interval)
                    continue
                self._transient_failures = 0
                if result.cancellation_requested:
                    LOGGER.info(
                        "Canonical run observed cancellation request: run_id=%s session_id=%s",
                        self.coordinator.run_id,
                        self.coordinator.session_id,
                    )
                    self.owner_task.cancel()
                    return
                await asyncio.sleep(self.interval)
        except asyncio.CancelledError:
            raise

    async def close(self) -> None:
        if not self.task.done():
            self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass


@dataclass
class CanonicalAgentRun:
    service: SessionService
    coordinator: RunCoordinator
    request: ChatRequest
    descriptor: HarnessDescriptor
    session_uid: str
    turn_id: str
    turn_sequence: int
    message_sequence: int
    event_sink: AgentEventSink
    event_writer: _DurableEventWriter
    heartbeat: _RunHeartbeat
    agent_id: str
    memory_sync_worker: SessionMemorySyncWorker | None = None
    recovering: bool = False
    replay_from_start: bool = False
    message_base: int = 0
    checkpointed_message_ids: set[str] = field(default_factory=set, repr=False)
    checkpoint_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    @classmethod
    async def begin(
        cls,
        service: SessionService,
        request: ChatRequest,
        descriptor: HarnessDescriptor,
        *,
        model: str,
        agent_id: str,
        event_sink: AgentEventSink | None = None,
        memory_sync_worker: SessionMemorySyncWorker | None = None,
    ) -> "CanonicalAgentRun":
        principal = request.principal
        if principal is None:  # ChatRequest validates this; defensive for alternate request implementations.
            raise ValueError("canonical sessions require a principal")
        try:
            session = await service.get_session(principal, request.session_id)
        except SessionNotFoundError:
            session = await service.create_session(
                principal,
                SessionCreateSpec(
                    session_id=request.session_id,
                    harness_id=descriptor.id,
                    harness_version=descriptor.version,
                    harness_state_schema_version=descriptor.state_schema_version,
                    title=request.message.strip().replace("\n", " ")[:80],
                    model=model,
                    metadata={"channel": request.channel},
                ),
            )
        if session.harness_id != descriptor.id:
            from dojoagents.sessions.errors import HarnessSessionIncompatibleError

            raise HarnessSessionIncompatibleError(f"session is bound to harness {session.harness_id!r}, not {descriptor.id!r}")

        history = await service.history(principal, request.session_id, HistoryQuery(limit=10_000))
        recovering = bool(request.metadata.get("_dojo_recovering"))
        pending_messages: tuple[SessionMessageRecord, ...] = ()
        if recovering:
            run_id = _durable_run_id(event_sink=event_sink, metadata=request.metadata)
            pending_messages = await service.load_run_messages(principal, run_id)
        replay_from_start = recovering and len(pending_messages) <= 1
        metadata = dict(request.metadata)
        metadata["defer_run_done"] = True
        durable_history = [_history_message(item) for item in history.items]
        if recovering and not replay_from_start:
            durable_history.extend(_history_message(item) for item in pending_messages)
            metadata["history"] = durable_history
            request = replace(
                request,
                message=("Continue the interrupted turn from the durable transcript. " "Do not repeat completed tool calls."),
                runtime_content=None,
                metadata=metadata,
            )
        else:
            if durable_history or "history" not in metadata:
                metadata["history"] = durable_history
            request = replace(request, metadata=metadata)

        turns = await service.turns(principal, request.session_id, TurnQuery(limit=10_000))
        turn_sequence = max((item.sequence for item in turns.items), default=0) + 1
        message_sequence = (
            max(
                (item.sequence for item in (*history.items, *pending_messages)),
                default=0,
            )
            + 1
        )
        if event_sink is not None and event_sink.session_id != request.session_id:
            raise ValueError("event sink session_id does not match request session_id")
        run_id = _durable_run_id(event_sink=event_sink, metadata=metadata)
        turn_id = str(metadata.get("turn_id") or f"turn-{uuid.uuid4().hex}")
        coordinator = RunCoordinator(
            service,
            principal,
            request.session_id,
            holder_id=str(metadata.get("_run_holder_id") or f"agent:{agent_id}:{uuid.uuid4().hex}"),
            model=model,
        )
        await coordinator.begin(run_id, idempotency_key=str(metadata.get("idempotency_key") or turn_id))
        LOGGER.info(
            "Canonical agent run started: run_id=%s session_id=%s harness_id=%s lease_expires_at=%s",
            run_id,
            request.session_id,
            descriptor.id,
            (coordinator.handle.lease.expires_at.isoformat() if coordinator.handle is not None else None),
        )
        sink = event_sink or AgentEventSink(run_id=run_id, session_id=request.session_id)
        owner_task = asyncio.current_task()
        if owner_task is None:
            raise RuntimeError("canonical run requires an active asyncio task")
        event_writer = _DurableEventWriter(coordinator, sink)
        heartbeat = _RunHeartbeat(coordinator, owner_task)
        canonical = cls(
            service=service,
            coordinator=coordinator,
            request=request,
            descriptor=descriptor,
            session_uid=session.session_uid,
            turn_id=turn_id,
            turn_sequence=turn_sequence,
            message_sequence=message_sequence,
            event_sink=sink,
            event_writer=event_writer,
            heartbeat=heartbeat,
            agent_id=agent_id,
            memory_sync_worker=memory_sync_worker,
            recovering=recovering,
            replay_from_start=replay_from_start,
            message_base=(0 if replay_from_start else len(pending_messages)),
        )
        if recovering and not replay_from_start:
            await canonical.persist_transcript(
                [{"role": "user", "content": request.message}],
            )
        return canonical

    async def _prepare_terminal(self) -> None:
        await self.heartbeat.close()
        await self.event_writer.close()

    def _turn_messages(
        self,
        transcript: list[dict[str, Any]] | None,
        response: AgentResponse | None = None,
    ) -> tuple[SessionMessageRecord, ...]:
        raw_messages = [dict(message) for message in (transcript or []) if isinstance(message, dict) and message.get("role") in {"user", "assistant", "tool", "system"}]
        continuation = self.recovering and not self.replay_from_start
        if not continuation:
            original_message = str(self.request.metadata.get("_recovery_original_message") or self.request.message)
            safe_user = {"role": "user", "content": [{"text": original_message}]}
            if (
                raw_messages
                and raw_messages[0].get("role") == "user"
                and not any(isinstance(block, dict) and "toolResult" in block for block in (raw_messages[0].get("content") or []))
            ):
                raw_messages[0] = safe_user
            else:
                raw_messages.insert(0, safe_user)

        if response is not None:
            final_content = raw_messages[-1].get("content") if raw_messages else None
            final_has_text = isinstance(final_content, str) and bool(final_content.strip())
            if isinstance(final_content, list):
                final_has_text = any(isinstance(block, dict) and bool(str(block.get("text") or "").strip()) for block in final_content)
            if not raw_messages or raw_messages[-1].get("role") != "assistant" or (response.content and not final_has_text):
                raw_messages.append({"role": "assistant", "content": [{"text": response.content}]})

        records: list[SessionMessageRecord] = []
        for offset, raw in enumerate(raw_messages):
            record = strands_to_canonical(
                raw,
                session_uid=self.session_uid,
                session_id=self.request.session_id,
                agent_id=self.agent_id,
                sequence=self.message_sequence + offset,
            )
            content = raw.get("content")
            blocks = content if isinstance(content, list) else ()
            has_tool_use = any(isinstance(block, dict) and "toolUse" in block for block in blocks)
            has_tool_result = any(isinstance(block, dict) and "toolResult" in block for block in blocks)
            if continuation and offset == 0 and raw.get("role") == "user":
                boundary_kind = "recovery_control"
                visibility = "internal"
            elif has_tool_use:
                boundary_kind = "assistant_tool_use"
                visibility = "conversation"
            elif has_tool_result or raw.get("role") == "tool":
                boundary_kind = "tool_result"
                visibility = "conversation"
            elif raw.get("role") == "user":
                boundary_kind = "user_input"
                visibility = "conversation"
            else:
                boundary_kind = "final_assistant"
                visibility = "conversation"
            ordinal = self.message_base + offset
            records.append(
                replace(
                    record,
                    message_id=f"{self.turn_id}:message:{ordinal}",
                    run_id=self.coordinator.run_id,
                    turn_id=self.turn_id,
                    state="pending",
                    boundary_kind=boundary_kind,
                    visibility=visibility,
                )
            )
        return tuple(records)

    async def persist_transcript(
        self,
        transcript: list[dict[str, Any]] | None,
        response: AgentResponse | None = None,
    ) -> tuple[SessionMessageRecord, ...]:
        messages = self._turn_messages(transcript, response)
        async with self.checkpoint_lock:
            pending = tuple(message for message in messages if message.message_id not in self.checkpointed_message_ids)
            persisted = await self.coordinator.append_messages(pending)
            self.checkpointed_message_ids.update(message.message_id for message in pending if message.message_id)
            return persisted

    async def start_tool(
        self,
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
    ):
        mutation_tools = frozenset(str(item) for item in self.request.metadata.get("_mutation_tools", ()))
        return await self.coordinator.start_tool(
            call_id,
            tool_name,
            arguments,
            tool_name in mutation_tools,
        )

    async def finish_tool(
        self,
        call_id: str,
        result: Any,
        ok: bool,
    ):
        return await self.coordinator.finish_tool(call_id, result, ok)

    async def commit(self, response: AgentResponse, *, transcript: list[dict[str, Any]] | None = None) -> TurnRecord:
        principal = self.request.principal
        assert principal is not None
        LOGGER.info(
            "Canonical agent run commit started: run_id=%s session_id=%s buffered_event_count=%d",
            self.coordinator.run_id,
            self.request.session_id,
            len(self.event_sink.events),
        )
        await self.persist_transcript(transcript, response)
        await self._prepare_terminal()
        completion = {"stopped": response.metadata.get("stopped")}
        if isinstance(response.metadata.get("cache"), dict):
            completion["cache"] = dict(response.metadata["cache"])
        turn = TurnRecord(
            session_uid=self.session_uid,
            session_id=self.request.session_id,
            run_id=self.coordinator.run_id,
            turn_id=self.turn_id,
            sequence=self.turn_sequence,
            input={
                "message": str(self.request.metadata.get("_recovery_original_message") or self.request.message),
                "context": self.request.context,
            },
            output={"content": response.content},
            completion=completion,
            tool_trace=tuple(response.metadata.get("tool_trace") or ()),
        )
        # Invocation-level usage is appended immediately by UsageCollector.
        # Persisting the Turn aggregate here would double-count the same calls.
        committed = await self.coordinator.commit(
            turn,
            terminal_payload={
                "model_id": str(response.metadata.get("model_id") or ""),
                "tool_trace": list(response.metadata.get("tool_trace") or ()),
                "tool_steps": len(response.metadata.get("tool_trace") or ()),
            },
        )
        if self.coordinator.terminal_event is not None:
            self.event_sink.replay(self.coordinator.terminal_event.payload)
        LOGGER.info(
            "Canonical agent run committed: run_id=%s session_id=%s persisted_event_count=%d",
            self.coordinator.run_id,
            self.request.session_id,
            len(self.event_sink.events),
        )
        if self.memory_sync_worker is not None:
            try:
                await self.memory_sync_worker.sync_pending(principal, self.request.session_id)
            except Exception:
                LOGGER.exception("Post-commit session memory sync failed")
        return committed

    async def fail(self, error: BaseException) -> None:
        LOGGER.exception(
            "Canonical agent run failing: run_id=%s session_id=%s buffered_event_count=%d error_type=%s error=%s",
            self.coordinator.run_id,
            self.request.session_id,
            len(self.event_sink.events),
            type(error).__name__,
            error,
        )
        await self._prepare_terminal()
        code = "chat_deadline_exceeded" if isinstance(error, TimeoutError) else "agent_run_failed"
        await self.coordinator.fail({"code": code, "type": type(error).__name__, "message": str(error)})
        if self.coordinator.terminal_event is not None:
            self.event_sink.replay(self.coordinator.terminal_event.payload)

    async def cancel(self) -> None:
        await self._prepare_terminal()
        await self.coordinator.cancel({"code": "agent_run_cancelled"})
        if self.coordinator.terminal_event is not None:
            self.event_sink.replay(self.coordinator.terminal_event.payload)

    async def suspend(self) -> None:
        await self._prepare_terminal()
        await self.coordinator.suspend()
