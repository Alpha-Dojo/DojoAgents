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

    def __post_init__(self) -> None:
        for value, name in ((self.usage_id, "usage_id"), (self.session_uid, "session_uid"), (self.run_id, "run_id"), (self.provider, "provider"), (self.model, "model")):
            _non_blank(value, name)
        for value, name in ((self.input_tokens, "input_tokens"), (self.output_tokens, "output_tokens"), (self.cache_tokens, "cache_tokens")):
            _non_negative(value, name)
        _utc(self.created_at, "created_at")


@dataclass(frozen=True)
class UsageSummary:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_tokens: int = 0
    cost: float = 0.0
    records: tuple[UsageRecord, ...] = ()


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
