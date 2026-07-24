from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]
RunStatus = Literal["running", "cancellation_requested", "completed", "failed", "cancelled"]
ObjectStatus = Literal["pending", "committed", "deleted"]
ContextCategory = Literal[
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
]
ContextUsageQuality = Literal[
    "rough_estimate",
    "model_tokenizer",
    "provider_reconciled",
    "unavailable",
]


def utc_now() -> datetime:
    return datetime.now(UTC)


def _non_blank(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-blank")


def _non_negative(value: int, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _utc(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{field_name} must be a UTC timestamp")


def _json_value(value: Any, field_name: str) -> None:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be JSON-compatible") from exc


def _positive_limit(value: int) -> None:
    if value <= 0:
        raise ValueError("limit must be positive")


@dataclass(frozen=True)
class SessionPrincipal:
    user_id: str
    tenant_id: str = "default"
    roles: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        _non_blank(self.user_id, "user_id")
        _non_blank(self.tenant_id, "tenant_id")
        object.__setattr__(self, "roles", frozenset(self.roles))
        if any(not isinstance(role, str) or not role.strip() for role in self.roles):
            raise ValueError("roles must contain non-blank strings")


@dataclass(frozen=True)
class SessionScope:
    tenant_id: str
    user_id: str

    def __post_init__(self) -> None:
        _non_blank(self.tenant_id, "tenant_id")
        _non_blank(self.user_id, "user_id")

    @classmethod
    def from_principal(cls, principal: SessionPrincipal) -> "SessionScope":
        return cls(tenant_id=principal.tenant_id, user_id=principal.user_id)


@dataclass(frozen=True)
class SessionRecord:
    session_uid: str
    session_id: str
    owner: SessionScope
    harness_id: str
    harness_version: str
    harness_state_schema_version: int
    title: str = ""
    model: str | None = None
    status: str = "idle"
    metadata: dict[str, JsonValue] = field(default_factory=dict)
    message_count: int = 0
    turn_count: int = 0
    version: int = 1
    archived: bool = False
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    schema_version: int = 1

    def __post_init__(self) -> None:
        for value, name in ((self.session_uid, "session_uid"), (self.session_id, "session_id"), (self.harness_id, "harness_id")):
            _non_blank(value, name)
        for value, name in (
            (self.harness_state_schema_version, "harness_state_schema_version"),
            (self.message_count, "message_count"),
            (self.turn_count, "turn_count"),
            (self.version, "version"),
        ):
            _non_negative(value, name)
        _json_value(self.metadata, "metadata")
        _utc(self.created_at, "created_at")
        _utc(self.updated_at, "updated_at")


@dataclass(frozen=True)
class SessionMessageRecord:
    session_uid: str
    session_id: str
    agent_id: str
    sequence: int
    role: Literal["user", "assistant", "tool", "system"]
    content: JsonValue
    message_id: str | None = None
    raw_provider_payload: JsonValue = None
    created_at: datetime = field(default_factory=utc_now)
    schema_version: int = 1

    def __post_init__(self) -> None:
        for value, name in ((self.session_uid, "session_uid"), (self.session_id, "session_id"), (self.agent_id, "agent_id")):
            _non_blank(value, name)
        _non_negative(self.sequence, "sequence")
        if self.role not in {"user", "assistant", "tool", "system"}:
            raise ValueError("role is invalid")
        _json_value(self.content, "content")
        _json_value(self.raw_provider_payload, "raw_provider_payload")
        _utc(self.created_at, "created_at")


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    session_uid: str
    status: RunStatus
    model: str
    idempotency_key: str
    version: int = 1
    cancellation_requested: bool = False
    error: dict[str, JsonValue] | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    finished_at: datetime | None = None
    schema_version: int = 1

    def __post_init__(self) -> None:
        for value, name in ((self.run_id, "run_id"), (self.session_uid, "session_uid"), (self.model, "model"), (self.idempotency_key, "idempotency_key")):
            _non_blank(value, name)
        _non_negative(self.version, "version")
        _json_value(self.error, "error")
        _utc(self.created_at, "created_at")
        _utc(self.updated_at, "updated_at")
        if self.finished_at is not None:
            _utc(self.finished_at, "finished_at")


@dataclass(frozen=True)
class RunHandle:
    run: RunRecord
    lease: "SessionLease"


@dataclass(frozen=True)
class HeartbeatResult:
    lease: "SessionLease"
    cancellation_requested: bool = False


@dataclass(frozen=True)
class TurnRecord:
    session_uid: str
    session_id: str
    run_id: str
    turn_id: str
    sequence: int
    input: JsonValue
    output: JsonValue
    completion: JsonValue = None
    tool_trace: tuple[JsonValue, ...] = ()
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    schema_version: int = 1

    def __post_init__(self) -> None:
        for value, name in ((self.session_uid, "session_uid"), (self.session_id, "session_id"), (self.run_id, "run_id"), (self.turn_id, "turn_id")):
            _non_blank(value, name)
        _non_negative(self.sequence, "sequence")
        _json_value(self.input, "input")
        _json_value(self.output, "output")
        _json_value(self.completion, "completion")
        _json_value(self.tool_trace, "tool_trace")
        _utc(self.created_at, "created_at")
        _utc(self.updated_at, "updated_at")


@dataclass(frozen=True)
class SessionEvent:
    run_id: str
    sequence: int
    event_type: str
    payload: JsonValue
    lease_id: str
    fencing_token: int
    idempotency_key: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    schema_version: int = 1

    def __post_init__(self) -> None:
        _non_blank(self.run_id, "run_id")
        _non_blank(self.event_type, "event_type")
        _non_blank(self.lease_id, "lease_id")
        _non_negative(self.sequence, "sequence")
        _non_negative(self.fencing_token, "fencing_token")
        _json_value(self.payload, "payload")
        _utc(self.created_at, "created_at")


@dataclass(frozen=True)
class UsageRecord:
    usage_id: str
    session_uid: str
    run_id: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_tokens: int = 0
    cost: float | None = None
    idempotency_key: str = ""
    created_at: datetime = field(default_factory=utc_now)
    schema_version: int = 1
    turn_id: str = ""
    invocation_id: str = ""
    invocation_index: int = 0
    category: str = "legacy_unattributed"
    operation: str = ""
    total_tokens: int = 0
    reasoning_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    quality: Literal["actual", "estimated", "unavailable"] = "unavailable"
    status: Literal["succeeded", "failed", "cancelled"] = "succeeded"
    agent_id: str = ""
    harness_id: str = ""
    parent_run_id: str | None = None
    cost_microunits: int | None = None
    currency: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        for value, name in ((self.usage_id, "usage_id"), (self.session_uid, "session_uid"), (self.run_id, "run_id"), (self.provider, "provider"), (self.model, "model")):
            _non_blank(value, name)
        for value, name in (
            (self.input_tokens, "input_tokens"),
            (self.output_tokens, "output_tokens"),
            (self.cache_tokens, "cache_tokens"),
            (self.total_tokens, "total_tokens"),
            (self.reasoning_tokens, "reasoning_tokens"),
            (self.cache_read_tokens, "cache_read_tokens"),
            (self.cache_write_tokens, "cache_write_tokens"),
            (self.invocation_index, "invocation_index"),
        ):
            _non_negative(value, name)
        if self.cost_microunits is not None:
            _non_negative(self.cost_microunits, "cost_microunits")
        if self.schema_version >= 2:
            for value, name in (
                (self.turn_id, "turn_id"),
                (self.invocation_id, "invocation_id"),
                (self.category, "category"),
            ):
                _non_blank(value, name)
        _utc(self.created_at, "created_at")
        if self.started_at is not None:
            _utc(self.started_at, "started_at")
        if self.completed_at is not None:
            _utc(self.completed_at, "completed_at")

    @property
    def effective_total_tokens(self) -> int:
        return self.total_tokens or self.input_tokens + self.output_tokens


@dataclass(frozen=True)
class UsageTotals:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    reasoning_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    calls: int = 0
    cost_microunits: int = 0


@dataclass(frozen=True)
class UsageGroup:
    dimensions: dict[str, str]
    totals: UsageTotals


@dataclass(frozen=True)
class UsageSummary:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_tokens: int = 0
    cost: float = 0.0
    records: tuple[UsageRecord, ...] = ()
    total_tokens: int = 0
    reasoning_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    calls: int = 0
    cost_microunits: int = 0
    groups: tuple[UsageGroup, ...] = ()
    actual_calls: int = 0
    estimated_calls: int = 0
    unavailable_calls: int = 0
    has_legacy_unattributed: bool = False
    tracking_started_at: datetime | None = None
    next_cursor: str | None = None


@dataclass(frozen=True)
class ContextComponent:
    component_id: str
    category: ContextCategory
    source: str
    content_hash: str
    estimated_tokens: int
    character_count: int
    quality: ContextUsageQuality = "rough_estimate"
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for value, name in (
            (self.component_id, "component_id"),
            (self.category, "category"),
            (self.source, "source"),
            (self.content_hash, "content_hash"),
        ):
            _non_blank(value, name)
        if len(self.component_id) > 256:
            raise ValueError("component_id must be at most 256 characters")
        if len(self.source) > 512:
            raise ValueError("source must be at most 512 characters")
        if len(self.content_hash) > 256:
            raise ValueError("content_hash must be at most 256 characters")
        if self.category not in {
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
        }:
            raise ValueError("category is invalid")
        if self.quality not in {
            "rough_estimate",
            "model_tokenizer",
            "provider_reconciled",
            "unavailable",
        }:
            raise ValueError("quality is invalid")
        _non_negative(self.estimated_tokens, "estimated_tokens")
        _non_negative(self.character_count, "character_count")
        _json_value(self.metadata, "metadata")


@dataclass(frozen=True)
class ContextUsageSnapshot:
    snapshot_id: str
    session_uid: str
    run_id: str
    turn_id: str
    invocation_id: str
    invocation_index: int
    agent_id: str
    harness_id: str
    provider: str
    model: str
    context_window_tokens: int
    estimated_input_tokens: int
    actual_input_tokens: int | None
    reconciliation_delta_tokens: int
    reserved_output_tokens: int
    quality: ContextUsageQuality
    components: tuple[ContextComponent, ...]
    captured_at: datetime
    idempotency_key: str
    invocation_category: str = "agent_inference"
    operation: str = "agent_inference"
    status: Literal["estimated", "succeeded", "failed", "cancelled"] = "estimated"
    reconciled_at: datetime | None = None
    parent_run_id: str | None = None
    manifest_mismatch: bool = False
    schema_version: int = 1

    def __post_init__(self) -> None:
        for value, name in (
            (self.snapshot_id, "snapshot_id"),
            (self.session_uid, "session_uid"),
            (self.run_id, "run_id"),
            (self.turn_id, "turn_id"),
            (self.invocation_id, "invocation_id"),
            (self.agent_id, "agent_id"),
            (self.provider, "provider"),
            (self.model, "model"),
            (self.idempotency_key, "idempotency_key"),
            (self.invocation_category, "invocation_category"),
            (self.operation, "operation"),
        ):
            _non_blank(value, name)
        for value, name in (
            (self.invocation_index, "invocation_index"),
            (self.context_window_tokens, "context_window_tokens"),
            (self.estimated_input_tokens, "estimated_input_tokens"),
            (self.reserved_output_tokens, "reserved_output_tokens"),
        ):
            _non_negative(value, name)
        if self.actual_input_tokens is not None:
            _non_negative(self.actual_input_tokens, "actual_input_tokens")
        if self.quality not in {
            "rough_estimate",
            "model_tokenizer",
            "provider_reconciled",
            "unavailable",
        }:
            raise ValueError("quality is invalid")
        if self.status not in {"estimated", "succeeded", "failed", "cancelled"}:
            raise ValueError("status is invalid")
        object.__setattr__(self, "components", tuple(self.components))
        _utc(self.captured_at, "captured_at")
        if self.reconciled_at is not None:
            _utc(self.reconciled_at, "reconciled_at")

    @property
    def used_tokens(self) -> int:
        return self.actual_input_tokens if self.actual_input_tokens is not None else self.estimated_input_tokens


@dataclass(frozen=True)
class ContextUsageSummary:
    latest: ContextUsageSnapshot | None = None
    turn_peak: ContextUsageSnapshot | None = None
    session_peak: ContextUsageSnapshot | None = None
    history: tuple[ContextUsageSnapshot, ...] = ()
    next_cursor: str | None = None


@dataclass(frozen=True)
class CheckpointRecord:
    session_uid: str
    session_id: str
    namespace: str
    key: str
    payload: JsonValue
    version: int
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    schema_version: int = 1

    def __post_init__(self) -> None:
        for value, name in ((self.session_uid, "session_uid"), (self.session_id, "session_id"), (self.namespace, "namespace"), (self.key, "key")):
            _non_blank(value, name)
        _non_negative(self.version, "version")
        _json_value(self.payload, "payload")
        _utc(self.created_at, "created_at")
        _utc(self.updated_at, "updated_at")


@dataclass(frozen=True)
class BlobRef:
    blob_id: str
    owner: SessionScope
    state: Literal["pending", "committed", "deleted"] = "pending"
    checksum_sha256: str | None = None
    size_bytes: int = 0
    created_at: datetime = field(default_factory=utc_now)
    schema_version: int = 1

    def __post_init__(self) -> None:
        _non_blank(self.blob_id, "blob_id")
        _non_negative(self.size_bytes, "size_bytes")
        _utc(self.created_at, "created_at")


@dataclass(frozen=True)
class BlobMetadata:
    content_type: str
    filename: str | None = None
    attributes: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _non_blank(self.content_type, "content_type")
        _json_value(self.attributes, "attributes")


@dataclass(frozen=True)
class BlobWriteMetadata:
    session_id: str
    object_id: str
    metadata: BlobMetadata

    def __post_init__(self) -> None:
        _non_blank(self.session_id, "session_id")
        _non_blank(self.object_id, "object_id")


@dataclass(frozen=True)
class SessionObjectRecord:
    object_id: str
    session_uid: str
    session_id: str
    kind: str
    name: str
    content_type: str
    status: ObjectStatus = "pending"
    blob_ref: BlobRef | None = None
    metadata: dict[str, JsonValue] = field(default_factory=dict)
    version: int = 1
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    schema_version: int = 1

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.object_id, "object_id"),
            (self.session_uid, "session_uid"),
            (self.session_id, "session_id"),
            (self.kind, "kind"),
            (self.name, "name"),
            (self.content_type, "content_type"),
        ):
            _non_blank(value, field_name)
        _non_negative(self.version, "version")
        _json_value(self.metadata, "metadata")
        _utc(self.created_at, "created_at")
        _utc(self.updated_at, "updated_at")


@dataclass(frozen=True)
class SessionLease:
    lease_id: str
    session_uid: str
    holder_id: str
    fencing_token: int
    acquired_at: datetime
    expires_at: datetime
    heartbeat_at: datetime
    schema_version: int = 1

    def __post_init__(self) -> None:
        for value, name in ((self.lease_id, "lease_id"), (self.session_uid, "session_uid"), (self.holder_id, "holder_id")):
            _non_blank(value, name)
        _non_negative(self.fencing_token, "fencing_token")
        for value, name in ((self.acquired_at, "acquired_at"), (self.expires_at, "expires_at"), (self.heartbeat_at, "heartbeat_at")):
            _utc(value, name)


@dataclass(frozen=True)
class StoreHealth:
    healthy: bool
    provider: str
    schema_version: int
    detail: str = ""
    checked_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _non_blank(self.provider, "provider")
        _utc(self.checked_at, "checked_at")


@dataclass(frozen=True)
class SessionCreateSpec:
    session_id: str
    harness_id: str
    harness_version: str
    harness_state_schema_version: int
    title: str = ""
    model: str | None = None
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _non_blank(self.session_id, "session_id")
        _non_blank(self.harness_id, "harness_id")
        _json_value(self.metadata, "metadata")


@dataclass(frozen=True)
class SessionPatch:
    title: str | None = None
    archived: bool | None = None
    metadata: dict[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        _json_value(self.metadata, "metadata")


@dataclass(frozen=True)
class SessionListQuery:
    archived: bool | None = None
    limit: int = 50
    cursor: str | None = None

    def __post_init__(self) -> None:
        _positive_limit(self.limit)


@dataclass(frozen=True)
class HistoryQuery:
    agent_id: str | None = None
    limit: int = 100
    cursor: str | None = None

    def __post_init__(self) -> None:
        _positive_limit(self.limit)


@dataclass(frozen=True)
class TurnQuery:
    limit: int = 50
    cursor: str | None = None

    def __post_init__(self) -> None:
        _positive_limit(self.limit)


@dataclass(frozen=True)
class UsageQuery:
    run_id: str | None = None
    provider: str | None = None
    turn_id: str | None = None
    model: str | None = None
    category: str | None = None
    quality: Literal["actual", "estimated", "unavailable"] | None = None
    status: Literal["succeeded", "failed", "cancelled"] | None = None
    agent_id: str | None = None
    from_time: datetime | None = None
    to_time: datetime | None = None
    include_children: bool = True
    include_records: bool = True
    group_by: tuple[str, ...] = ()
    limit: int = 100
    cursor: str | None = None

    def __post_init__(self) -> None:
        _positive_limit(self.limit)
        if self.quality not in {None, "actual", "estimated", "unavailable"}:
            raise ValueError("quality must be actual, estimated, or unavailable")
        if self.status not in {None, "succeeded", "failed", "cancelled"}:
            raise ValueError("status must be succeeded, failed, or cancelled")
        allowed = {
            "turn_id",
            "run_id",
            "category",
            "provider",
            "model",
            "quality",
            "status",
            "agent_id",
            "harness_id",
            "currency",
        }
        if len(self.group_by) > 3:
            raise ValueError("group_by supports at most three dimensions")
        invalid = sorted(set(self.group_by) - allowed)
        if invalid:
            raise ValueError(f"unsupported usage group_by dimensions: {', '.join(invalid)}")
        if self.from_time is not None:
            _utc(self.from_time, "from_time")
        if self.to_time is not None:
            _utc(self.to_time, "to_time")
        if self.from_time is not None and self.to_time is not None and self.from_time > self.to_time:
            raise ValueError("from_time must not be after to_time")


@dataclass(frozen=True)
class ContextUsageQuery:
    run_id: str | None = None
    turn_id: str | None = None
    provider: str | None = None
    model: str | None = None
    agent_id: str | None = None
    from_time: datetime | None = None
    to_time: datetime | None = None
    include_children: bool = True
    include_history: bool = False
    detail: Literal["category", "source"] = "category"
    limit: int = 50
    cursor: str | None = None

    def __post_init__(self) -> None:
        _positive_limit(self.limit)
        if self.detail not in {"category", "source"}:
            raise ValueError("detail must be category or source")
        if self.from_time is not None:
            _utc(self.from_time, "from_time")
        if self.to_time is not None:
            _utc(self.to_time, "to_time")
        if self.from_time is not None and self.to_time is not None and self.from_time > self.to_time:
            raise ValueError("from_time must not be after to_time")


@dataclass(frozen=True)
class ObjectQuery:
    kind: str | None = None
    status: ObjectStatus | None = None
    limit: int = 50
    cursor: str | None = None

    def __post_init__(self) -> None:
        _positive_limit(self.limit)


@dataclass(frozen=True)
class BeginRunCommand:
    session_id: str
    run_id: str
    model: str
    idempotency_key: str
    holder_id: str
    lease_seconds: int = 90

    def __post_init__(self) -> None:
        for value, name in (
            (self.session_id, "session_id"),
            (self.run_id, "run_id"),
            (self.model, "model"),
            (self.idempotency_key, "idempotency_key"),
            (self.holder_id, "holder_id"),
        ):
            _non_blank(value, name)
        if self.lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")


@dataclass(frozen=True)
class CommitTurnCommand:
    run_id: str
    lease: SessionLease
    turn: TurnRecord
    messages: tuple[SessionMessageRecord, ...] = ()
    usage: tuple[UsageRecord, ...] = ()


@dataclass(frozen=True)
class FinishRunCommand:
    run_id: str
    lease: SessionLease
    error: dict[str, JsonValue] | None = None

    def __post_init__(self) -> None:
        _non_blank(self.run_id, "run_id")
        _json_value(self.error, "error")


@dataclass(frozen=True)
class CheckpointWrite:
    session_id: str
    namespace: str
    key: str
    payload: JsonValue

    def __post_init__(self) -> None:
        for value, name in ((self.session_id, "session_id"), (self.namespace, "namespace"), (self.key, "key")):
            _non_blank(value, name)
        _json_value(self.payload, "payload")


@dataclass(frozen=True)
class SessionObjectSpec:
    session_id: str
    kind: str
    name: str
    content_type: str
    metadata: dict[str, JsonValue] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for value, field_name in ((self.session_id, "session_id"), (self.kind, "kind"), (self.name, "name"), (self.content_type, "content_type")):
            _non_blank(value, field_name)
        _json_value(self.metadata, "metadata")


@dataclass(frozen=True)
class LeaseRequest:
    session_id: str
    holder_id: str
    lease_seconds: int = 90

    def __post_init__(self) -> None:
        _non_blank(self.session_id, "session_id")
        _non_blank(self.holder_id, "holder_id")
        if self.lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")


@dataclass(frozen=True)
class SessionPage:
    items: tuple[SessionRecord, ...]
    next_cursor: str | None = None


@dataclass(frozen=True)
class HistoryPage:
    items: tuple[SessionMessageRecord, ...]
    next_cursor: str | None = None


@dataclass(frozen=True)
class TurnPage:
    items: tuple[TurnRecord, ...]
    next_cursor: str | None = None


@dataclass(frozen=True)
class EventPage:
    items: tuple[SessionEvent, ...]
    next_cursor: str | None = None


@dataclass(frozen=True)
class SessionObjectPage:
    items: tuple[SessionObjectRecord, ...]
    next_cursor: str | None = None


def cursor_scope_hash(tenant_id: str, user_id: str, filters: dict[str, JsonValue]) -> str:
    _non_blank(tenant_id, "tenant_id")
    _non_blank(user_id, "user_id")
    _json_value(filters, "filters")
    canonical = json.dumps(
        {"tenant_id": tenant_id, "user_id": user_id, "filters": filters},
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _urlsafe_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _urlsafe_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def encode_cursor(payload: dict[str, JsonValue], secret: bytes) -> str:
    if not secret:
        raise ValueError("cursor secret must be non-empty")
    if "sort" not in payload or not isinstance(payload["sort"], list):
        raise ValueError("cursor sort keys are required")
    if payload.get("direction") not in {"next", "previous"}:
        raise ValueError("cursor direction must be next or previous")
    if not isinstance(payload.get("scope_hash"), str) or not payload["scope_hash"]:
        raise ValueError("cursor scope_hash is required")
    canonical_payload = {"version": 1, **payload}
    _json_value(canonical_payload, "cursor payload")
    encoded = _urlsafe_encode(json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8"))
    signature = _urlsafe_encode(hmac.new(secret, encoded.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded}.{signature}"


def decode_cursor(token: str, secret: bytes, expected_scope_hash: str) -> dict[str, JsonValue]:
    if not secret:
        raise ValueError("cursor secret must be non-empty")
    try:
        encoded, signature = token.split(".", 1)
    except ValueError as exc:
        raise ValueError("invalid cursor signature") from exc
    expected_signature = _urlsafe_encode(hmac.new(secret, encoded.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected_signature):
        raise ValueError("invalid cursor signature")
    try:
        payload = json.loads(_urlsafe_decode(encoded))
    except Exception as exc:
        raise ValueError("invalid cursor payload") from exc
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("unsupported cursor version")
    if payload.get("scope_hash") != expected_scope_hash:
        raise ValueError("cursor scope does not match query")
    return payload
